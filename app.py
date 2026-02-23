import os
import logging
from flask import Flask, session, g, redirect, url_for, request, abort, jsonify
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "maskan-breakfast-management-secret-key")

# Session Security for Shared PCs
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=15)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

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

    # Basic schema guardrails
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if not inspector.has_table("tenants"):
            logging.warning("Multi-tenant tables not found. Run scripts/multi_tenant_migration.sql")
    except Exception as e:
        logging.critical(str(e))


    # Admin setup
    try:
        query_engine = db.engine
        from models import User
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=query_engine)
        session_db = Session()
        admin = session_db.query(User).filter_by(username='Administrator').first()
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
            session_db.add(admin_user)
            session_db.commit()
            logging.info("Default admin user created.")
        session_db.close()
    except Exception as e:
        logging.warning(f"Admin management failed: {e}")

from blueprints.utils import _get_current_user, _get_active_floor, _display_name_for, _get_floor_options_for_admin

@app.before_request
def enforce_tenancy():
    # Public routes and Platform Admin portal
    public_endpoints = ['auth.login', 'static', 'auth.logout', 'main.home', 'super_admin.login', 'send_email']
    if request.endpoint in public_endpoints or (request.endpoint and request.endpoint.startswith('static')) or request.path.startswith('/platform-admin'):
        return

    user_id = session.get("user_id")
    if user_id:
        from models import User, Tenant
        user = User.query.get(user_id)
        
        if not user:
            session.clear()
            return redirect(url_for('auth.login'))

        # Super Admin Bypass (tenant_id is NULL)
        if user.role == 'super_admin' or user.tenant_id is None:
            g.tenant_id = None
            g.is_super_admin = True
            return

        # Tenant Status Check
        tenant = Tenant.query.get(user.tenant_id)
        if not tenant or not tenant.is_active:
            session.clear()
            return "Your tenant account is suspended or does not exist. Please contact support.", 403

        # Bind tenant context
        g.tenant_id = user.tenant_id
        g.tenant_name = tenant.name
        g.is_super_admin = False
        session['tenant_id'] = str(user.tenant_id)

@app.context_processor
def inject_current_user():
    current_user = _get_current_user()
    active_floor = _get_active_floor(current_user)
    return {
        "current_user": current_user,
        "display_name": _display_name_for(current_user),
        "needs_profile_details": bool(current_user and current_user.role == 'member' and not (current_user.username and current_user.username.strip())),
        "active_floor": active_floor,
        "floor_options": _get_floor_options_for_admin() if current_user and current_user.role in ['admin', 'super_admin'] else [],
        "now": datetime.utcnow(),
        "tenant_name": getattr(g, 'tenant_name', None),
        "is_super_admin": getattr(g, 'is_super_admin', False)
    }

from blueprints.auth import auth_bp
from blueprints.pantry import pantry_bp
from blueprints.finance import finance_bp
from blueprints.ops import ops_bp
from blueprints.admin import admin_bp
from blueprints.main import main_bp
from blueprints.super_admin import super_admin_bp

app.register_blueprint(auth_bp)
app.register_blueprint(pantry_bp)
app.register_blueprint(finance_bp)
app.register_blueprint(ops_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(main_bp)
app.register_blueprint(super_admin_bp)

@app.route("/internal/send-email", methods=["POST"])
def send_email():
    secret = request.headers.get("X-SECRET")

    # Simple protection so nobody abuses your endpoint
    if secret != "PANTRY_SECRET_123":
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    to_email = data.get("email")
    subject = data.get("subject")
    html_content = data.get("html")

    if not to_email:
        return jsonify({"error": "Missing email"}), 400

    msg = MIMEMultipart("alternative")
    msg["From"] = os.environ.get("GMAIL_USER")
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_content, "html"))

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(
            os.environ.get("GMAIL_USER"),
            os.environ.get("GMAIL_PASS")
        )
        server.sendmail(
            os.environ.get("GMAIL_USER"),
            to_email,
            msg.as_string()
        )
        server.quit()

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
