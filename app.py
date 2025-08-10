import os
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import inspect

app = Flask(__name__)

# Configuration - Use environment variables
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL').replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Models with explicit table names
class Facility(db.Model):
    __tablename__ = 'facilities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    location = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True)

# Database initialization with migration check
def initialize_database():
    with app.app_context():
        inspector = inspect(db.engine)
        
        # Check if migrations table exists
        if 'alembic_version' not in inspector.get_table_names():
            from flask_migrate import init as migrate_init
            migrate_init()
        
        # Apply migrations
        from flask_migrate import upgrade
        upgrade()

        # Only seed if tables are empty
        if Facility.query.count() == 0:
            db.session.add(Facility(name='Default', location='Main'))
            db.session.commit()

# Application factory
def create_app():
    initialize_database()
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
