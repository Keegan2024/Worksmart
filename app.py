import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from dotenv import load_dotenv
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))
    full_name = db.Column(db.String(120))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    role = db.Column(db.String(50))  # admin, pc, lc, clinician, coordinator
    facility_id = db.Column(db.Integer, db.ForeignKey('facilities.id'))
    approved = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime)
    
    facility = db.relationship('Facility', back_populates='users')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Facility(db.Model):
    __tablename__ = 'facilities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    district = db.Column(db.String(100))
    province = db.Column(db.String(100))
    location = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True)
    
    users = db.relationship('User', back_populates='facility')
    clients = db.relationship('Client', back_populates='facility')

class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    art_number = db.Column(db.String(80), unique=True)
    full_name = db.Column(db.String(200))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(20))
    phone = db.Column(db.String(30))
    address = db.Column(db.String(255))
    village = db.Column(db.String(100))
    coordinates = db.Column(db.String(100))  # lat,long
    status = db.Column(db.String(50), default='active')  # active, IIT, defaulter, dead, transfer_out
    facility_id = db.Column(db.Integer, db.ForeignKey('facilities.id'))
    
    # Tracking dates
    last_pickup = db.Column(db.Date)
    next_pickup = db.Column(db.Date)
    last_vl = db.Column(db.Date)
    next_vl = db.Column(db.Date)
    last_eac = db.Column(db.Date)
    next_eac = db.Column(db.Date)
    last_cervical = db.Column(db.Date)
    next_cervical = db.Column(db.Date)
    
    # Negative events
    negative_event = db.Column(db.String(50))
    negative_event_date = db.Column(db.Date)
    negative_event_notes = db.Column(db.Text)
    
    facility = db.relationship('Facility', back_populates='clients')
    tracking = db.relationship('Tracking', back_populates='client')

class Tracking(db.Model):
    __tablename__ = 'tracking'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    intervention_date = db.Column(db.Date, default=datetime.utcnow)
    intervention_type = db.Column(db.String(80))  # phone, home_visit, etc.
    findings = db.Column(db.Text)
    followup_date = db.Column(db.Date)
    resolved = db.Column(db.Boolean, default=False)
    
    client = db.relationship('Client', back_populates='tracking')
    user = db.relationship('User')
load_dotenv()

# Configuration
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
DATABASE_URL = os.getenv('DATABASE_URL')
SEED_DATA = os.getenv('SEED_DATA', '0') == '1'

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

# Database Configuration
if DATABASE_URL:
    try:
        db_url = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg2://')
        if '?' in db_url and 'sslmode' not in db_url:
            db_url += '&sslmode=require'
        elif '?' not in db_url:
            db_url += '?sslmode=require'
            
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': 5,
            'max_overflow': 10
        }
        print("Using PostgreSQL database with connection pooling")
    except Exception as e:
        print(f"Error configuring PostgreSQL: {e}")
        raise
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///worksmart.db'
    print("Using SQLite database for local development")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120))
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    role = db.Column(db.String(50))
    facility_id = db.Column(db.Integer, db.ForeignKey('facility.id'))
    approved = db.Column(db.Boolean, default=False)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Facility(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    location = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True)
    users = db.relationship('User', backref='facility', lazy=True)
    clients = db.relationship('Client', backref='facility', lazy=True)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    art_number = db.Column(db.String(80), unique=True)
    full_name = db.Column(db.String(200))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(20))
    phone = db.Column(db.String(30))
    address = db.Column(db.String(255))
    coordinates = db.Column(db.String(100))
    last_pickup = db.Column(db.Date)
    next_pickup = db.Column(db.Date)
    last_vl = db.Column(db.Date)
    next_vl = db.Column(db.Date)
    status = db.Column(db.String(50), default='active')
    facility_id = db.Column(db.Integer, db.ForeignKey('facility.id'))
    tracking = db.relationship('Tracking', backref='client', lazy=True)

class Tracking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    intervention = db.Column(db.String(80))
    findings = db.Column(db.Text)
    followup_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(120))

# Flask-Login Configuration
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Application Routes
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password) and user.approved:
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials or account not approved', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', current_user=current_user)

# API Endpoints (keep your existing API routes)
# ...

# Database Initialization
def seed_sample_data():
    if Facility.query.first():
        return
    
    facilities = [
        Facility(name='Kitwe Central Hospital', location='Kitwe Central'),
        Facility(name='Riverside Clinic', location='Riverside Township'),
        Facility(name='Kamkole Health Post', location='Kamkole Village')
    ]
    db.session.add_all(facilities)
    db.session.commit()

    users = [
        {'username': 'admin', 'password': 'admin123', 'role': 'system_admin', 
         'full_name': 'System Administrator', 'approved': True, 'facility': facilities[0]},
        {'username': 'pc001', 'password': 'pc123', 'role': 'professional_counselor',
         'full_name': 'Dr. Susan Phiri', 'approved': True, 'facility': facilities[0]},
        {'username': 'lc001', 'password': 'lc123', 'role': 'lay_counselor',
         'full_name': 'James Mwape', 'approved': True, 'facility': facilities[1]},
        {'username': 'cl001', 'password': 'cl123', 'role': 'clinician',
         'full_name': 'Dr. Michael Zulu', 'approved': True, 'facility': facilities[0]}
    ]

    for u in users:
        user = User(
            username=u['username'],
            full_name=u['full_name'],
            role=u['role'],
            approved=u['approved'],
            facility_id=u['facility'].id
        )
        user.password_hash = generate_password_hash(u['password'])
        db.session.add(user)
    
    db.session.commit()
    print('Database seeded with sample data')

# Initialize database
with app.app_context():
    try:
        db.create_all()
        if SEED_DATA:
            seed_sample_data()
    except Exception as e:
        print(f'Database initialization error: {e}')

# Health Check Endpoint
@app.route('/health')
def health_check():
    try:
        db.session.execute('SELECT 1')
        return jsonify({'status': 'healthy', 'database': 'connected'}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# Simple 404 handler
@app.errorhandler(404)
def page_not_found(e):
    return "<h1>404</h1><p>Page not found.</p>", 404

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
