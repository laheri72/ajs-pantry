import os
import logging
import click
from dotenv import load_dotenv

load_dotenv()
from flask import Flask, session, g, redirect, url_for, request, abort, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from blueprints.rate_limit_keys import client_ip_key
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_migrate import Migrate
from datetime import datetime, timedelta
from flask_caching import Cache
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from redis import Redis
from werkzeug.middleware.proxy_fix import ProxyFix
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
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    headers_enabled=True,
    in_memory_fallback_enabled=True,
    key_prefix="ajs-pantry",
    strategy="fixed-window",
    swallow_errors=True,
)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
if not app.secret_key:
    raise RuntimeError("CRITICAL: SESSION_SECRET environment variable is missing.")

if os.environ.get("TRUST_PROXY_HEADERS", "1").lower() not in {"0", "false", "no", "off"}:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# Redis and RQ Setup
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
rate_limit_storage_url = os.environ.get("RATE_LIMIT_STORAGE_URL") or os.environ.get("REDIS_URL")
if rate_limit_storage_url:
    app.config["RATELIMIT_STORAGE_URI"] = rate_limit_storage_url
else:
    app.config["RATELIMIT_STORAGE_URI"] = "memory://"
    logging.warning("RATE_LIMIT_STORAGE_URL/REDIS_URL not configured. Login rate limits use in-memory storage.")

try:
    redis_conn = Redis.from_url(redis_url)
    # Test connection
    redis_conn.ping()
    # Separate queues so a slow OCR backlog can't delay quick notification/email jobs.
    app.task_queue = Queue("ajs_pantry_tasks", connection=redis_conn) if Queue else None
    app.notification_queue = Queue("ajs_pantry_notifications", connection=redis_conn) if Queue else None
    app.email_queue = Queue("ajs_pantry_emails", connection=redis_conn) if Queue else None
    app.config["CACHE_TYPE"] = "RedisCache"
    app.config["CACHE_REDIS_URL"] = redis_url
    logging.info("Redis connected and RQ queues initialized (tasks, notifications, emails).")
except Exception as e:
    logging.warning(f"Redis not available ({e}). Falling back to SimpleCache and sync tasks.")
    app.task_queue = None  # Fallback logic will check this
    app.notification_queue = None
    app.email_queue = None
    app.config["CACHE_TYPE"] = "SimpleCache"

cache.init_app(app)
limiter.init_app(app)
csrf.init_app(app)

# Session Security for Shared PCs
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=15)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

# Session cookie hardening
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "1").lower() not in {"0", "false", "no", "off"}
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["REPORT_STORAGE_ROOT"] = os.environ.get(
    "REPORT_STORAGE_ROOT",
    os.path.join(os.path.expanduser("~"), "ajs-pantry-data", "reports")
)
app.config["RECEIPT_IMPORT_STALL_SECONDS"] = os.environ.get("RECEIPT_IMPORT_STALL_SECONDS", "90")
app.config["RECEIPT_IMPORT_ASYNC_ENABLED"] = os.environ.get(
    "RECEIPT_IMPORT_ASYNC_ENABLED",
    "0" if os.name == "nt" else "1",
)
app.config["RECEIPT_TEMP_FILE_TTL_SECONDS"] = os.environ.get("RECEIPT_TEMP_FILE_TTL_SECONDS", "300")

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


@app.cli.command("bootstrap-admin")
@click.option("--username", default="Administrator", show_default=True, help="Username for the new admin account.")
@click.option("--floor", default=1, show_default=True, type=int, help="Floor to assign the new admin account to.")
def bootstrap_admin(username, floor):
    """One-time CLI bootstrap for the first Administrator account.

    Generates a random password, prints it once, and forces a password
    change on first login. Refuses to run if the username already exists.
    Run with: flask --app app.py bootstrap-admin
    """
    import secrets
    from models import User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        existing = User.query.filter_by(username=username).first()
        if existing:
            click.echo(f"Refusing to bootstrap: user '{username}' already exists.", err=True)
            raise SystemExit(1)

        password = secrets.token_urlsafe(18)
        admin_user = User()
        admin_user.username = username
        admin_user.email = f"{username.lower()}@maskan.local"
        admin_user.password_hash = generate_password_hash(password)
        admin_user.role = 'admin'
        admin_user.floor = floor
        admin_user.is_verified = True
        admin_user.is_active = True
        admin_user.is_first_login = True
        db.session.add(admin_user)
        db.session.commit()

        click.echo("Administrator account created.")
        click.echo(f"username: {username}")
        click.echo(f"temporary password: {password}")
        click.echo("This password is shown only once. The account must change it on first login.")

from blueprints.utils import (
    _get_active_floor,
    _get_current_user,
    _display_name_for,
    _get_floor_options_for_admin,
    faculty_workflow_enabled_for_tenant,
)

@app.before_request
def enforce_tenancy():
    # Public routes and Platform Admin portal.
    public_endpoints = ['auth.login', 'static', 'auth.logout', 'main.home', 'super_admin.login', 'faculty.login', 'send_email', 'healthz']
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
        
        if not user or not getattr(user, 'is_active', True):
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
        g.faculty_workflow_enabled = faculty_workflow_enabled_for_tenant(tenant=tenant)
        session['tenant_id'] = str(user.tenant_id)
        if user.role == 'faculty' and not g.faculty_workflow_enabled:
            from flask import flash
            session.clear()
            flash('Faculty workflow is disabled for this tenant right now.', 'error')
            return redirect(url_for('faculty.login'))
    elif is_faculty_route or request.path.startswith('/faculty'):
        from flask import flash
        session.clear()
        flash('Your Faculty session expired. Please sign in again.', 'error')
        return redirect(url_for('faculty.login'))

@app.errorhandler(429)
def handle_rate_limit(error):
    retry_after = getattr(error, "retry_after", None) or 60
    message = "Too many login attempts. Please wait a minute and try again."
    headers = {"Retry-After": str(retry_after)}

    wants_json = (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
        or request.path.startswith("/expenses/import-")
        or request.path.startswith("/expenses/save-imported-bill")
        or request.path.startswith("/api/")
        or request.path.startswith("/internal/")
    )
    if wants_json:
        return jsonify({"error": "rate_limited", "retry_after": retry_after}), 429, headers

    from flask import flash, render_template

    login_templates = {
        "auth.login": "login.html",
        "auth.staff_login": "staff_login.html",
        "faculty.login": "faculty/login.html",
        "super_admin.login": "super_admin/login.html",
    }
    template = login_templates.get(request.endpoint)
    if template:
        flash(message, "error")
        return render_template(template), 429, headers

    return message, 429, headers

@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    message = "Your session security token expired. Please try again."

    wants_json = (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
        or request.path.startswith("/api/")
        or request.path.startswith("/internal/")
    )
    if wants_json:
        return jsonify({"error": "csrf_invalid", "message": message}), 400

    from flask import flash

    flash(message, "error")
    referrer = request.referrer
    if referrer and referrer.startswith(request.host_url):
        return redirect(referrer)
    return redirect(url_for('main.home'))

@app.context_processor
def inject_terms():
    from config.terms import TERMS
    return {f"TERM_{k}": v for k, v in TERMS.items()}

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
        "is_faculty": bool(current_user and current_user.role == 'faculty'),
        "faculty_workflow_enabled": getattr(g, 'faculty_workflow_enabled', True),
    }

def format_indian_currency(val, show_decimals=True):
    if val is None:
        return "0.00" if show_decimals else "0"
    try:
        val = float(val)
    except (ValueError, TypeError):
        return "0.00" if show_decimals else "0"

    is_negative = val < 0
    val = abs(val)

    if show_decimals:
        s = f"{val:.2f}"
        parts = s.split('.')
        integer_part = parts[0]
        decimal_part = parts[1]
    else:
        integer_part = f"{round(val):.0f}"
        decimal_part = ""

    if len(integer_part) <= 3:
        formatted_int = integer_part
    else:
        last_three = integer_part[-3:]
        remaining = integer_part[:-3]
        groups = []
        while len(remaining) > 2:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.insert(0, remaining)
        formatted_int = ",".join(groups) + "," + last_three

    if show_decimals:
        res = f"{formatted_int}.{decimal_part}"
    else:
        res = formatted_int

    return f"-{res}" if is_negative else res

app.jinja_env.filters['inr'] = format_indian_currency
app.jinja_env.filters['indian_currency'] = format_indian_currency


def format_hijri_date(dt):
    if not dt:
        return ""
    if hasattr(dt, 'date') and callable(getattr(dt, 'date')):
        dt = dt.date()
    year = dt.year
    month = dt.month
    day = dt.day
    if month < 3:
        year -= 1
        month += 12
    if (dt.year < 1582) or (dt.year == 1582 and (dt.month < 10 or (dt.month == 10 and dt.day < 5))):
        b = 0
    else:
        a = year // 100
        b = 2 - a + (a // 4)
    ajd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + b - 1524.5
    left = int(ajd - 1948083.5)
    y30 = int(left / 10631.0)
    left -= y30 * 10631
    i = 0
    days_in_30_years = [
        354, 708, 1063, 1417, 1771, 2126, 2480, 2834, 3189, 3543,
        3898, 4252, 4606, 4961, 5315, 5669, 6024, 6378, 6732, 7087,
        7441, 7796, 8150, 8504, 8859, 9213, 9567, 9922, 10276, 10631
    ]
    days_in_year = [30, 59, 89, 118, 148, 177, 207, 236, 266, 295, 325]
    hijri_month_names = [
        "Moharram al-Haraam", "Safar al-Muzaffar", "Rabi al-Awwal", "Rabi al-Aakhar",
        "Jumada al-Ula", "Jumada al-Ukhra", "Rajab al-Asab", "Shabaan al-Karim",
        "Ramadaan al-Moazzam", "Shawwal al-Mukarram", "Zilqadah al-Haraam", "Zilhaj al-Haraam"
    ]
    while i < len(days_in_30_years) and left > days_in_30_years[i]:
        i += 1
    h_year = int(round(y30 * 30.0 + i))
    if i > 0:
        left -= days_in_30_years[i - 1]
    i = 0
    while i < len(days_in_year) and left > days_in_year[i]:
        i += 1
    h_month = int(round(i))
    h_date = int(round(left - days_in_year[i - 1])) if i > 0 else int(round(left))
    m_name = hijri_month_names[h_month] if 0 <= h_month < 12 else ""
    return f"{h_date} {m_name} {h_year}H"


app.jinja_env.filters['hijri'] = format_hijri_date

@app.route('/favicon.ico')
def favicon():
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.root_path, 'static', 'favicon_io'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/healthz')
def healthz():
    from sqlalchemy import text
    try:
        db.session.execute(text("SELECT 1")).fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    status = 200 if db_ok else 503
    return jsonify({"status": "ok" if db_ok else "error", "database": db_ok}), status

from blueprints.auth import auth_bp
from blueprints.pantry import pantry_bp
from blueprints.finance import finance_bp
from blueprints.ops import ops_bp
from blueprints.admin import admin_bp
from blueprints.main import main_bp
from blueprints.super_admin import super_admin_bp
from blueprints.faculty import faculty_bp

# Import route modules to register them before blueprint registration
from blueprints.auth import routes as auth_routes
from blueprints.pantry import routes as pantry_routes
from blueprints.finance import routes as finance_routes
from blueprints.ops import routes as ops_routes
from blueprints.admin import routes as admin_routes
from blueprints.main import routes as main_routes
from blueprints.super_admin import routes as super_admin_routes
from blueprints.faculty import routes as faculty_routes

app.register_blueprint(auth_bp)
app.register_blueprint(pantry_bp)
app.register_blueprint(finance_bp)
app.register_blueprint(ops_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(main_bp)
app.register_blueprint(super_admin_bp)
app.register_blueprint(faculty_bp)

MAX_INTERNAL_EMAIL_SUBJECT_LEN = 200
MAX_INTERNAL_EMAIL_HTML_LEN = 200_000


@app.route("/internal/send-email", methods=["POST"])
@csrf.exempt
@limiter.limit("20 per minute; 200 per hour", key_func=client_ip_key)
def send_email():
    import hmac as hmac_module

    secret = request.headers.get("X-SECRET") or ""
    internal_secret = os.environ.get("INTERNAL_API_SECRET") or ""

    # Constant-time comparison so the secret can't be brute-forced via timing.
    if not internal_secret or not hmac_module.compare_digest(secret, internal_secret):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    to_email = (data.get("email") or "").strip()
    subject = (data.get("subject") or "").strip()
    html_content = data.get("html") or ""

    if not to_email or "@" not in to_email:
        return jsonify({"error": "Missing or invalid email"}), 400
    if not subject or len(subject) > MAX_INTERNAL_EMAIL_SUBJECT_LEN:
        return jsonify({"error": "Missing or oversized subject"}), 400
    if not html_content or len(html_content) > MAX_INTERNAL_EMAIL_HTML_LEN:
        return jsonify({"error": "Missing or oversized html body"}), 400

    from blueprints.utils import send_email_notification

    try:
        send_email_notification(to_email, subject, html_content)
    except Exception:
        logging.exception("Failed to dispatch internal email to %s", to_email)
        return jsonify({"error": "Failed to send email"}), 500

    return jsonify({"success": True})
