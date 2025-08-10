import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from io import BytesIO
import pandas as pd
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# Configuration - Using environment variables with defaults for development
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-me-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///worksmart.db').replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'xlsx', 'xls'}
app.config['SCHEDULER_API_ENABLED'] = False  # Disable APScheduler web interface

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='user')  # admin, coordinator, pc, clinician, user
    approved = db.Column(db.Boolean, default=False)
    facility_id = db.Column(db.Integer, db.ForeignKey('facility.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self.approved

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

class Facility(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    location = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True)
    users = db.relationship('User', backref='facility', lazy=True)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    art_number = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(100))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    village = db.Column(db.String(100))
    address = db.Column(db.Text)
    facility_id = db.Column(db.Integer, db.ForeignKey('facility.id'))
    status = db.Column(db.String(20), default='active')  # active, defaulter, IIT, dead, transfer_out
    last_pickup = db.Column(db.Date)
    next_pickup = db.Column(db.Date)
    last_vl = db.Column(db.Date)
    next_vl = db.Column(db.Date)
    negative_event = db.Column(db.String(50))
    negative_event_date = db.Column(db.Date)
    negative_event_notes = db.Column(db.Text)
    transfer_facility = db.Column(db.String(100))
    transfer_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tracking = db.relationship('Tracking', backref='client', lazy=True)

class Tracking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    intervention_type = db.Column(db.String(50))  # reminder, visit, call, status_change
    intervention_date = db.Column(db.Date, default=datetime.utcnow().date)
    findings = db.Column(db.Text)
    followup_date = db.Column(db.Date)
    resolved = db.Column(db.Boolean, default=False)

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_user.role not in roles:
                flash('You are not authorized to access this page', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def calculate_due_dates(last_date, frequency_months=1):
    if not last_date:
        return None
    return last_date + timedelta(days=30*frequency_months)

def init_scheduler():
    def check_due_clients():
        with app.app_context():
            # Clients due for pickup (within next 7 days)
            due_pickup = Client.query.filter(
                Client.status == 'active',
                Client.next_pickup <= datetime.now().date() + timedelta(days=7),
                Client.next_pickup >= datetime.now().date()
            ).all()
            
            # Clients overdue for pickup (up to 28 days)
            overdue_pickup = Client.query.filter(
                Client.status == 'active',
                Client.next_pickup < datetime.now().date(),
                Client.next_pickup >= datetime.now().date() - timedelta(days=28)
            ).all()
            
            # Process reminders
            for client in due_pickup + overdue_pickup:
                days_late = (datetime.now().date() - client.next_pickup).days if client.next_pickup < datetime.now().date() else 0
                
                # Check if reminder already sent today
                last_reminder = Tracking.query.filter(
                    Tracking.client_id == client.id,
                    Tracking.intervention_type == 'reminder',
                    Tracking.intervention_date == datetime.now().date()
                ).first()
                
                if not last_reminder:
                    # Create new reminder
                    tracking = Tracking(
                        client_id=client.id,
                        user_id=1,  # System user
                        intervention_type='reminder',
                        findings=f"Automated reminder: {'Overdue' if days_late > 0 else 'Due'} for pharmacy pickup",
                        followup_date=client.next_pickup
                    )
                    db.session.add(tracking)
            
            db.session.commit()

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=check_due_clients, trigger="interval", days=1)
    scheduler.start()

# --- Authentication Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        facility_id = request.form.get('facility_id')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password) and user.approved:
            login_user(user)
            session['facility_id'] = facility_id
            return redirect(url_for('dashboard'))
        
        flash('Invalid credentials or account not approved', 'danger')
    
    facilities = Facility.query.filter_by(active=True).all()
    return render_template('auth/login.html', facilities=facilities)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Dashboard Routes ---
@app.route('/')
@login_required
def dashboard():
    facility_id = session.get('facility_id')
    
    # Calculate stats
    stats = {
        'active_clients': Client.query.filter_by(facility_id=facility_id, status='active').count(),
        'due_pickup': Client.query.filter(
            Client.facility_id == facility_id,
            Client.status == 'active',
            Client.next_pickup <= datetime.now().date()
        ).count(),
        'due_vl': Client.query.filter(
            Client.facility_id == facility_id,
            Client.status == 'active',
            Client.next_vl <= datetime.now().date()
        ).count(),
        'defaulters': Client.query.filter_by(facility_id=facility_id, status='defaulter').count()
    }
    
    # Get due clients
    due_clients = Client.query.filter(
        Client.facility_id == facility_id,
        Client.status == 'active',
        (
            (Client.next_pickup <= datetime.now().date()) |
            (Client.next_vl <= datetime.now().date())
        )
    ).limit(10).all()
    
    return render_template('dashboard.html', 
                         stats=stats, 
                         due_clients=due_clients,
                         current_facility=Facility.query.get(facility_id))

# [Rest of your routes remain the same as in your original file...]

# --- Initialization ---
def create_app():
    # Create upload directory if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize scheduler
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        init_scheduler()
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
