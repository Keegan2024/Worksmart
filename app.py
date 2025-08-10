import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from io import BytesIO
import pandas as pd
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import inspect, text

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///app.db').replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'xlsx', 'xls'}
app.config['SCHEDULER_API_ENABLED'] = False

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Models ---
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='user')
    approved = db.Column(db.Boolean, default=False)
    facility_id = db.Column(db.Integer, db.ForeignKey('facilities.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Facility(db.Model):
    __tablename__ = 'facilities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    location = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True)
    users = db.relationship('User', backref='facility', lazy=True)
    clients = db.relationship('Client', backref='facility', lazy=True)

class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    art_number = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(100))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    village = db.Column(db.String(100))
    address = db.Column(db.Text)
    facility_id = db.Column(db.Integer, db.ForeignKey('facilities.id'))
    status = db.Column(db.String(20), default='active')
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
    __tablename__ = 'tracking'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    intervention_type = db.Column(db.String(50))
    intervention_date = db.Column(db.Date, default=datetime.utcnow().date)
    findings = db.Column(db.Text)
    followup_date = db.Column(db.Date)
    resolved = db.Column(db.Boolean, default=False)

# --- Database Initialization ---
def initialize_database():
    """Safe database initialization with migration checks"""
    with app.app_context():
        # Check if this is a fresh database
        inspector = inspect(db.engine)
        if 'alembic_version' not in inspector.get_table_names():
            # Initialize migrations if needed
            from flask_migrate import init as migrate_init
            migrate_init()
        
        # Apply any pending migrations
        from flask_migrate import upgrade
        upgrade()

        # Seed initial data if needed
        if Facility.query.count() == 0:
            default_facility = Facility(
                name='Main Facility',
                location='Default Location',
                active=True
            )
            db.session.add(default_facility)
            
            admin_user = User(
                username='admin',
                role='admin',
                approved=True
            )
            admin_user.set_password('admin')
            db.session.add(admin_user)
            
            db.session.commit()

# --- Background Scheduler ---
def init_scheduler():
    def check_due_clients():
        with app.app_context():
            # Your existing scheduler logic here
            pass

    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=check_due_clients, trigger="interval", days=1)
        scheduler.start()

# --- Application Factory ---
def create_app():
    # Create necessary directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize database
    initialize_database()
    
    # Initialize scheduler
    init_scheduler()
    
    return app

# --- Routes ---
@app.route('/')
def index():
    return jsonify({
        'status': 'success',
        'message': 'Application is running',
        'version': '1.0.0'
    })

# Include all your existing routes here
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Your login implementation
    pass

@app.route('/dashboard')
@login_required
def dashboard():
    # Your dashboard implementation
    pass

# [Include all other routes from your original implementation]

# --- Error Handlers ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('errors/500.html'), 500

# --- Run the Application ---
if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8000)))
