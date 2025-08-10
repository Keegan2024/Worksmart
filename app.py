import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
DATABASE_URL = os.getenv('DATABASE_URL')  # If not set, we will use sqlite for local testing
SEED_DATA = os.getenv('SEED_DATA', '0') == '1'

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
if DATABASE_URL:
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    # Local sqlite default (for quick testing)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///worksmart.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'index'

### Models ###
class User(db.Model):
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

# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Simple user-like wrapper so LoginManager can work with our User model
class UserWrapper:
    def __init__(self, user):
        self._user = user
    def is_authenticated(self): return True
    def is_active(self): return True
    def is_anonymous(self): return False
    def get_id(self): return str(self._user.id)

###############
# Routes - simple and minimal to get you started
###############
@app.route('/', methods=['GET', 'POST'])
def index():
    # Login page and login handler (username-based)
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password) and user.approved:
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials or account not approved', 'danger')
        return redirect(url_for('index'))
    return render_template('index.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', current_user=current_user)

# API endpoints
@app.route('/api/clients', methods=['GET'])
@login_required
def api_clients():
    # For admin roles return all; otherwise filter by user's facility
    if current_user.role in ('system_admin', 'hub_coordinator'):
        q = Client.query.all()
    else:
        q = Client.query.filter_by(facility_id=current_user.facility_id).all()
    def cl_to_dict(c):
        return {
            'id': c.id,
            'artNumber': c.art_number,
            'fullName': c.full_name,
            'age': c.age,
            'gender': c.gender,
            'phone': c.phone,
            'address': c.address,
            'coordinates': c.coordinates,
            'lastPickup': c.last_pickup.isoformat() if c.last_pickup else None,
            'nextPickup': c.next_pickup.isoformat() if c.next_pickup else None,
            'lastVL': c.last_vl.isoformat() if c.last_vl else None,
            'nextVL': c.next_vl.isoformat() if c.next_vl else None,
            'status': c.status,
            'facilityId': c.facility_id
        }
    return jsonify([cl_to_dict(c) for c in q])

@app.route('/api/clients', methods=['POST'])
@login_required
def api_clients_add():
    data = request.get_json() or request.form.to_dict()
    # Basic validation omitted for brevity
    c = Client(
        art_number=data.get('artNumber'),
        full_name=data.get('fullName'),
        age=int(data.get('age') or 0),
        gender=data.get('gender'),
        phone=data.get('phone'),
        address=data.get('address'),
        coordinates=data.get('coordinates'),
        last_pickup=_parse_date(data.get('lastPickup')),
        next_pickup=_parse_date(data.get('nextPickup')),
        last_vl=_parse_date(data.get('lastVL')),
        next_vl=_parse_date(data.get('nextVL')),
        status=data.get('status') or 'active',
        facility_id=current_user.facility_id or None
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({'status':'ok','id': c.id}), 201

def _parse_date(s):
    if not s: return None
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        try:
            return datetime.strptime(s, '%Y-%m-%d').date()
        except Exception:
            return None

@app.route('/api/facilities', methods=['GET'])
@login_required
def api_facilities():
    q = Facility.query.all()
    return jsonify([{'id': f.id, 'name': f.name, 'location': f.location, 'active': f.active} for f in q])

############
# Database seeding (runs automatically if empty and SEED_DATA enabled)
############
def seed_sample_data():
    if Facility.query.first():
        return
    f1 = Facility(name='Kitwe Central Hospital', location='Kitwe Central')
    f2 = Facility(name='Riverside Clinic', location='Riverside Township')
    f3 = Facility(name='Kamkole Health Post', location='Kamkole Village')
    db.session.add_all([f1,f2,f3])
    db.session.commit()

    # users
    users = [
        {'username':'admin','password':'admin123','role':'system_admin','full_name':'System Administrator','approved':True,'facility':f1},
        {'username':'pc001','password':'pc123','role':'professional_counselor','full_name':'Dr. Susan Phiri','approved':True,'facility':f1},
        {'username':'lc001','password':'lc123','role':'lay_counselor','full_name':'James Mwape','approved':True,'facility':f2},
        {'username':'cl001','password':'cl123','role':'clinician','full_name':'Dr. Michael Zulu','approved':True,'facility':f1},
    ]
    for u in users:
        user = User(username=u['username'], full_name=u['full_name'], role=u['role'], approved=u['approved'], facility_id=u['facility'].id)
        user.password_hash = generate_password_hash(u['password'])
        db.session.add(user)
    db.session.commit()

    # sample clients
    clients = [
        {'art_number':'KT/001/2024','full_name':'John Banda','age':35,'gender':'Male','phone':'0971234567','address':'Wusakile Compound','coordinates':'-12.8065,28.2137','last_pickup':date(2024,7,20),'next_pickup':date(2024,8,20),'last_vl':date(2024,6,15),'next_vl':date(2024,12,15),'status':'active','facility_id':f1.id},
        {'art_number':'KT/002/2024','full_name':'Mary Mwanza','age':28,'gender':'Female','phone':'0977654321','address':'Riverside Township','coordinates':'-12.8025,28.2087','last_pickup':date(2024,8,5),'next_pickup':date(2024,9,5),'last_vl':date(2024,5,20),'next_vl':date(2024,11,20),'status':'due','facility_id':f2.id},
        {'art_number':'KT/003/2024','full_name':'Peter Mulenga','age':42,'gender':'Male','phone':'0965432109','address':'Kamkole Village','coordinates':'-12.7995,28.2157','last_pickup':date(2024,7,25),'next_pickup':date(2024,8,10),'last_vl':date(2024,4,10),'next_vl':date(2024,10,10),'status':'overdue','facility_id':f3.id},
    ]
    for c in clients:
        cl = Client(**c)
        db.session.add(cl)
    db.session.commit()
    print('Seeded sample data.')

@app.before_first_request
def ensure_seed():
    try:
        db.create_all()
        if SEED_DATA:
            seed_sample_data()
    except Exception as e:
        print('DB init error:', e)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
