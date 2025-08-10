import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from io import BytesIO
import pandas as pd
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler

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

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_due_clients, trigger="interval", days=1)
scheduler.start()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///worksmart.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'xlsx', 'xls'}

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Import models (from previous implementation)
from models import User, Facility, Client, Tracking

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

# --- Client Management ---
@app.route('/clients')
@login_required
def client_list():
    facility_id = session.get('facility_id')
    search = request.args.get('search', '')
    
    query = Client.query.filter_by(facility_id=facility_id)
    
    if search:
        query = query.filter(
            (Client.art_number.contains(search)) |
            (Client.full_name.contains(search)) |
            (Client.phone.contains(search)) |
            (Client.village.contains(search))
        )
    
    clients = query.order_by(Client.next_pickup).all()
    return render_template('clients/list.html', clients=clients, search=search)

@app.route('/clients/<int:client_id>')
@login_required
def client_details(client_id):
    client = Client.query.get_or_404(client_id)
    tracking = Tracking.query.filter_by(client_id=client_id).order_by(Tracking.intervention_date.desc()).all()
    
    # Calculate days since last pickup
    days_late = (datetime.now().date() - client.last_pickup).days if client.last_pickup else None
    
    return render_template('clients/details.html', 
                         client=client, 
                         tracking=tracking,
                         days_late=days_late)

@app.route('/clients/<int:client_id>/update', methods=['POST'])
@login_required
def update_client(client_id):
    client = Client.query.get_or_404(client_id)
    
    # Handle different update types
    update_type = request.form.get('update_type')
    
    if update_type == 'pharmacy':
        client.last_pickup = datetime.strptime(request.form['pickup_date'], '%Y-%m-%d').date()
        client.next_pickup = calculate_due_dates(client.last_pickup)
        flash('Pharmacy pickup updated successfully', 'success')
    
    elif update_type == 'vl':
        client.last_vl = datetime.strptime(request.form['vl_date'], '%Y-%m-%d').date()
        client.next_vl = calculate_due_dates(client.last_vl, frequency_months=6)
        flash('Viral load updated successfully', 'success')
    
    elif update_type == 'tracking':
        tracking = Tracking(
            client_id=client_id,
            user_id=current_user.id,
            intervention_type=request.form['intervention_type'],
            findings=request.form['findings'],
            followup_date=datetime.strptime(request.form['followup_date'], '%Y-%m-%d').date() if request.form['followup_date'] else None
        )
        db.session.add(tracking)
        
        # Check if client should be marked as defaulter
        days_late = (datetime.now().date() - client.last_pickup).days if client.last_pickup else 0
        if days_late >= 28 and current_user.role in ['pc', 'admin', 'coordinator']:
            client.status = 'defaulter'
            client.negative_event = 'defaulter'
            client.negative_event_date = datetime.now().date()
            flash('Client marked as defaulter', 'warning')
        else:
            flash('Tracking intervention recorded', 'success')
    
    db.session.commit()
    return redirect(url_for('client_details', client_id=client_id))

# --- Reports and Exports ---
@app.route('/reports/due-clients')
@login_required
@role_required(['admin', 'coordinator', 'pc', 'clinician'])
def due_clients_report():
    facility_id = session.get('facility_id')
    timeframe = request.args.get('timeframe', 'today')
    
    today = datetime.now().date()
    query = Client.query.filter_by(facility_id=facility_id, status='active')
    
    if timeframe == 'today':
        clients = query.filter(Client.next_pickup == today).all()
    elif timeframe == 'week':
        clients = query.filter(
            Client.next_pickup >= today,
            Client.next_pickup <= today + timedelta(days=7)
        ).all()
    elif timeframe == 'month':
        clients = query.filter(
            Client.next_pickup >= today,
            Client.next_pickup <= today + timedelta(days=30)
        ).all()
    else:
        clients = query.filter(Client.next_pickup <= today).all()
    
    return render_template('reports/due_clients.html', 
                         clients=clients, 
                         timeframe=timeframe,
                         today=today)
@app.route('/import/tx_curr', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'coordinator'])
def import_tx_curr():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            try:
                # Read file with multiple sheet support
                if file.filename.endswith('.csv'):
                    df = pd.read_csv(file)
                else:
                    xls = pd.ExcelFile(file)
                    sheet_names = xls.sheet_names
                    df = pd.concat([xls.parse(sheet) for sheet in sheet_names])
                
                # Column mapping with flexible matching
                column_map = {
                    'art_number': ['artno', 'art number', 'art_num'],
                    'full_name': ['name', 'patient name', 'client'],
                    'age': ['age'],
                    'gender': ['sex', 'gender'],
                    'last_pickup': ['last pickup', 'last collection'],
                    'last_vl': ['last vl', 'viral load date']
                }
                
                # Find matching columns
                matched_columns = {}
                for standard_col, possible_cols in column_map.items():
                    for col in possible_cols:
                        if col in df.columns:
                            matched_columns[standard_col] = col
                            break
                
                # Validate required columns
                required = ['art_number', 'full_name']
                missing = [col for col in required if col not in matched_columns]
                if missing:
                    flash(f'Missing required columns: {", ".join(missing)}', 'danger')
                    return redirect(request.url)
                
                # Process data
                facility_id = session.get('facility_id')
                imported = updated = 0
                
                for _, row in df.iterrows():
                    art_num = str(row[matched_columns['art_number']]).strip()
                    existing = Client.query.filter_by(art_number=art_num).first()
                    
                    if existing:
                        # Update existing client
                        if 'last_pickup' in matched_columns:
                            pickup_date = pd.to_datetime(row[matched_columns['last_pickup']], errors='coerce')
                            if pd.notna(pickup_date):
                                existing.last_pickup = pickup_date.date()
                                existing.next_pickup = calculate_due_dates(existing.last_pickup)
                        
                        if 'last_vl' in matched_columns:
                            vl_date = pd.to_datetime(row[matched_columns['last_vl']], errors='coerce')
                            if pd.notna(vl_date):
                                existing.last_vl = vl_date.date()
                                existing.next_vl = calculate_due_dates(existing.last_vl, 6)
                        
                        updated += 1
                    else:
                        # Create new client
                        client = Client(
                            art_number=art_num,
                            full_name=str(row[matched_columns['full_name']]).strip(),
                            age=int(row[matched_columns.get('age', 0)]),
                            gender=str(row[matched_columns.get('gender', 'Unknown')]).strip().capitalize(),
                            facility_id=facility_id,
                            status='active'
                        )
                        
                        if 'last_pickup' in matched_columns:
                            pickup_date = pd.to_datetime(row[matched_columns['last_pickup']], errors='coerce')
                            if pd.notna(pickup_date):
                                client.last_pickup = pickup_date.date()
                                client.next_pickup = calculate_due_dates(client.last_pickup)
                        
                        db.session.add(client)
                        imported += 1
                
                db.session.commit()
                flash(f'Successfully imported {imported} and updated {updated} clients', 'success')
                return redirect(url_for('client_list'))
            
            except Exception as e:
                db.session.rollback()
                flash(f'Error during import: {str(e)}', 'danger')
                return redirect(request.url)
        
        else:
            flash('Invalid file type. Allowed: CSV, Excel (xls, xlsx)', 'danger')
            return redirect(request.url)
    
    return render_template('data/import_tx_curr.html')

@app.route('/clients/<int:client_id>/mark-defaulter', methods=['POST'])
@login_required
@role_required(['admin', 'coordinator', 'pc'])
def mark_defaulter(client_id):
    client = Client.query.get_or_404(client_id)
    
    # Get form data
    status = request.form.get('status')
    notes = request.form.get('notes', '')
    
    # Validate status
    if status not in ['defaulter', 'IIT', 'dead', 'transfer_out']:
        flash('Invalid status selected', 'danger')
        return redirect(url_for('client_details', client_id=client_id))
    
    # Update client
    client.status = status
    client.negative_event = status
    client.negative_event_date = datetime.now().date()
    client.negative_event_notes = notes
    
    # Handle transfer out
    if status == 'transfer_out':
        client.transfer_facility = request.form.get('transfer_facility', '')
        client.transfer_date = datetime.now().date()
    
    # Record tracking intervention
    tracking = Tracking(
        client_id=client_id,
        user_id=current_user.id,
        intervention_type='status_change',
        findings=f"Marked as {status}. Notes: {notes}",
        resolved=True
    )
    db.session.add(tracking)
    db.session.commit()
    
    flash(f'Client status updated to {status}', 'success')
    return redirect(url_for('client_details', client_id=client_id))
@app.route('/export/tx_curr')
@login_required
@role_required(['admin', 'coordinator', 'pc'])
def export_tx_curr():
    facility_id = session.get('facility_id')
    clients = Client.query.filter_by(facility_id=facility_id).all()
    
    # Prepare data
    data = []
    for client in clients:
        data.append({
            'ART Number': client.art_number,
            'Name': client.full_name,
            'Age': client.age,
            'Gender': client.gender,
            'Village': client.village,
            'Phone': client.phone,
            'Status': client.status,
            'Last Pickup': client.last_pickup.strftime('%Y-%m-%d') if client.last_pickup else '',
            'Next Pickup': client.next_pickup.strftime('%Y-%m-%d') if client.next_pickup else '',
            'Days Late': (datetime.now().date() - client.last_pickup).days if client.last_pickup else 0,
            'Last VL Date': client.last_vl.strftime('%Y-%m-%d') if client.last_vl else '',
            'Next VL Date': client.next_vl.strftime('%Y-%m-%d') if client.next_vl else '',
            'VL Eligible': 'Yes' if client.next_vl and client.next_vl <= datetime.now().date() else 'No',
            'Interventions': len(client.tracking)
        })
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Create Excel file with multiple sheets
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Main data sheet
        df.to_excel(writer, sheet_name='TX_CURR', index=False)
        
        # Due clients sheet
        due_df = df[df['Next Pickup'] != '']
        due_df = due_df[due_df['Status'] == 'active']
        due_df.to_excel(writer, sheet_name='Due for Pickup', index=False)
        
        # Defaulters sheet
        defaulter_df = df[df['Status'].isin(['defaulter', 'IIT'])]
        defaulter_df.to_excel(writer, sheet_name='Defaulters', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'tx_curr_report_{datetime.now().date()}.xlsx'
    )

@app.route('/export/clients')
@login_required
@role_required(['admin', 'coordinator', 'pc'])
def export_clients():
    facility_id = session.get('facility_id')
    clients = Client.query.filter_by(facility_id=facility_id).all()
    
    # Create DataFrame
    data = []
    for client in clients:
        data.append({
            'ART Number': client.art_number,
            'Name': client.full_name,
            'Age': client.age,
            'Gender': client.gender,
            'Phone': client.phone,
            'Village': client.village,
            'Status': client.status,
            'Last Pickup': client.last_pickup.strftime('%Y-%m-%d') if client.last_pickup else '',
            'Next Pickup': client.next_pickup.strftime('%Y-%m-%d') if client.next_pickup else '',
            'Last VL': client.last_vl.strftime('%Y-%m-%d') if client.last_vl else '',
            'Next VL': client.next_vl.strftime('%Y-%m-%d') if client.next_vl else ''
        })
    
    df = pd.DataFrame(data)
    
    # Export to Excel
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Clients', index=False)
    writer.close()
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'worksmart_clients_{datetime.now().date()}.xlsx'
    )

# --- Data Import ---
@app.route('/import/clients', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'coordinator'])
def import_clients():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                # Read file based on extension
                if filename.endswith('.csv'):
                    df = pd.read_csv(filepath)
                else:  # Excel
                    df = pd.read_excel(filepath)
                
                # Validate columns
                required_columns = {'art_number', 'full_name', 'age', 'gender'}
                if not required_columns.issubset(df.columns):
                    missing = required_columns - set(df.columns)
                    flash(f'Missing required columns: {", ".join(missing)}', 'danger')
                    return redirect(request.url)
                
                # Process data
                facility_id = session.get('facility_id')
                imported = 0
                for _, row in df.iterrows():
                    client = Client(
                        art_number=row['art_number'],
                        full_name=row['full_name'],
                        age=row.get('age', 0),
                        gender=row.get('gender', 'Unknown'),
                        phone=row.get('phone', ''),
                        village=row.get('village', ''),
                        address=row.get('address', ''),
                        facility_id=facility_id,
                        status='active'
                    )
                    db.session.add(client)
                    imported += 1
                
                db.session.commit()
                flash(f'Successfully imported {imported} clients', 'success')
                return redirect(url_for('client_list'))
            
            except Exception as e:
                db.session.rollback()
                flash(f'Error importing data: {str(e)}', 'danger')
                return redirect(request.url)
            
        else:
            flash('Invalid file type. Only CSV and Excel files allowed', 'danger')
            return redirect(request.url)
    
    return render_template('data/import.html')

# --- User Management ---
@app.route('/users')
@login_required
@role_required(['admin', 'coordinator'])
def user_management():
    users = User.query.all()
    return render_template('users/list.html', users=users)

@app.route('/users/approve/<int:user_id>')
@login_required
@role_required(['admin', 'coordinator'])
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.approved = True
    db.session.commit()
    flash(f'User {user.username} approved successfully', 'success')
    return redirect(url_for('user_management'))

# --- Facility Management ---
@app.route('/facilities')
@login_required
@role_required(['admin', 'coordinator'])
def facility_management():
    facilities = Facility.query.all()
    return render_template('facilities/list.html', facilities=facilities)

# --- Error Handlers ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
