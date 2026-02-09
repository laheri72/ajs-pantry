import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Set up logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "maskan-breakfast-management-secret-key")

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///maskan_breakfast.db"
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize the app with the extension
db.init_app(app)

with app.app_context():
    # Import models to ensure tables are created
    import models
    db.create_all()
    
    # Create default admin user if it doesn't exist
    try:
        from models import User
        admin = User.query.filter_by(username='Administrator').first()
        if not admin:
            from werkzeug.security import generate_password_hash
            admin_user = User()
            admin_user.username='Administrator'
            admin_user.email='admin@maskan.local'
            admin_user.password_hash=generate_password_hash('administrator')
            admin_user.role='admin'
            admin_user.floor=1
            admin_user.is_verified=True
            db.session.add(admin_user)
            db.session.commit()
            logging.info("Default admin user created")
    except Exception as e:
        logging.warning(f"Admin user creation failed: {e}")

# Import routes
from routes import *

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
