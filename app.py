import os
import logging
from flask import Flask, session, g, redirect, url_for, request, abort, jsonify
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_migrate import Migrate
from datetime import datetime, timedelta
from flask_caching import Cache
from redis import Redis
try:
    from rq import Queue
except Exception:
    Queue = None

# Set up logging
logging.basicConfig(level=logging.INFO)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
migrate = Migrate()

# Initialize Cache
cache = Cache()

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
if not app.secret_key:
    raise RuntimeError("CRITICAL: SESSION_SECRET environment variable is missing.")

# Redis and RQ Setup
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
try:
    redis_conn = Redis.from_url(redis_url)
    # Test connection
    redis_conn.ping()
    app.task_queue = Queue("ajs_pantry_tasks", connection=redis_conn) if Queue else None
    app.config["CACHE_TYPE"] = "RedisCache"
    app.config["CACHE_REDIS_URL"] = redis_url
    logging.info("Redis connected and RQ queue initialized.")
except Exception as e:
    logging.warning(f"Redis not available ({e}). Falling back to SimpleCache and sync tasks.")
    app.task_queue = None # Fallback logic will check this
    app.config["CACHE_TYPE"] = "SimpleCache"

cache.init_app(app)

# Session Security for Shared PCs
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=15)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["REPORT_STORAGE_ROOT"] = os.environ.get(
    "REPORT_STORAGE_ROOT",
    os.path.join(os.path.expanduser("~"), "ajs-pantry-data", "reports")
)

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
migrate.init_app(app, db)

# Attempt to connect to the configured database
with app.app_context():
    import models
    from sqlalchemy import text

    try:
        db.session.execute(text("SELECT 1")).fetchone()
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
    public_endpoints = ['auth.login', 'static', 'auth.logout', 'main.home', 'super_admin.login', 'faculty.login', 'send_email']
    if request.endpoint in public_endpoints or (request.endpoint and request.endpoint.startswith('static')) or request.path.startswith('/platform-admin'):
        return

    shared_staff_endpoints = {'faculty.reports_page', 'faculty.download_floor_submission'}
    is_faculty_route = bool(
        request.endpoint
        and request.endpoint.startswith('faculty.')
        and request.endpoint not in shared_staff_endpoints
    )

    user_id = session.get("user_id")
    if user_id:
        from models import User, Tenant
        user = User.query.get(user_id)
        
        if not user:
            was_faculty = session.get('role') == 'faculty' or is_faculty_route or request.path.startswith('/faculty')
            session.clear()
            if was_faculty:
                from flask import flash
                flash('Your Faculty session expired. Please sign in again.', 'error')
                return redirect(url_for('faculty.login'))
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
    elif is_faculty_route or request.path.startswith('/faculty'):
        from flask import flash
        session.clear()
        flash('Your Faculty session expired. Please sign in again.', 'error')
        return redirect(url_for('faculty.login'))

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
        "is_super_admin": getattr(g, 'is_super_admin', False),
        "is_faculty": bool(current_user and current_user.role == 'faculty')
    }

@app.route('/favicon.ico')
def favicon():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<text y=".9em" font-size="90">🍳</text>'
        '</svg>',
        200,
        {'Content-Type': 'image/svg+xml'}
    )

from blueprints.auth import auth_bp
from blueprints.pantry import pantry_bp
from blueprints.finance import finance_bp
from blueprints.ops import ops_bp
from blueprints.admin import admin_bp
from blueprints.main import main_bp
from blueprints.super_admin import super_admin_bp
from blueprints.faculty import faculty_bp

app.register_blueprint(auth_bp)
app.register_blueprint(pantry_bp)
app.register_blueprint(finance_bp)
app.register_blueprint(ops_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(main_bp)
app.register_blueprint(super_admin_bp)
app.register_blueprint(faculty_bp)

@app.route("/internal/send-email", methods=["POST"])
def send_email():
    secret = request.headers.get("X-SECRET")
    internal_secret = os.environ.get("INTERNAL_API_SECRET")

    # Simple protection so nobody abuses your endpoint
    if not internal_secret or secret != internal_secret:
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
