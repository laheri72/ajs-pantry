from flask import session, abort, g
from models import User
from datetime import datetime

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
    return full_name.split()[0][:64]

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

def _require_staff_for_floor(user):
    if not user:
        abort(401)
    if user.role not in {'admin', 'pantryHead', 'teaManager'}:
        abort(403)
    return user

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
from pywebpush import webpush, WebPushException

def send_push_notification(user_id, title, body, icon=None, url=None):
    """Sends a push notification to all subscriptions of a specific user."""
    from models import PushSubscription
    from app import db
    
    subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subscriptions:
        return False

    vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY")
    vapid_public_key = os.environ.get("VAPID_PUBLIC_KEY")
    vapid_claims = {"sub": "mailto:admin@maskan.local"} # Replace with your email if desired

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
            # If the subscription is no longer valid, we should probably delete it
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
