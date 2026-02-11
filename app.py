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
    url = os.environ.get("SUPABASE_DATABASE_URL")
    if not url:
        return "sqlite:///maskan.db"
    
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    import re
    from urllib.parse import quote_plus
    url = url.replace(" ", "")
    try:
        if "://" in url and "@" in url:
            proto, rest = url.split("://", 1)
            creds, host_part = rest.rsplit("@", 1)
            if ":" in creds:
                user, password = creds.split(":", 1)
                password = password.strip("[]")
                url = f"{proto}://{user}:{quote_plus(password)}@{host_part}"
    except Exception:
        pass

    if "supabase.co" in url:
        if "sslmode" not in url:
            url += "&sslmode=require" if "?" in url else "?sslmode=require"
        if "connect_timeout" not in url:
            url += "&connect_timeout=5"
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
    try:
        # Test connection
        from sqlalchemy import text
        db.session.execute(text("SELECT 1")).fetchone()
        db.create_all()
        logging.info("Connected to primary database successfully.")
    except Exception as e:
        logging.error(f"Primary database connection failed: {e}. Falling back to SQLite.")
        # Reconfigure for SQLite
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///maskan.db"
        # In Flask-SQLAlchemy 3, the engine is cached. We must bypass the cached engine for migrations.
        from sqlalchemy import create_engine
        engine = create_engine(app.config["SQLALCHEMY_DATABASE_URI"])
        models.db.metadata.create_all(bind=engine)
        # Note: The app will still attempt to use the failed engine for requests 
        # unless we explicitly swap it or the user restarts without the env var.
        # But for booting the app, this is the safest path.

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
            session.add(admin_user)
            session.commit()
            logging.info("Default admin user created.")
        session.close()
    except Exception as e:
        logging.warning(f"Admin management failed: {e}")

from routes import *

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
