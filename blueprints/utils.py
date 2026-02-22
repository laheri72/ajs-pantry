from flask import session, abort
from models import User
from datetime import datetime

FLOOR_MIN = 1
FLOOR_MAX = 11

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
    return list(range(FLOOR_MIN, FLOOR_MAX + 1))

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

def _require_user():
    user = _get_current_user()
    if not user:
        session.clear()
    return user
