from flask import session, abort, g, current_app
from models import User
from datetime import datetime
from sqlalchemy import and_, or_, select

FLOOR_MIN = 1
FLOOR_MAX = 11

def tenant_filter(query):
    """Filters the query by the current tenant_id in g."""
    if hasattr(g, 'tenant_id') and g.tenant_id:
        return query.filter_by(tenant_id=g.tenant_id)
    return query

def require_super_admin():
    user = _get_current_user()
    if not user or (user.role != 'super_admin' and user.tenant_id is not None):
        abort(403)
    return user

def _extract_first_name(full_name):
    if not full_name:
        return None
    full_name = full_name.strip()
    if not full_name:
        return None
    
    parts = full_name.split()
    if not parts:
        return None
        
    if len(parts) > 1 and parts[0].lower() == 'mulla':
        return parts[1][:64]
    
    return parts[0][:64]

def _make_unique_username(base, exclude_user_id=None):
    base = (base or '').strip()
    if not base:
        return None

    candidate = base[:64]
    counter = 2
    while True:
        existing = User.query.filter_by(username=candidate).first()
        if not existing or (exclude_user_id and existing.id == exclude_user_id):
            return candidate

        suffix = str(counter)
        trim_to = max(1, 64 - len(suffix))
        candidate = f"{base[:trim_to]}{suffix}"
        counter += 1

def _ensure_username_from_full_name(user, db_session):
    if not user:
        return False
    if user.username and user.username.strip():
        return False

    first_name = _extract_first_name(user.full_name)
    if not first_name:
        return False

    unique_username = _make_unique_username(first_name, exclude_user_id=user.id)
    if not unique_username:
        return False

    user.username = unique_username
    return True

def _display_name_for(user):
    if not user:
        return ""
    first_name = _extract_first_name(user.full_name)
    if first_name:
        return first_name
    if user.username and user.username.strip():
        return user.username
    return user.email or ""

def _get_active_floor(user):
    if not user:
        return None

    if user.role != 'admin':
        return user.floor

    raw = session.get('active_floor')
    if raw is None:
        return user.floor or FLOOR_MIN

    try:
        val = int(raw)
    except Exception:
        val = user.floor or FLOOR_MIN

    if val < FLOOR_MIN:
        return FLOOR_MIN
    if val > FLOOR_MAX:
        return FLOOR_MAX
    return val

def _get_floor_options_for_admin():
    from models import Tenant
    user = _get_current_user()
    if not user or not user.tenant_id:
        return list(range(FLOOR_MIN, FLOOR_MAX + 1))
    
    tenant = Tenant.query.get(user.tenant_id)
    limit = tenant.floor_count if tenant and tenant.floor_count else FLOOR_MAX
    return list(range(FLOOR_MIN, limit + 1))

def _get_tenant_floor_options(user=None):
    from models import Tenant

    user = user or _get_current_user()
    if not user or not user.tenant_id:
        return list(range(FLOOR_MIN, FLOOR_MAX + 1))

    tenant = Tenant.query.get(user.tenant_id)
    limit = tenant.floor_count if tenant and tenant.floor_count else FLOOR_MAX
    return list(range(FLOOR_MIN, limit + 1))

def faculty_workflow_enabled_for_tenant(tenant_id=None, tenant=None):
    from models import Tenant

    if tenant is not None:
        return bool(getattr(tenant, 'faculty_workflow_enabled', True))

    tenant_id = tenant_id if tenant_id is not None else getattr(g, 'tenant_id', None)
    if tenant_id is None:
        return True

    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        return True

    return bool(getattr(tenant, 'faculty_workflow_enabled', True))

def faculty_workflow_enabled_for_user(user=None):
    user = user or _get_current_user()
    if not user or not user.tenant_id:
        return True
    return faculty_workflow_enabled_for_tenant(tenant_id=user.tenant_id)

def current_tenant_faculty_workflow_enabled(default=True):
    if hasattr(g, 'faculty_workflow_enabled'):
        return bool(g.faculty_workflow_enabled)

    tenant_id = getattr(g, 'tenant_id', None)
    if tenant_id is None:
        return default

    return faculty_workflow_enabled_for_tenant(tenant_id=tenant_id)

def _require_staff_for_floor(user):
    if not user:
        abort(401)
    if user.role not in {'admin', 'faculty', 'pantryHead', 'teaManager'}:
        abort(403)
    return user

def _require_faculty(user=None):
    user = user or _get_current_user()
    if not user:
        abort(401)
    if user.role != 'faculty':
        abort(403)
    return user

def visible_budget_condition(faculty_enabled=None):
    return visible_budget_condition_for_tenant(faculty_enabled)

def visible_budget_condition_for_tenant(faculty_enabled=None):
    from models import Budget, FacultyBudgetCycle, Tenant

    cycle_visible = Budget.cycle.has(FacultyBudgetCycle.status != 'draft')

    if faculty_enabled is False:
        return Budget.cycle_id.is_(None)

    if faculty_enabled is True:
        return or_(Budget.cycle_id.is_(None), cycle_visible)

    enabled_tenants = select(Tenant.id).where(Tenant.faculty_workflow_enabled.is_(True))
    return or_(
        Budget.cycle_id.is_(None),
        and_(cycle_visible, Budget.tenant_id.in_(enabled_tenants))
    )

def _require_team_access(user, team):
    if user.role == 'admin':
        return
    if user.role == 'pantryHead' and team.floor == user.floor:
        return
    abort(403)

def _get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return User.query.get(user_id)

import os
import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pywebpush import webpush, WebPushException

def send_email_notification(to_email, subject, html_content):
    """Dispatches an email notification, using the background queue if available."""
    if hasattr(current_app, 'task_queue') and current_app.task_queue:
        current_app.task_queue.enqueue('blueprints.utils.send_email_worker', to_email, subject, html_content)
        return True
    return send_email_worker(to_email, subject, html_content)

def send_email_worker(to_email, subject, html_content):
    """Synchronous worker that performs the actual email delivery."""
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_PASS")

    if not gmail_user or not gmail_pass:
        logging.warning("Email notification failed: GMAIL credentials not found.")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = gmail_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_content, "html"))

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        logging.error(f"Email Error: {e}")
        return False

def send_push_notification(user_id, title, body, icon=None, url=None):
    """Dispatches a push notification, using the background queue if available."""
    if hasattr(current_app, 'task_queue') and current_app.task_queue:
        current_app.task_queue.enqueue('blueprints.utils.send_push_worker', user_id, title, body, icon, url)
        return True
    return send_push_worker(user_id, title, body, icon, url)

def send_push_worker(user_id, title, body, icon=None, url=None):
    """Synchronous worker that performs the actual push delivery."""
    from models import PushSubscription, User
    from app import db, app
    
    # Worker might not have application context in some setups, but RQ usually handles it if configured
    with app.app_context():
        subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
        if not subscriptions:
            return False

        vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY")
        vapid_public_key = os.environ.get("VAPID_PUBLIC_KEY")
        vapid_claims = {"sub": "mailto:admin@maskan.local"}

        if not vapid_private_key or not vapid_public_key:
            logging.warning("Push Notification failed: VAPID keys not found in environment.")
            return False

        notification_data = {
            "title": title,
            "body": body,
            "icon": icon or "/static/icons/icon-192.png",
            "url": url or "/dashboard"
        }

        success_count = 0
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {
                            "p256dh": sub.p256dh,
                            "auth": sub.auth
                        }
                    },
                    data=json.dumps(notification_data),
                    vapid_private_key=vapid_private_key,
                    vapid_claims=vapid_claims
                )
                success_count += 1
            except WebPushException as ex:
                logging.error(f"Push Notification Error: {ex}")
                if ex.response and ex.response.status_code in [404, 410]:
                    db.session.delete(sub)
                    db.session.commit()
            except Exception as e:
                logging.error(f"General Push Error: {e}")

        return success_count > 0

def _require_user():
    user = _get_current_user()
    if not user:
        session.clear()
    return user
