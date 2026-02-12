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

def get_db_url():
    # Read both possible env names
    url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DATABASE_URL")

    # If still missing → stop immediately (no SQLite fallback)
    if not url:
        raise RuntimeError("No DATABASE_URL or SUPABASE_DATABASE_URL set.")

    # Fix old postgres:// prefix
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # Encode password safely
    from urllib.parse import quote_plus

    try:
        proto, rest = url.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        user, password = creds.split(":", 1)
        password = quote_plus(password)
        url = f"{proto}://{user}:{password}@{host}"
    except Exception:
        pass  # if parsing fails, keep original

    # Ensure SSL for Supabase
    if "supabase.co" in url and "sslmode" not in url:
        url += "?sslmode=require"

    return url


# Initial configuration
app.config["SQLALCHEMY_DATABASE_URI"] = get_db_url()
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

db.init_app(app)

# Attempt to connect to the configured database
with app.app_context():
    import models
    from sqlalchemy import text

    try:
        db.session.execute(text("SELECT 1")).fetchone()
        db.create_all()
        logging.info("Connected to primary database successfully.")
    except Exception as e:
        logging.critical("DATABASE CONNECTION FAILED. App will stop.")
        raise RuntimeError("Cannot connect to primary database.") from e


    # Admin setup
    try:
        # Use a fresh engine if primary failed
        query_engine = db.engine
        if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
            from sqlalchemy import create_engine
            query_engine = create_engine(app.config["SQLALCHEMY_DATABASE_URI"])
        
        from models import User
        # Check if admin exists using the engine directly to avoid session issues
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=query_engine)
        session = Session()
        admin = session.query(User).filter_by(username='Administrator').first()
        if not admin:
            from werkzeug.security import generate_password_hash
            admin_user = User()
            admin_user.username='Administrator'
            admin_user.email='admin@maskan.local'
            admin_user.password_hash=generate_password_hash('administrator')
            admin_user.role='admin'
            admin_user.floor=1
            admin_user.is_verified=True
            admin_user.is_first_login=False
            session.add(admin_user)
            session.commit()
            logging.info("Default admin user created.")
        session.close()
    except Exception as e:
        logging.warning(f"Admin management failed: {e}")

from routes import *

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
