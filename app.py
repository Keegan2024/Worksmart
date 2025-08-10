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
        # Handle Neon.tech connection string
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
login_manager.login_view = 'index'

# [Keep all your existing models here...]

# [Keep all your existing routes here...]

# Database Initialization
def seed_sample_data():
    if Facility.query.first():
        return
    
    # [Keep your existing seeding logic...]
    print('Database seeded with sample data')

def parse_date(date_str):
    # [Keep your existing date parsing...]
    pass

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

# Custom 404 handler
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
