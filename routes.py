from flask import render_template, request, redirect, url_for, session, flash, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, db
from models import User, Menu, Expense, TeaTask, Suggestion, Feedback, Request, ProcurementItem, Team, TeamMember
from datetime import datetime, date, timedelta
import logging
from sqlalchemy import or_, func


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


def _ensure_username_from_full_name(user):
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


@app.context_processor
def inject_current_user():
    current_user = _get_current_user()
    active_floor = _get_active_floor(current_user)
    return {
        "current_user": current_user,
        "display_name": _display_name_for(current_user),
        "needs_profile_details": bool(current_user and current_user.role == 'member' and not (current_user.username and current_user.username.strip())),
        "active_floor": active_floor,
        "floor_options": _get_floor_options_for_admin() if current_user and current_user.role == 'admin' else [],
    }

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = 'member'
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        user = None
        user = User.query.filter_by(email=email, role=role).first()
            
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            if _ensure_username_from_full_name(user):
                db.session.commit()
            if user.is_first_login:
                session['temp_user_id'] = user.id
                return redirect(url_for('change_password'))
            
            session['user_id'] = user.id
            session['role'] = user.role
            session['floor'] = user.floor
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('login.html')


@app.route('/staff-login', methods=['GET', 'POST'])
def staff_login():
    if request.method == 'POST':
        role = (request.form.get('role') or '').strip()
        email = request.form.get('email', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if role not in {'admin', 'pantryHead', 'teaManager'}:
            flash('Invalid role selected', 'error')
            return render_template('staff_login.html')

        if role == 'admin' and not username:
            flash('Admin login requires a username (not email).', 'error')
            return render_template('staff_login.html')
        if role != 'admin' and not email:
            flash('Please enter your email address.', 'error')
            return render_template('staff_login.html')

        user = None
        if role == 'admin':
            user = User.query.filter_by(username=username, role='admin').first()
        else:
            user = User.query.filter_by(email=email, role=role).first()

        if not user or not user.password_hash:
            flash('Invalid credentials', 'error')
            if role == 'admin' and user and not user.password_hash:
                flash('Admin password is not set. Reset it and try again.', 'error')
            return render_template('staff_login.html')

        if check_password_hash(user.password_hash, password):
            if _ensure_username_from_full_name(user):
                db.session.commit()

            if user.role != 'admin' and user.is_first_login:
                session['temp_user_id'] = user.id
                return redirect(url_for('change_password'))

            session['user_id'] = user.id
            session['role'] = user.role
            session['floor'] = user.floor
            if user.role == 'admin':
                session['active_floor'] = user.floor
            return redirect(url_for('dashboard'))

        flash('Invalid credentials', 'error')

    return render_template('staff_login.html')

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'temp_user_id' not in session:
        return redirect(url_for('login'))
        
    user = User.query.get(session['temp_user_id'])
    if not user:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('change_password.html')
            
        user.password_hash = generate_password_hash(new_password)
        user.is_first_login = False
        db.session.commit()
        
        session.pop('temp_user_id', None)
        session['user_id'] = user.id
        session['role'] = user.role
        session['floor'] = user.floor
        if user.role == 'admin':
            session['active_floor'] = user.floor
        
        flash('Password updated successfully', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('change_password.html')


@app.route('/admin/active-floor', methods=['POST'])
def set_active_floor():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if user.role != 'admin':
        abort(403)

    try:
        new_floor = int(request.form.get('floor') or '')
    except Exception:
        flash('Invalid floor', 'error')
        return redirect(request.referrer or url_for('dashboard'))

    if new_floor < FLOOR_MIN or new_floor > FLOOR_MAX:
        flash('Invalid floor', 'error')
        return redirect(request.referrer or url_for('dashboard'))

    session['active_floor'] = new_floor
    flash(f'Now viewing Floor {new_floor}', 'success')
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/teams', methods=['POST'])
def create_team():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if user.role not in {'admin', 'pantryHead'}:
        abort(403)

    floor = _get_active_floor(user)
    if user.role == 'pantryHead':
        floor = user.floor

    name = (request.form.get('name') or '').strip()
    icon = (request.form.get('icon') or '').strip() or None
    if not name:
        flash('Team name is required', 'error')
        return redirect(url_for('people'))

    existing = Team.query.filter_by(floor=floor, name=name).first()
    if existing:
        flash('Team name already exists on this floor', 'error')
        return redirect(url_for('people'))

    team = Team(name=name, icon=icon, floor=floor, created_by_id=user.id)
    db.session.add(team)
    db.session.commit()
    flash('Team created', 'success')
    return redirect(url_for('people'))


@app.route('/teams/<int:team_id>/update', methods=['POST'])
def update_team(team_id):
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if user.role not in {'admin', 'pantryHead'}:
        abort(403)

    team = Team.query.get(team_id)
    if not team:
        abort(404)

    _require_team_access(user, team)

    name = (request.form.get('name') or '').strip()
    icon = (request.form.get('icon') or '').strip() or None
    if not name:
        flash('Team name is required', 'error')
        return redirect(url_for('people'))

    if Team.query.filter(Team.floor == team.floor, Team.name == name, Team.id != team.id).first():
        flash('Team name already exists on this floor', 'error')
        return redirect(url_for('people'))

    team.name = name
    team.icon = icon
    db.session.commit()
    flash('Team updated', 'success')
    return redirect(url_for('people'))


@app.route('/teams/<int:team_id>/delete', methods=['POST'])
def delete_team(team_id):
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if user.role not in {'admin', 'pantryHead'}:
        abort(403)

    team = Team.query.get(team_id)
    if not team:
        abort(404)

    _require_team_access(user, team)

    TeamMember.query.filter_by(team_id=team.id).delete(synchronize_session=False)
    Menu.query.filter_by(assigned_team_id=team.id).update({"assigned_team_id": None}, synchronize_session=False)
    db.session.delete(team)
    db.session.commit()
    flash('Team deleted', 'success')
    return redirect(url_for('people'))


@app.route('/teams/<int:team_id>/members/add', methods=['POST'])
def add_team_member(team_id):
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if user.role not in {'admin', 'pantryHead'}:
        abort(403)

    team = Team.query.get(team_id)
    if not team:
        abort(404)

    _require_team_access(user, team)

    try:
        member_id = int(request.form.get('user_id') or '')
    except Exception:
        flash('Invalid user selected', 'error')
        return redirect(url_for('people'))

    member = User.query.get(member_id)
    if not member or member.floor != team.floor or member.role == 'admin':
        flash('User must be on this floor', 'error')
        return redirect(url_for('people'))

    if TeamMember.query.filter_by(team_id=team.id, user_id=member.id).first():
        flash('User is already in this team', 'error')
        return redirect(url_for('people'))

    db.session.add(TeamMember(team_id=team.id, user_id=member.id))
    db.session.commit()
    flash('Member added to team', 'success')
    return redirect(url_for('people'))


@app.route('/teams/<int:team_id>/members/remove', methods=['POST'])
def remove_team_member(team_id):
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if user.role not in {'admin', 'pantryHead'}:
        abort(403)

    team = Team.query.get(team_id)
    if not team:
        abort(404)

    _require_team_access(user, team)

    try:
        member_id = int(request.form.get('user_id') or '')
    except Exception:
        flash('Invalid user selected', 'error')
        return redirect(url_for('people'))

    TeamMember.query.filter_by(team_id=team.id, user_id=member_id).delete(synchronize_session=False)
    db.session.commit()
    flash('Member removed', 'success')
    return redirect(url_for('people'))

@app.route('/dashboard')
def dashboard():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    floor = _get_active_floor(user)
    today = date.today()
    upcoming_until = today + timedelta(days=2)
    since_dt = datetime.utcnow() - timedelta(days=2)
    
    stats = {
        'user_count': User.query.filter_by(floor=floor).count(),
        'pending_requests': Request.query.filter_by(floor=floor, status='pending').count(),
        'weekly_expenses': sum([e.amount for e in Expense.query.filter_by(floor=floor).all()])
    }

    upcoming_tea_duties = (
        TeaTask.query.filter_by(floor=floor, assigned_to_id=user.id)
        .filter(TeaTask.status != 'completed', TeaTask.date >= today, TeaTask.date <= upcoming_until)
        .order_by(TeaTask.date.asc())
        .all()
    )

    upcoming_procurement_assignments = (
        ProcurementItem.query.filter_by(floor=floor, assigned_to_id=user.id)
        .filter(ProcurementItem.status != 'completed', ProcurementItem.created_at >= since_dt)
        .order_by(ProcurementItem.created_at.desc())
        .all()
    )

    team_ids = [
        tid
        for (tid,) in (
            db.session.query(TeamMember.team_id)
            .join(Team, TeamMember.team_id == Team.id)
            .filter(Team.floor == floor, TeamMember.user_id == user.id)
            .all()
        )
    ]
    menu_filters = [Menu.assigned_to_id == user.id]
    if team_ids:
        menu_filters.append(Menu.assigned_team_id.in_(team_ids))

    upcoming_menu_assignments = (
        Menu.query.filter_by(floor=floor)
        .filter(Menu.date >= today, Menu.date <= upcoming_until)
        .filter(or_(*menu_filters))
        .order_by(Menu.date.asc())
        .all()
    )
    
    return render_template(
        'dashboard.html',
        user=user,
        stats=stats,
        upcoming_tea_duties=upcoming_tea_duties,
        upcoming_procurement_assignments=upcoming_procurement_assignments,
        upcoming_menu_assignments=upcoming_menu_assignments,
        today=today,
        upcoming_until=upcoming_until,
        current_user=user,
    )


@app.route('/home')
def home():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    floor = _get_active_floor(user)
    stats = {
        'user_count': User.query.filter_by(floor=floor).count(),
        'pending_requests': Request.query.filter_by(floor=floor, status='pending').count(),
        'weekly_expenses': sum([e.amount for e in Expense.query.filter_by(floor=floor).all()])
    }

    return render_template('home.html', user=user, stats=stats, current_user=user)


@app.route('/people')
def people():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    floor = _get_active_floor(user)
    users = User.query.filter_by(floor=floor).all()
    users.sort(key=lambda u: (u.full_name or u.username or u.email or "").lower())
    teams = Team.query.filter_by(floor=floor).order_by(Team.name.asc()).all()

    team_memberships = TeamMember.query.join(Team, TeamMember.team_id == Team.id).filter(Team.floor == floor).all()
    members_by_team_id = {}
    for tm in team_memberships:
        members_by_team_id.setdefault(tm.team_id, []).append(tm.user)

    for team_id, members in members_by_team_id.items():
        members.sort(key=lambda u: (u.full_name or u.username or u.email or "").lower())

    my_team_ids = [tm.team_id for tm in team_memberships if tm.user_id == user.id]
    my_teams = [t for t in teams if t.id in set(my_team_ids)]

    return render_template(
        'people.html',
        users=users,
        teams=teams,
        members_by_team_id=members_by_team_id,
        my_teams=my_teams,
        current_user=user,
    )


@app.route('/calendar')
def calendar():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    floor = _get_active_floor(user)
    floor_menus = Menu.query.filter_by(floor=floor).all()
    floor_tea_tasks = TeaTask.query.filter_by(floor=floor).all()

    menus = [
        {
            "id": m.id,
            "title": m.title,
            "description": m.description,
            "date": m.date.isoformat() if m.date else None,
            "meal_type": m.meal_type,
            "dish_type": getattr(m, "dish_type", "main"),
            "assigned_to_id": m.assigned_to_id,
            "assigned_to_label": (
                (
                    (f"{m.assigned_team.icon} {m.assigned_team.name}".strip() if m.assigned_team.icon else m.assigned_team.name)
                    if m.assigned_team
                    else None
                )
                or (m.assigned_to.full_name if m.assigned_to and m.assigned_to.full_name else None)
                or (m.assigned_to.username if m.assigned_to and m.assigned_to.username else None)
                or (m.assigned_to.email if m.assigned_to else None)
            ),
        }
        for m in floor_menus
    ]

    tea_tasks = [
        {
            "id": t.id,
            "title": "Tea Duty",
            "date": t.date.isoformat() if t.date else None,
            "status": t.status,
            "assigned_to_id": t.assigned_to_id,
            "assigned_to_name": (t.assigned_to.full_name or t.assigned_to.username or t.assigned_to.email) if t.assigned_to else None,
        }
        for t in floor_tea_tasks
    ]

    return render_template('calendar.html', menus=menus, tea_tasks=tea_tasks, current_user=user)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    user = _require_user()
    if not user or user.role != 'admin':
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_user':
            role = request.form.get('role')
            floor = int(request.form.get('floor', user.floor))
            
            new_user = User()
            new_user.role = role
            new_user.floor = floor
            new_user.password_hash = generate_password_hash('maskan1447')
            new_user.is_first_login = True
            
            if role == 'member':
                tr_number = request.form.get('tr_number')
                new_user.tr_number = tr_number
                new_user.email = f"{tr_number}@jameasaifiyah.edu"
            else:
                new_user.email = request.form.get('email')
                
            db.session.add(new_user)
            db.session.commit()
            flash(f'User added successfully', 'success')
            
    all_users = User.query.all()
    return render_template('admin.html', user=user, all_users=all_users, current_user=user)


@app.route('/floor-admin', methods=['GET', 'POST'])
def floor_admin():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if user.role not in {'admin', 'pantryHead'}:
        abort(403)

    floor = _get_active_floor(user)
    floor_users = User.query.filter_by(floor=floor).order_by(User.role.asc(), User.email.asc()).all()
    tea_managers = [u for u in floor_users if u.role == 'teaManager']

    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()

        if action == 'assign_tea_manager':
            try:
                target_user_id = int(request.form.get('user_id') or '')
            except Exception:
                flash('Invalid user selected', 'error')
                return redirect(url_for('floor_admin'))

            target = User.query.get(target_user_id)
            if not target:
                flash('User not found', 'error')
                return redirect(url_for('floor_admin'))

            if user.role == 'pantryHead' and target.floor != user.floor:
                abort(403)

            if target.floor != floor:
                flash('User must be on the selected floor', 'error')
                return redirect(url_for('floor_admin'))

            if target.role != 'member':
                flash('Only members can be assigned as tea manager', 'error')
                return redirect(url_for('floor_admin'))

            target.role = 'teaManager'
            db.session.commit()
            flash('Tea manager assigned successfully', 'success')
            return redirect(url_for('floor_admin'))

        if action == 'remove_tea_manager':
            try:
                target_user_id = int(request.form.get('user_id') or '')
            except Exception:
                flash('Invalid user selected', 'error')
                return redirect(url_for('floor_admin'))

            target = User.query.get(target_user_id)
            if not target:
                flash('User not found', 'error')
                return redirect(url_for('floor_admin'))

            if user.role == 'pantryHead' and target.floor != user.floor:
                abort(403)

            if target.floor != floor:
                flash('User must be on the selected floor', 'error')
                return redirect(url_for('floor_admin'))

            if target.role != 'teaManager':
                flash('Selected user is not a tea manager', 'error')
                return redirect(url_for('floor_admin'))

            target.role = 'member'
            db.session.commit()
            flash('Tea manager removed successfully', 'success')
            return redirect(url_for('floor_admin'))

        flash('Unknown action', 'error')
        return redirect(url_for('floor_admin'))

    return render_template(
        'floor_admin.html',
        floor=floor,
        floor_users=floor_users,
        tea_managers=tea_managers,
        current_user=user,
    )

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        user.full_name = request.form.get('full_name')
        user.phone_number = request.form.get('phone_number')

        _ensure_username_from_full_name(user)
        
        new_password = request.form.get('new_password')
        if new_password:
            user.password_hash = generate_password_hash(new_password)
            
        db.session.commit()
        flash('Profile updated successfully', 'success')
        
    return render_template('profile.html', user=user, current_user=user)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

# Remaining routes for menus, tea, expenses, etc. (kept for functionality)
@app.route('/menus', methods=['GET', 'POST'])
def menus():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    floor = _get_active_floor(user)
    floor_users = User.query.filter_by(floor=floor).all()
    floor_teams = Team.query.filter_by(floor=floor).order_by(Team.name.asc()).all()

    if request.method == 'POST' and user.role in ['admin', 'pantryHead']:
        try:
            menu_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        except Exception:
            flash('Invalid menu date', 'error')
            return redirect(url_for('menus'))

        assigned_to_id = request.form.get('assigned_to_id') or None
        assigned_team_id = request.form.get('assigned_team_id') or None
        if assigned_team_id:
            try:
                assigned_team_id = int(assigned_team_id)
            except ValueError:
                assigned_team_id = None
        if assigned_to_id:
            try:
                assigned_to_id = int(assigned_to_id)
            except ValueError:
                assigned_to_id = None

        if assigned_team_id and not Team.query.filter_by(id=assigned_team_id, floor=floor).first():
            flash('Assigned team must be on your floor', 'error')
            assigned_team_id = None

        if assigned_team_id:
            assigned_to_id = None

        if assigned_to_id and not User.query.filter_by(id=assigned_to_id, floor=floor).first():
            flash('Assigned user must be on your floor', 'error')
            assigned_to_id = None

        menu = Menu(
            title=request.form.get('title'),
            description=request.form.get('description'),
            date=menu_date,
            meal_type=request.form.get('meal_type'),
            dish_type=request.form.get('dish_type') or 'main',
            assigned_to_id=assigned_to_id,
            assigned_team_id=assigned_team_id,
            floor=floor,
            created_by_id=user.id,
        )
        db.session.add(menu)
        db.session.commit()
        flash('Menu added successfully', 'success')

    floor_menus = Menu.query.filter_by(floor=floor).order_by(Menu.date.desc()).all()
    return render_template('menus.html', menus=floor_menus, floor_users=floor_users, floor_teams=floor_teams, current_user=user)


@app.route('/menus/<int:menu_id>/delete', methods=['POST'])
def delete_menu(menu_id):
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if user.role not in ['admin', 'pantryHead']:
        abort(403)

    menu = Menu.query.get(menu_id)
    if not menu:
        abort(404)
    if user.role == 'pantryHead' and menu.floor != user.floor:
        abort(404)

    db.session.delete(menu)
    db.session.commit()
    flash('Menu deleted successfully', 'success')
    return redirect(url_for('menus'))

@app.route('/tea', methods=['GET', 'POST'])
def tea():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    floor = _get_active_floor(user)
    floor_users = User.query.filter_by(floor=floor).all()

    if request.method == 'POST' and user.role in ['admin', 'teaManager']:
        try:
            task_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        except Exception:
            flash('Invalid tea task date', 'error')
            return redirect(url_for('tea'))

        assigned_to_id = request.form.get('assigned_to_id') or None
        if assigned_to_id:
            try:
                assigned_to_id = int(assigned_to_id)
            except ValueError:
                assigned_to_id = None

        if assigned_to_id and not User.query.filter_by(id=assigned_to_id, floor=floor).first():
            flash('Assigned user must be on your floor', 'error')
            assigned_to_id = None

        task = TeaTask(
            date=task_date,
            assigned_to_id=assigned_to_id,
            floor=floor,
            created_by_id=user.id,
        )
        db.session.add(task)
        db.session.commit()
        flash('Tea task added successfully', 'success')
        return redirect(url_for('tea'))

    month_param = (request.args.get('month') or '').strip()
    today = date.today()
    if month_param:
        try:
            year_str, month_str = month_param.split('-', 1)
            year = int(year_str)
            month = int(month_str)
            month_start = date(year, month, 1)
        except Exception:
            flash('Invalid month filter', 'error')
            return redirect(url_for('tea'))
    else:
        month_start = date(today.year, today.month, 1)
        month_param = f"{today.year:04d}-{today.month:02d}"

    if month_start.month == 12:
        month_end = date(month_start.year + 1, 1, 1)
    else:
        month_end = date(month_start.year, month_start.month + 1, 1)

    task_query = TeaTask.query.filter_by(floor=floor).filter(TeaTask.date >= month_start, TeaTask.date < month_end)
    floor_tasks = task_query.order_by(TeaTask.date.desc()).all()

    count_rows = (
        db.session.query(TeaTask.assigned_to_id, func.count(TeaTask.id))
        .filter(
            TeaTask.floor == floor,
            TeaTask.date >= month_start,
            TeaTask.date < month_end,
            TeaTask.status == 'completed',
            TeaTask.assigned_to_id.isnot(None),
        )
        .group_by(TeaTask.assigned_to_id)
        .all()
    )
    counts = {user_id: int(cnt) for user_id, cnt in count_rows}
    tea_counts = [
        {"user": u, "count": counts.get(u.id, 0)}
        for u in floor_users
        if u.role != 'admin'
    ]
    tea_counts.sort(key=lambda x: (x["count"], (x["user"].full_name or x["user"].username or x["user"].email or "").lower()))

    return render_template(
        'tea.html',
        tea_tasks=floor_tasks,
        floor_users=floor_users,
        tea_counts=tea_counts,
        selected_month=month_param,
        month_start=month_start,
        current_user=user,
    )


@app.route('/tea/complete/<int:task_id>', methods=['POST'])
def complete_tea_task(task_id):
    user = _require_user()
    if not user:
        return ('', 401)

    if user.role not in ['admin', 'teaManager']:
        return ('', 403)

    task = TeaTask.query.get(task_id)
    if not task:
        return ('', 404)
    if user.role != 'admin' and task.floor != user.floor:
        return ('', 404)

    task.status = 'completed'
    db.session.commit()
    return ('', 204)

@app.route('/expenses', methods=['GET', 'POST'])
def expenses():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    floor = _get_active_floor(user)
    if request.method == 'POST' and user.role in ['admin', 'pantryHead']:
        try:
            expense_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        except Exception:
            flash('Invalid expense date', 'error')
            return redirect(url_for('expenses'))

        exp = Expense(
            description=request.form.get('description'),
            amount=float(request.form.get('amount')),
            category=request.form.get('category'),
            date=expense_date,
            user_id=user.id,
            floor=floor,
        )
        db.session.add(exp)
        db.session.commit()
        flash('Expense added successfully', 'success')
        return redirect(
            url_for(
                'expenses',
                category=(request.args.get('category') or None),
                date=(request.args.get('date') or None),
            )
        )

    filter_category = (request.args.get('category') or '').strip()
    filter_date = (request.args.get('date') or '').strip()

    query = Expense.query.filter_by(floor=floor)
    if filter_category:
        query = query.filter(Expense.category == filter_category)
    if filter_date:
        try:
            query = query.filter(Expense.date == datetime.strptime(filter_date, '%Y-%m-%d').date())
        except Exception:
            flash('Invalid filter date', 'error')
            filter_date = ''

    floor_expenses = query.order_by(Expense.date.desc()).all()
    total_amount = sum(e.amount for e in floor_expenses)
    categories = Expense.query.filter_by(floor=floor).with_entities(Expense.category).distinct().all()

    return render_template(
        'expenses.html',
        expenses=floor_expenses,
        total_amount=total_amount,
        categories=categories,
        filter_category=filter_category,
        filter_date=filter_date,
        current_user=user,
    )


@app.route('/expenses/<int:expense_id>/delete', methods=['POST'])
def delete_expense(expense_id):
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if user.role not in ['admin', 'pantryHead']:
        abort(403)

    expense = Expense.query.get(expense_id)
    if not expense:
        abort(404)
    if user.role == 'pantryHead' and expense.floor != user.floor:
        abort(404)

    db.session.delete(expense)
    db.session.commit()
    flash('Expense deleted successfully', 'success')
    return redirect(url_for('expenses'))


@app.route('/suggestions', methods=['GET', 'POST'])
def suggestions():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        suggestion = Suggestion(
            title=request.form.get('title'),
            description=request.form.get('description'),
            user_id=user.id,
            floor=user.floor,
        )
        db.session.add(suggestion)
        db.session.commit()
        flash('Suggestion submitted successfully. Pending approval.', 'success')
        return redirect(url_for('suggestions'))

    floor = _get_active_floor(user)
    if user.role == 'admin':
        visible_suggestions = Suggestion.query.filter_by(floor=floor).order_by(Suggestion.created_at.desc()).all()
    elif user.role == 'pantryHead':
        visible_suggestions = Suggestion.query.filter_by(floor=user.floor).order_by(Suggestion.created_at.desc()).all()
    else:
        visible_suggestions = (
            Suggestion.query.filter_by(floor=user.floor, status='approved')
            .order_by(Suggestion.created_at.desc())
            .all()
        )

    return render_template('suggestions.html', suggestions=visible_suggestions, current_user=user)


@app.route('/suggestions/<int:suggestion_id>/status', methods=['POST'])
def update_suggestion_status(suggestion_id):
    user = _require_user()
    if not user:
        return ('', 401)

    if user.role not in {'admin', 'pantryHead'}:
        return ('', 403)

    suggestion = Suggestion.query.get(suggestion_id)
    if not suggestion:
        return ('', 404)

    if user.role == 'pantryHead' and suggestion.floor != user.floor:
        return ('', 403)

    payload = request.get_json(silent=True) or {}
    new_status = (payload.get('status') or request.form.get('status') or '').strip().lower()
    if new_status == 'accepted':
        new_status = 'approved'

    allowed = {'pending', 'approved', 'rejected'}
    if new_status not in allowed:
        return jsonify({"error": "invalid_status", "allowed": sorted(allowed)}), 400

    suggestion.status = new_status
    db.session.commit()
    return ('', 204)


@app.route('/suggestions/<int:suggestion_id>/delete', methods=['POST'])
def delete_suggestion(suggestion_id):
    user = _require_user()
    if not user:
        return ('', 401)

    if user.role not in {'admin', 'pantryHead'}:
        return ('', 403)

    suggestion = Suggestion.query.get(suggestion_id)
    if not suggestion:
        return ('', 404)

    if user.role == 'pantryHead' and suggestion.floor != user.floor:
        return ('', 403)

    db.session.delete(suggestion)
    db.session.commit()
    return ('', 204)


@app.route('/feedbacks', methods=['GET', 'POST'])
def feedbacks():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            rating = int(request.form.get('rating') or 0)
        except ValueError:
            rating = 0

        if rating < 1 or rating > 5:
            flash('Rating must be between 1 and 5', 'error')
            return redirect(url_for('feedbacks'))

        feedback = Feedback(
            title=request.form.get('title'),
            description=request.form.get('description'),
            rating=rating,
            user_id=user.id,
            floor=user.floor,
        )
        db.session.add(feedback)
        db.session.commit()
        flash('Feedback submitted successfully. Pending approval.', 'success')
        return redirect(url_for('feedbacks'))

    floor = _get_active_floor(user)
    if user.role == 'admin':
        visible_feedbacks = Feedback.query.filter_by(floor=floor).order_by(Feedback.created_at.desc()).all()
    elif user.role == 'pantryHead':
        visible_feedbacks = Feedback.query.filter_by(floor=user.floor).order_by(Feedback.created_at.desc()).all()
    else:
        visible_feedbacks = (
            Feedback.query.filter_by(floor=user.floor, is_approved=True)
            .order_by(Feedback.created_at.desc())
            .all()
        )

    return render_template('feedbacks.html', feedbacks=visible_feedbacks, current_user=user)


@app.route('/feedbacks/<int:feedback_id>/status', methods=['POST'])
def update_feedback_status(feedback_id):
    user = _require_user()
    if not user:
        return ('', 401)

    if user.role not in {'admin', 'pantryHead'}:
        return ('', 403)

    feedback = Feedback.query.get(feedback_id)
    if not feedback:
        return ('', 404)

    if user.role == 'pantryHead' and feedback.floor != user.floor:
        return ('', 403)

    payload = request.get_json(silent=True) or {}
    new_status = (payload.get('status') or request.form.get('status') or '').strip().lower()
    if new_status == 'accepted':
        new_status = 'approved'

    allowed = {'pending', 'approved'}
    if new_status not in allowed:
        return jsonify({"error": "invalid_status", "allowed": sorted(allowed)}), 400

    feedback.is_approved = (new_status == 'approved')
    db.session.commit()
    return ('', 204)


@app.route('/feedbacks/<int:feedback_id>/delete', methods=['POST'])
def delete_feedback(feedback_id):
    user = _require_user()
    if not user:
        return ('', 401)

    if user.role not in {'admin', 'pantryHead'}:
        return ('', 403)

    feedback = Feedback.query.get(feedback_id)
    if not feedback:
        return ('', 404)

    if user.role == 'pantryHead' and feedback.floor != user.floor:
        return ('', 403)

    db.session.delete(feedback)
    db.session.commit()
    return ('', 204)


@app.route('/requests', methods=['GET', 'POST'])
def requests():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Create a new request
        start_date_val = request.form.get('start_date') or None
        end_date_val = request.form.get('end_date') or None

        start_date_obj = None
        end_date_obj = None
        try:
            if start_date_val:
                start_date_obj = datetime.strptime(start_date_val, '%Y-%m-%d').date()
            if end_date_val:
                end_date_obj = datetime.strptime(end_date_val, '%Y-%m-%d').date()
        except Exception:
            flash('Invalid date(s) for request', 'error')
            return redirect(url_for('requests'))

        new_req = Request(
            title=request.form.get('title'),
            description=request.form.get('description'),
            request_type=request.form.get('request_type'),
            start_date=start_date_obj,
            end_date=end_date_obj,
            user_id=user.id,
            floor=user.floor,
            status='pending',
        )
        db.session.add(new_req)
        db.session.commit()
        flash('Request submitted successfully', 'success')
        return redirect(url_for('requests'))

    floor = _get_active_floor(user)
    if user.role == 'admin':
        visible_requests = Request.query.filter_by(floor=floor).order_by(Request.created_at.desc()).all()
    elif user.role == 'pantryHead':
        visible_requests = Request.query.filter_by(floor=user.floor).order_by(Request.created_at.desc()).all()
    else:
        visible_requests = (
            Request.query.filter_by(floor=user.floor)
            .filter(or_(Request.status == 'approved', Request.user_id == user.id))
            .order_by(Request.created_at.desc())
            .all()
        )

    return render_template('requests.html', requests=visible_requests, current_user=user)


@app.route('/requests/<int:request_id>/status', methods=['POST'])
def update_request_status(request_id):
    user = _require_user()
    if not user:
        return ('', 401)

    if user.role not in {'admin', 'pantryHead'}:
        return ('', 403)

    req = Request.query.get(request_id)
    if not req:
        return ('', 404)

    if user.role == 'pantryHead' and req.floor != user.floor:
        return ('', 403)

    payload = request.get_json(silent=True) or {}
    new_status = (payload.get('status') or request.form.get('status') or '').strip().lower()
    if new_status == 'accepted':
        new_status = 'approved'

    allowed = {'pending', 'approved', 'rejected'}
    if new_status not in allowed:
        return jsonify({"error": "invalid_status", "allowed": sorted(allowed)}), 400

    req.status = new_status
    req.approved_by_id = user.id if new_status == 'approved' else None
    db.session.commit()
    return ('', 204)


@app.route('/requests/<int:request_id>/delete', methods=['POST'])
def delete_request(request_id):
    user = _require_user()
    if not user:
        return ('', 401)

    if user.role not in {'admin', 'pantryHead'}:
        return ('', 403)

    req = Request.query.get(request_id)
    if not req:
        return ('', 404)

    if user.role == 'pantryHead' and req.floor != user.floor:
        return ('', 403)

    db.session.delete(req)
    db.session.commit()
    return ('', 204)


@app.route('/procurement', methods=['GET', 'POST'])
def procurement():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    floor = _get_active_floor(user)
    floor_users = User.query.filter_by(floor=floor).all()

    if request.method == 'POST':
        if user.role not in ['admin', 'pantryHead']:
            abort(403)

        assigned_to_id = request.form.get('assigned_to_id') or None
        if assigned_to_id:
            try:
                assigned_to_id = int(assigned_to_id)
            except ValueError:
                assigned_to_id = None

        if assigned_to_id and not User.query.filter_by(id=assigned_to_id, floor=floor).first():
            flash('Assigned user must be on your floor', 'error')
            assigned_to_id = None

        item = ProcurementItem(
            item_name=request.form.get('item_name'),
            quantity=request.form.get('quantity'),
            category=request.form.get('category'),
            priority=request.form.get('priority') or 'medium',
            assigned_to_id=assigned_to_id,
            created_by_id=user.id,
            floor=floor,
        )
        db.session.add(item)
        db.session.commit()
        flash('Procurement item added successfully', 'success')
        return redirect(url_for('procurement'))

    procurement_items = ProcurementItem.query.filter_by(floor=floor).order_by(ProcurementItem.created_at.desc()).all()
    return render_template(
        'procurement.html',
        procurement_items=procurement_items,
        floor_users=floor_users,
        current_user=user,
    )


@app.route('/procurement/complete/<int:item_id>', methods=['POST'])
def complete_procurement_item(item_id):
    user = _require_user()
    if not user:
        return ('', 401)

    if user.role not in ['admin', 'pantryHead']:
        return ('', 403)

    item = ProcurementItem.query.get(item_id)
    if not item:
        return ('', 404)
    if user.role != 'admin' and item.floor != user.floor:
        return ('', 404)

    item.status = 'completed'
    db.session.commit()
    return ('', 204)
