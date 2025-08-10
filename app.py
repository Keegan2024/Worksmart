import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from dotenv import load_dotenv

# Load environment variables
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
            'max_overflow': 10,
            'connect_args': {
                'options': '-c statement_timeout=30000'
            }
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
login_manager.login_view = 'index'

# Database Models (keep your existing models here)
# ... [Your existing model classes] ...

# Flask-Login Configuration
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class UserWrapper:
    def __init__(self, user):
        self._user = user
    def is_authenticated(self): return True
    def is_active(self): return True
    def is_anonymous(self): return False
    def get_id(self): return str(self._user.id)

# Application Routes (keep your existing routes here)
# ... [Your existing route functions] ...

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
    
    clients = [
        {'art_number': 'KT/001/2024', 'full_name': 'John Banda', 'age': 35, 'gender': 'Male',
         'phone': '0971234567', 'address': 'Wusakile Compound', 'coordinates': '-12.8065,28.2137',
         'last_pickup': date(2024, 7, 20), 'next_pickup': date(2024, 8, 20),
         'last_vl': date(2024, 6, 15), 'next_vl': date(2024, 12, 15), 'status': 'active',
         'facility_id': facilities[0].id},
        # Add other sample clients...
    ]

    for c in clients:
        db.session.add(Client(**c))
    
    db.session.commit()
    print('Database seeded with sample data')

def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str).date()
    except ValueError:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return None

# New initialization approach for Flask 2.3+
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

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
