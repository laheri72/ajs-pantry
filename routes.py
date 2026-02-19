from flask import render_template, request, redirect, url_for, session, flash, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, db
from models import User, Dish, Menu, Expense, TeaTask, Suggestion, Feedback, Request, ProcurementItem, Team, TeamMember, Budget, FloorLendBorrow, SpecialEvent, SuggestionVote
from datetime import datetime, date, timedelta
import logging
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError


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
    stars_since_dt = datetime.utcnow() - timedelta(days=7)
    
    # Stats and restricted data
    is_privileged = user.role in ['admin', 'pantryHead']
    pending_lend_borrow_count = 0
    weekly_expenses = 0

    if is_privileged:
        # Total spent: Legacy Expenses + Completed Procurement Costs
        total_spent_proc = db.session.query(func.sum(ProcurementItem.actual_cost)).filter(
            ProcurementItem.floor == floor, 
            ProcurementItem.status == 'completed'
        ).scalar() or 0
        total_spent_legacy = db.session.query(func.sum(Expense.amount)).filter(Expense.floor == floor).scalar() or 0
        weekly_expenses = float(total_spent_proc) + float(total_spent_legacy)

        # Pending Lend/Borrow for this floor (either as lender or borrower)
        pending_lend_borrow_count = FloorLendBorrow.query.filter(
            or_(FloorLendBorrow.lender_floor == floor, FloorLendBorrow.borrower_floor == floor),
            FloorLendBorrow.status == 'pending'
        ).count()

    stats = {
        'user_count': User.query.filter_by(floor=floor).count(),
        'pending_requests': Request.query.filter_by(floor=floor, status='pending').count(),
        'weekly_expenses': weekly_expenses,
        'stars_7d': int(
            (
                db.session.query(func.coalesce(func.sum(Feedback.rating), 0))
                .filter(Feedback.floor == floor, Feedback.created_at >= stars_since_dt, Feedback.menu_id.isnot(None))
                .scalar()
            )
            or 0
        ),
    }

    upcoming_dish = (
        Menu.query.filter_by(floor=floor)
        .filter(Menu.date >= today)
        .order_by(Menu.date.asc())
        .first()
    )

    top_team_row = (
        db.session.query(Menu.assigned_team_id.label('team_id'), func.sum(Feedback.rating).label('stars'))
        .join(Feedback, Feedback.menu_id == Menu.id)
        .filter(Menu.floor == floor, Feedback.created_at >= stars_since_dt, Menu.assigned_team_id.isnot(None))
        .group_by(Menu.assigned_team_id)
        .order_by(func.sum(Feedback.rating).desc())
        .first()
    )
    if top_team_row and top_team_row.team_id:
        t = Team.query.get(top_team_row.team_id)
        stats['top_team_7d'] = f"{(t.icon or '').strip()} {(t.name or '').strip()}".strip() if t else None
    else:
        stats['top_team_7d'] = None

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
        upcoming_dish=upcoming_dish,
        pending_lend_borrow_count=pending_lend_borrow_count,
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

    return redirect(url_for('dashboard'))


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

    leaderboard_since = datetime.utcnow() - timedelta(days=30)

    team_leaderboard = []
    team_rows = (
        db.session.query(
            Team.id.label('team_id'),
            Team.name.label('team_name'),
            Team.icon.label('team_icon'),
            func.coalesce(func.sum(Feedback.rating), 0).label('stars'),
            func.count(Feedback.id).label('ratings_count'),
            func.coalesce(func.avg(Feedback.rating), 0).label('avg_rating'),
        )
        .join(Menu, Menu.assigned_team_id == Team.id)
        .join(Feedback, Feedback.menu_id == Menu.id)
        .filter(Team.floor == floor, Feedback.created_at >= leaderboard_since)
        .group_by(Team.id, Team.name, Team.icon)
        .order_by(func.sum(Feedback.rating).desc(), func.count(Feedback.id).desc(), Team.name.asc())
        .limit(10)
        .all()
    )
    for r in team_rows:
        team_leaderboard.append(
            {
                "id": r.team_id,
                "name": r.team_name,
                "icon": r.team_icon,
                "stars": int(r.stars or 0),
                "ratings_count": int(r.ratings_count or 0),
                "avg_rating": float(r.avg_rating or 0),
            }
        )

    individual_leaderboard = []
    individual_rows = (
        db.session.query(
            User.id.label('user_id'),
            User.full_name.label('full_name'),
            User.username.label('username'),
            User.email.label('email'),
            func.coalesce(func.sum(Feedback.rating), 0).label('stars'),
            func.count(Feedback.id).label('ratings_count'),
            func.coalesce(func.avg(Feedback.rating), 0).label('avg_rating'),
        )
        .join(Menu, Menu.assigned_to_id == User.id)
        .join(Feedback, Feedback.menu_id == Menu.id)
        .filter(User.floor == floor, Feedback.created_at >= leaderboard_since)
        .group_by(User.id, User.full_name, User.username, User.email)
        .order_by(func.sum(Feedback.rating).desc(), func.count(Feedback.id).desc())
        .limit(10)
        .all()
    )
    for r in individual_rows:
        label = (r.full_name or r.username or r.email or '').strip()
        individual_leaderboard.append(
            {
                "id": r.user_id,
                "label": label,
                "stars": int(r.stars or 0),
                "ratings_count": int(r.ratings_count or 0),
                "avg_rating": float(r.avg_rating or 0),
            }
        )

    dish_name_expr = func.coalesce(Dish.name, Menu.title)
    dish_leaderboard = []
    dish_rows = (
        db.session.query(
            dish_name_expr.label('dish_name'),
            func.coalesce(func.sum(Feedback.rating), 0).label('stars'),
            func.count(Feedback.id).label('ratings_count'),
            func.coalesce(func.avg(Feedback.rating), 0).label('avg_rating'),
        )
        .join(Menu, Feedback.menu_id == Menu.id)
        .outerjoin(Dish, Menu.dish_id == Dish.id)
        .filter(Menu.floor == floor, Feedback.created_at >= leaderboard_since)
        .group_by(dish_name_expr)
        .order_by(func.sum(Feedback.rating).desc(), dish_name_expr.asc())
        .limit(10)
        .all()
    )
    for r in dish_rows:
        name = (r.dish_name or '').strip()
        if not name:
            continue
        dish_leaderboard.append(
            {
                "name": name,
                "stars": int(r.stars or 0),
                "ratings_count": int(r.ratings_count or 0),
                "avg_rating": float(r.avg_rating or 0),
            }
        )

    dish_champion_rows = (
        db.session.query(
            dish_name_expr.label('dish_name'),
            Team.id.label('team_id'),
            Team.name.label('team_name'),
            Team.icon.label('team_icon'),
            func.coalesce(func.sum(Feedback.rating), 0).label('stars'),
        )
        .join(Menu, Feedback.menu_id == Menu.id)
        .outerjoin(Dish, Menu.dish_id == Dish.id)
        .join(Team, Menu.assigned_team_id == Team.id)
        .filter(Menu.floor == floor, Feedback.created_at >= leaderboard_since)
        .group_by(dish_name_expr, Team.id, Team.name, Team.icon)
        .all()
    )
    champions_by_dish = {}
    for r in dish_champion_rows:
        dish_name = (r.dish_name or '').strip()
        if not dish_name:
            continue
        stars = int(r.stars or 0)
        current = champions_by_dish.get(dish_name)
        if not current or stars > current["stars"]:
            champions_by_dish[dish_name] = {
                "dish_name": dish_name,
                "team_id": r.team_id,
                "team_name": r.team_name,
                "team_icon": r.team_icon,
                "stars": stars,
            }
    dish_champions = list(champions_by_dish.values())
    dish_champions.sort(key=lambda x: (-x["stars"], (x["dish_name"] or "").lower()))
    dish_champions = dish_champions[:10]

    return render_template(
        'people.html',
        users=users,
        teams=teams,
        members_by_team_id=members_by_team_id,
        my_teams=my_teams,
        leaderboard_since=leaderboard_since,
        team_leaderboard=team_leaderboard,
        individual_leaderboard=individual_leaderboard,
        dish_leaderboard=dish_leaderboard,
        dish_champions=dish_champions,
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
    floor_special_events = SpecialEvent.query.filter_by(floor=floor).all()

    menus = [
        {
            "id": m.id,
            "type": "menu",
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
            "type": "tea",
            "title": "Tea Duty",
            "date": t.date.isoformat() if t.date else None,
            "status": t.status,
            "assigned_to_id": t.assigned_to_id,
            "assigned_to_name": (t.assigned_to.full_name or t.assigned_to.username or t.assigned_to.email) if t.assigned_to else None,
        }
        for t in floor_tea_tasks
    ]

    special_events = [
        {
            "id": s.id,
            "type": "special",
            "title": s.title,
            "description": s.description,
            "date": s.date.isoformat() if s.date else None,
            "created_by": (s.created_by.full_name or s.created_by.username) if s.created_by else "System"
        }
        for s in floor_special_events
    ]

    return render_template('calendar.html', menus=menus, tea_tasks=tea_tasks, special_events=special_events, current_user=user)


@app.route('/special-events', methods=['POST'])
def create_special_event():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)

    floor = _get_active_floor(user)
    try:
        title = request.form.get('title')
        description = request.form.get('description')
        event_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
    except Exception:
        flash('Invalid event data', 'error')
        return redirect(url_for('calendar'))

    new_event = SpecialEvent(
        title=title,
        description=description,
        date=event_date,
        floor=floor,
        created_by_id=user.id
    )
    db.session.add(new_event)
    db.session.commit()
    flash('Special event added to calendar.', 'success')
    return redirect(url_for('calendar'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    user = _require_user()
    if not user or user.role != 'admin':
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        
        if action == 'add_user':
            role = (request.form.get('role') or '').strip()
            if role != 'member':
                flash('Only members can be created from the admin panel now.', 'error')
                return redirect(url_for('admin'))

            try:
                floor = int(request.form.get('floor', user.floor) or user.floor or FLOOR_MIN)
            except Exception:
                floor = user.floor or FLOOR_MIN

            if floor < FLOOR_MIN or floor > FLOOR_MAX:
                flash('Invalid floor selected', 'error')
                return redirect(url_for('admin'))

            tr_number = (request.form.get('tr_number') or '').strip()
            if not tr_number:
                flash('TR Number is required', 'error')
                return redirect(url_for('admin'))

            email = f"{tr_number}@jameasaifiyah.edu"
            if User.query.filter(or_(User.email == email, User.tr_number == tr_number)).first():
                flash('A user with this TR number/email already exists', 'error')
                return redirect(url_for('admin'))
            
            new_user = User()
            new_user.role = role
            new_user.floor = floor
            new_user.password_hash = generate_password_hash('maskan1447')
            new_user.is_first_login = True
            
            new_user.tr_number = tr_number
            new_user.email = email
                
            db.session.add(new_user)
            db.session.commit()
            flash('Member added successfully', 'success')
            return redirect(url_for('admin'))

        if action == 'assign_role':
            role = (request.form.get('role') or '').strip()
            if role not in {'pantryHead', 'teaManager'}:
                flash('Invalid role selected', 'error')
                return redirect(url_for('admin'))

            try:
                floor = int(request.form.get('floor') or '')
            except Exception:
                flash('Invalid floor selected', 'error')
                return redirect(url_for('admin'))

            if floor < FLOOR_MIN or floor > FLOOR_MAX:
                flash('Invalid floor selected', 'error')
                return redirect(url_for('admin'))

            try:
                target_user_id = int(request.form.get('user_id') or '')
            except Exception:
                flash('Invalid user selected', 'error')
                return redirect(url_for('admin'))

            target = User.query.get(target_user_id)
            if not target:
                flash('User not found', 'error')
                return redirect(url_for('admin'))

            if target.role == 'admin':
                flash('Admin users cannot be reassigned.', 'error')
                return redirect(url_for('admin'))

            if target.floor != floor:
                flash('Selected user must be on the selected floor', 'error')
                return redirect(url_for('admin'))

            if target.role != 'member':
                flash('Only members can be assigned to staff roles.', 'error')
                return redirect(url_for('admin'))

            target.role = role
            db.session.commit()
            flash('Role assigned successfully', 'success')
            return redirect(url_for('admin'))

        if action == 'delete_user':
            try:
                target_user_id = int(request.form.get('user_id') or '')
            except Exception:
                flash('Invalid user selected', 'error')
                return redirect(url_for('admin'))

            target = User.query.get(target_user_id)
            if not target:
                flash('User not found', 'error')
                return redirect(url_for('admin'))

            if target.id == user.id:
                flash('You cannot delete your own account.', 'error')
                return redirect(url_for('admin'))

            if target.role == 'admin':
                flash('Admin users cannot be deleted from this panel.', 'error')
                return redirect(url_for('admin'))

            # Remove / detach references to avoid FK constraint failures.
            TeamMember.query.filter_by(user_id=target.id).delete(synchronize_session=False)

            Menu.query.filter_by(assigned_to_id=target.id).update({Menu.assigned_to_id: None}, synchronize_session=False)
            Menu.query.filter_by(created_by_id=target.id).update({Menu.created_by_id: None}, synchronize_session=False)

            TeaTask.query.filter_by(assigned_to_id=target.id).update({TeaTask.assigned_to_id: None}, synchronize_session=False)
            TeaTask.query.filter_by(created_by_id=target.id).update({TeaTask.created_by_id: None}, synchronize_session=False)

            ProcurementItem.query.filter_by(assigned_to_id=target.id).update({ProcurementItem.assigned_to_id: None}, synchronize_session=False)
            ProcurementItem.query.filter_by(created_by_id=target.id).update({ProcurementItem.created_by_id: None}, synchronize_session=False)

            Request.query.filter_by(user_id=target.id).update({Request.user_id: None}, synchronize_session=False)
            Request.query.filter_by(approved_by_id=target.id).update({Request.approved_by_id: None}, synchronize_session=False)

            Expense.query.filter_by(user_id=target.id).update({Expense.user_id: None}, synchronize_session=False)
            Suggestion.query.filter_by(user_id=target.id).update({Suggestion.user_id: None}, synchronize_session=False)
            Feedback.query.filter_by(user_id=target.id).update({Feedback.user_id: None}, synchronize_session=False)

            Team.query.filter_by(created_by_id=target.id).update({Team.created_by_id: None}, synchronize_session=False)

            try:
                db.session.delete(target)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('Cannot delete this user because they are referenced elsewhere.', 'error')
                return redirect(url_for('admin'))

            flash('User deleted successfully', 'success')
            return redirect(url_for('admin'))
            
    all_users = User.query.all()
    return render_template('admin.html', user=user, all_users=all_users, current_user=user)


@app.route('/admin/floor-members', methods=['GET'])
def admin_floor_members():
    user = _require_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    if user.role != 'admin':
        return jsonify({"error": "forbidden"}), 403

    try:
        floor = int(request.args.get('floor') or '')
    except Exception:
        return jsonify({"error": "invalid_floor"}), 400

    if floor < FLOOR_MIN or floor > FLOOR_MAX:
        return jsonify({"error": "invalid_floor"}), 400

    members = (
        User.query.filter_by(floor=floor, role='member')
        .order_by(User.tr_number.asc(), User.full_name.asc(), User.email.asc())
        .all()
    )

    def _label(u):
        name = (u.full_name or u.username or u.email or '').strip()
        tr = (u.tr_number or '-').strip()
        return f"{tr} - {name}".strip(' -')

    return jsonify(
        {
            "floor": floor,
            "members": [
                {
                    "id": u.id,
                    "tr_number": u.tr_number,
                    "name": (u.full_name or u.username or u.email),
                    "label": _label(u),
                }
                for u in members
            ],
        }
    )


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
    dishes = Dish.query.order_by(func.lower(Dish.name).asc()).all()

    if request.method == 'POST' and user.role in ['admin', 'pantryHead']:
        try:
            menu_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        except Exception:
            flash('Invalid menu date', 'error')
            return redirect(url_for('menus'))

        dish = None
        dish_id_raw = (request.form.get('dish_id') or '').strip()
        new_dish_name = (request.form.get('new_dish_name') or '').strip()

        if dish_id_raw:
            try:
                dish_id_val = int(dish_id_raw)
            except Exception:
                dish_id_val = None
            if not dish_id_val:
                flash('Invalid dish selected', 'error')
                return redirect(url_for('menus'))
            dish = Dish.query.get(dish_id_val)
            if not dish:
                flash('Dish not found', 'error')
                return redirect(url_for('menus'))
        elif new_dish_name:
            if len(new_dish_name) > 120:
                flash('Dish name is too long', 'error')
                return redirect(url_for('menus'))
            existing = Dish.query.filter(func.lower(Dish.name) == new_dish_name.lower()).first()
            if existing:
                dish = existing
            else:
                dish = Dish(name=new_dish_name, created_by_id=user.id)
                db.session.add(dish)
                db.session.flush()
        else:
            flash('Please select a dish (or create a new one)', 'error')
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

        menu_title = (dish.name or '').strip() if dish else (request.form.get('title') or '').strip()
        if not menu_title:
            menu_title = 'Menu'

        menu = Menu(
            title=menu_title[:100],
            description=request.form.get('description'),
            date=menu_date,
            meal_type=request.form.get('meal_type'),
            dish_type=request.form.get('dish_type') or 'main',
            dish_id=dish.id if dish else None,
            assigned_to_id=assigned_to_id,
            assigned_team_id=assigned_team_id,
            floor=floor,
            created_by_id=user.id,
        )
        db.session.add(menu)
        db.session.commit()
        flash('Menu added successfully', 'success')

    floor_menus = Menu.query.filter_by(floor=floor).order_by(Menu.date.desc()).all()

    # Prepare Weekly View Data
    today = date.today()
    # Find start of week (Monday)
    start_of_week = today - timedelta(days=today.weekday())
    
    weekly_days = []
    for i in range(7):
        day_date = start_of_week + timedelta(days=i)
        day_menus = [m for m in floor_menus if m.date == day_date]
        weekly_days.append({
            "date": day_date,
            "is_today": day_date == today,
            "menus": day_menus
        })

    return render_template(
        'menus.html', 
        menus=floor_menus, 
        weekly_days=weekly_days,
        floor_users=floor_users, 
        floor_teams=floor_teams, 
        dishes=dishes, 
        current_user=user,
        today=today
    )


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

    _require_staff_for_floor(user)

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
    
    # Permission check: Read-only for members, manage for PH/Admin
    is_manager = user.role in ['admin', 'pantryHead']

    # 1. Handle actual_cost updates for completed procurements
    if request.method == 'POST' and is_manager:
        action = request.form.get('action')
        if action == 'record_cost':
            try:
                item_id = int(request.form.get('item_id') or 0)
                cost = float(request.form.get('actual_cost') or 0)
            except ValueError:
                flash('Invalid cost value', 'error')
                return redirect(url_for('expenses'))

            item = ProcurementItem.query.get(item_id)
            if item and (user.role == 'admin' or item.floor == user.floor):
                if item.status != 'completed':
                    flash('Costs can only be recorded for completed items.', 'error')
                else:
                    item.actual_cost = cost
                    item.expense_recorded_at = datetime.utcnow()
                    db.session.commit()
                    flash(f'Cost for {item.item_name} recorded.', 'success')
            return redirect(url_for('expenses'))

    # 2. Financial Calculations
    # Total Budget Allocated
    total_budget = db.session.query(func.sum(Budget.amount_allocated)).filter(Budget.floor == floor).scalar() or 0
    
    # Total Spent (Current System: Completed Procurements with Costs)
    total_spent_procurement = db.session.query(func.sum(ProcurementItem.actual_cost)).filter(
        ProcurementItem.floor == floor, 
        ProcurementItem.status == 'completed'
    ).scalar() or 0
    
    # Legacy Expenses (Optional: include in total spent if desired)
    total_spent_legacy = db.session.query(func.sum(Expense.amount)).filter(Expense.floor == floor).scalar() or 0
    
    total_spent = float(total_spent_procurement) + float(total_spent_legacy)
    remaining_balance = float(total_budget) - total_spent

    # 3. Data for Ledger
    # Get completed procurements for this floor
    completed_procurements = ProcurementItem.query.filter_by(floor=floor, status='completed').order_by(ProcurementItem.created_at.desc()).all()
    
    # Get budget history
    budgets = Budget.query.filter_by(floor=floor).order_by(Budget.start_date.desc()).all()
    
    # Legacy expenses for reference
    legacy_expenses = Expense.query.filter_by(floor=floor).order_by(Expense.date.desc()).all()

    return render_template(
        'expenses.html',
        total_budget=total_budget,
        total_spent=total_spent,
        remaining_balance=remaining_balance,
        completed_procurements=completed_procurements,
        budgets=budgets,
        legacy_expenses=legacy_expenses,
        is_manager=is_manager,
        today=date.today(),
        current_user=user
    )


@app.route('/budgets/add', methods=['POST'])
def add_budget():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)

    floor = _get_active_floor(user)
    try:
        amount = float(request.form.get('amount') or 0)
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date_raw = request.form.get('end_date')
        end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date() if end_date_raw else None
    except Exception:
        flash('Invalid budget data', 'error')
        return redirect(url_for('expenses'))

    budget = Budget(
        floor=floor,
        amount_allocated=amount,
        allocation_type=request.form.get('allocation_type'),
        start_date=start_date,
        end_date=end_date,
        notes=request.form.get('notes')
    )
    db.session.add(budget)
    db.session.commit()
    flash('Budget allocation added.', 'success')
    return redirect(url_for('expenses'))


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
        flash('Suggestion submitted successfully.', 'success')
        return redirect(url_for('suggestions'))

    floor = _get_active_floor(user)
    
    # Base query for suggestions on this floor
    query = Suggestion.query.filter_by(floor=floor)
    
    # Calculate vote counts and join for sorting
    suggestions_with_votes = (
        db.session.query(Suggestion, func.count(SuggestionVote.id).label('vote_count'))
        .outerjoin(SuggestionVote)
        .filter(Suggestion.floor == floor)
        .group_by(Suggestion.id)
        .order_by(func.count(SuggestionVote.id).desc(), Suggestion.created_at.desc())
        .all()
    )

    # Get the IDs of suggestions the current user has voted for
    user_voted_ids = {v.suggestion_id for v in SuggestionVote.query.filter_by(user_id=user.id).all()}

    return render_template(
        'suggestions.html', 
        suggestions_with_votes=suggestions_with_votes, 
        user_voted_ids=user_voted_ids,
        current_user=user
    )


@app.route('/suggestions/<int:suggestion_id>/vote', methods=['POST'])
def vote_suggestion(suggestion_id):
    user = _require_user()
    if not user:
        return ('', 401)

    suggestion = Suggestion.query.get_or_404(suggestion_id)
    if suggestion.floor != user.floor:
        abort(403)

    existing_vote = SuggestionVote.query.filter_by(suggestion_id=suggestion_id, user_id=user.id).first()
    
    if existing_vote:
        # If user already voted, remove the vote (toggle)
        db.session.delete(existing_vote)
        db.session.commit()
        return jsonify({"voted": False, "votes": len(suggestion.votes)})
    else:
        # Add new vote
        new_vote = SuggestionVote(suggestion_id=suggestion_id, user_id=user.id)
        db.session.add(new_vote)
        db.session.commit()
        return jsonify({"voted": True, "votes": len(suggestion.votes)})


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
        floor = _get_active_floor(user)
        menu_id_raw = (request.form.get('menu_id') or '').strip()
        if not menu_id_raw:
            flash('Please select a menu to evaluate', 'error')
            return redirect(url_for('feedbacks'))

        try:
            menu_id_val = int(menu_id_raw)
        except Exception:
            menu_id_val = None

        if not menu_id_val:
            flash('Invalid menu selected', 'error')
            return redirect(url_for('feedbacks'))

        menu = Menu.query.get(menu_id_val)
        if not menu or menu.floor != floor:
            flash('Menu not found on this floor', 'error')
            return redirect(url_for('feedbacks'))

        if menu.date and menu.date > date.today():
            flash('You can only evaluate menus from today or earlier', 'error')
            return redirect(url_for('feedbacks'))

        if not (menu.assigned_team_id or menu.assigned_to_id):
            flash('This menu is not assigned to a team/person yet', 'error')
            return redirect(url_for('feedbacks'))

        try:
            rating = int(request.form.get('rating') or 0)
        except ValueError:
            rating = 0

        if rating < 1 or rating > 5:
            flash('Rating must be between 1 and 5', 'error')
            return redirect(url_for('feedbacks'))

        description = (request.form.get('description') or '').strip()
        if not description:
            flash('Please add a short comment', 'error')
            return redirect(url_for('feedbacks'))

        dish_label = (
            (menu.dish.name if getattr(menu, "dish", None) else None)
            or (menu.title or '').strip()
            or 'Menu'
        )
        title = dish_label[:100]

        existing = Feedback.query.filter_by(menu_id=menu.id, user_id=user.id).first()
        if existing:
            existing.title = title
            existing.description = description
            existing.rating = rating
            existing.floor = menu.floor
        else:
            feedback = Feedback(
                title=title,
                description=description,
                rating=rating,
                menu_id=menu.id,
                user_id=user.id,
                floor=menu.floor,
            )
            db.session.add(feedback)

        db.session.commit()
        flash('Evaluation saved successfully.', 'success')
        return redirect(url_for('feedbacks'))

    floor = _get_active_floor(user)
    visible_feedbacks = Feedback.query.filter_by(floor=floor).order_by(Feedback.created_at.desc()).all()

    today = date.today()
    menu_window_start = today - timedelta(days=14)
    menu_options = (
        Menu.query.filter_by(floor=floor)
        .filter(Menu.date >= menu_window_start, Menu.date <= today)
        .filter(or_(Menu.assigned_team_id.isnot(None), Menu.assigned_to_id.isnot(None)))
        .order_by(Menu.date.desc())
        .limit(80)
        .all()
    )

    rated_menu_ids = {
        f.menu_id for f in Feedback.query.filter_by(user_id=user.id).filter(Feedback.menu_id.isnot(None)).all()
    }

    return render_template('feedbacks.html', feedbacks=visible_feedbacks, menu_options=menu_options, rated_menu_ids=rated_menu_ids, current_user=user)


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

        category = (request.form.get('category') or 'other').strip() or 'other'
        priority = (request.form.get('priority') or 'medium').strip() or 'medium'

        item_names = request.form.getlist('item_name[]')
        quantities = request.form.getlist('quantity[]')
        if item_names or quantities:
            max_len = max(len(item_names), len(quantities))
            items_to_add = []

            for idx in range(max_len):
                name = (item_names[idx] if idx < len(item_names) else '').strip()
                qty = (quantities[idx] if idx < len(quantities) else '').strip()

                if not name and not qty:
                    continue
                if not name or not qty:
                    flash(f'Row {idx + 1}: please provide both item and quantity (or leave the row blank).', 'error')
                    return redirect(url_for('procurement'))

                items_to_add.append(
                    ProcurementItem(
                        item_name=name,
                        quantity=qty,
                        category=category,
                        priority=priority,
                        assigned_to_id=assigned_to_id,
                        created_by_id=user.id,
                        floor=floor,
                    )
                )

            if not items_to_add:
                flash('Please add at least one item.', 'error')
                return redirect(url_for('procurement'))

            db.session.add_all(items_to_add)
            db.session.commit()
            flash(f'Added {len(items_to_add)} procurement items successfully.', 'success')
            return redirect(url_for('procurement'))

        item_name = (request.form.get('item_name') or '').strip()
        quantity = (request.form.get('quantity') or '').strip()
        if not item_name or not quantity:
            flash('Item name and quantity are required.', 'error')
            return redirect(url_for('procurement'))

        item = ProcurementItem(
            item_name=item_name,
            quantity=quantity,
            category=category,
            priority=priority,
            assigned_to_id=assigned_to_id,
            created_by_id=user.id,
            floor=floor,
        )
        db.session.add(item)
        db.session.commit()
        flash('Procurement item added successfully.', 'success')
        return redirect(url_for('procurement'))

    procurement_items = ProcurementItem.query.filter_by(floor=floor).order_by(ProcurementItem.created_at.desc()).all()
    pending_items = [i for i in procurement_items if (i.status or '').strip().lower() != 'completed']
    completed_items = [i for i in procurement_items if (i.status or '').strip().lower() == 'completed']

    priority_rank = {'high': 0, 'medium': 1, 'low': 2}
    pending_items.sort(
        key=lambda i: (
            priority_rank.get((i.priority or '').strip().lower(), 99),
            -(i.created_at.timestamp() if i.created_at else 0),
        )
    )
    completed_items.sort(key=lambda i: -(i.created_at.timestamp() if i.created_at else 0))

    pending_group_map = {}
    for item in pending_items:
        key = item.assigned_to_id or 0
        pending_group_map.setdefault(key, []).append(item)

    pending_groups = []
    for key, items in pending_group_map.items():
        is_unassigned = key == 0
        label = 'Unassigned' if is_unassigned else (_display_name_for(items[0].assigned_to) or f'User #{key}')
        pending_groups.append(
            {
                "assigned_to_id": None if is_unassigned else key,
                "label": label,
                "is_unassigned": is_unassigned,
                "items": items,
            }
        )

    pending_groups.sort(key=lambda g: (0 if g["is_unassigned"] else 1, (g["label"] or "").lower()))

    return render_template(
        'procurement.html',
        pending_items=pending_items,
        pending_groups=pending_groups,
        completed_items=completed_items,
        floor_users=floor_users,
        current_user=user,
    )


@app.route('/procurement/complete/<int:item_id>', methods=['POST'])
def complete_procurement_item(item_id):
    user = _require_user()
    if not user:
        if request.accept_mimetypes.accept_html:
            return redirect(url_for('login'))
        return ('', 401)

    if user.role not in ['admin', 'pantryHead']:
        if request.accept_mimetypes.accept_html:
            abort(403)
        return ('', 403)

    item = ProcurementItem.query.get(item_id)
    if not item:
        if request.accept_mimetypes.accept_html:
            abort(404)
        return ('', 404)
    if user.role != 'admin' and item.floor != user.floor:
        if request.accept_mimetypes.accept_html:
            abort(404)
        return ('', 404)

    item.status = 'completed'
    db.session.commit()
    if request.accept_mimetypes.accept_html:
        flash('Marked as completed', 'success')
        return redirect(url_for('procurement'))
    return ('', 204)


@app.route('/procurement/suggest', methods=['GET'])
def procurement_suggest():
    user = _require_user()
    if not user:
        return ('', 401)

    floor = _get_active_floor(user)
    q = (request.args.get('q') or '').strip()

    base_query = ProcurementItem.query.filter_by(floor=floor)
    if q:
        q_lower = q.lower()
        base_query = base_query.filter(func.lower(ProcurementItem.item_name).like(f"%{q_lower}%"))

    recent_rows = base_query.order_by(ProcurementItem.created_at.desc()).limit(250).all()

    seen = set()
    out = []
    for row in recent_rows:
        name = (row.item_name or '').strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "last_quantity": (row.quantity or '').strip()})
        if len(out) >= 30:
            break

    return jsonify({"items": out})


@app.route('/procurement/suggest-qty', methods=['GET'])
def procurement_suggest_qty():
    user = _require_user()
    if not user:
        return ('', 401)

    floor = _get_active_floor(user)
    item = (request.args.get('item') or '').strip()
    if not item:
        return jsonify({"quantities": [], "last_quantity": ""})

    item_lower = item.lower()
    rows = (
        ProcurementItem.query.filter_by(floor=floor)
        .filter(func.lower(ProcurementItem.item_name) == item_lower)
        .order_by(ProcurementItem.created_at.desc())
        .limit(80)
        .all()
    )

    quantities = []
    seen = set()
    last_quantity = ""
    for r in rows:
        q = (r.quantity or '').strip()
        if not last_quantity and q:
            last_quantity = q
        if not q:
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        quantities.append(q)
        if len(quantities) >= 10:
            break

    return jsonify({"quantities": quantities, "last_quantity": last_quantity})


@app.route('/lend-borrow')
def lend_borrow():
    user = _require_user()
    if not user:
        return redirect(url_for('login'))

    if user.role not in ['admin', 'pantryHead']:
        abort(403)

    floor = _get_active_floor(user)
    
    # Permission: Admin sees all, Pantry Head sees floor-involved
    if user.role == 'admin':
        pending = FloorLendBorrow.query.filter_by(status='pending').order_by(FloorLendBorrow.created_at.desc()).all()
        returned = FloorLendBorrow.query.filter_by(status='returned').order_by(FloorLendBorrow.borrower_marked_at.desc()).all()
        completed = FloorLendBorrow.query.filter_by(status='completed').order_by(FloorLendBorrow.lender_verified_at.desc()).limit(100).all()
    else:
        # User role pantryHead or others who have access
        # Only lender_floor or borrower_floor matches current active floor
        query = FloorLendBorrow.query.filter(or_(FloorLendBorrow.lender_floor == floor, FloorLendBorrow.borrower_floor == floor))
        
        pending = query.filter(FloorLendBorrow.status == 'pending').order_by(FloorLendBorrow.created_at.desc()).all()
        returned = query.filter(FloorLendBorrow.status == 'returned').order_by(FloorLendBorrow.borrower_marked_at.desc()).all()
        completed = query.filter(FloorLendBorrow.status == 'completed').order_by(FloorLendBorrow.lender_verified_at.desc()).limit(50).all()

    return render_template(
        'lend_borrow.html',
        pending=pending,
        returned=returned,
        completed=completed,
        floor_options=_get_floor_options_for_admin(),
        current_user=user,
        active_floor=floor
    )


@app.route('/lend-borrow/create', methods=['POST'])
def create_lend_borrow():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)

    floor = _get_active_floor(user)
    borrower_floor = int(request.form.get('borrower_floor'))
    
    if borrower_floor == floor:
        flash('You cannot lend to your own floor.', 'error')
        return redirect(url_for('lend_borrow'))

    new_record = FloorLendBorrow(
        lender_floor=floor,
        borrower_floor=borrower_floor,
        item_name=request.form.get('item_name'),
        quantity=request.form.get('quantity'),
        item_type=request.form.get('item_type'),
        notes=request.form.get('notes'),
        created_by_id=user.id,
        status='pending'
    )
    db.session.add(new_record)
    db.session.commit()
    flash('Lend request created.', 'success')
    return redirect(url_for('lend_borrow'))


@app.route('/lend-borrow/<int:record_id>/mark-returned', methods=['POST'])
def mark_returned(record_id):
    user = _require_user()
    if not user:
        abort(401)

    if user.role not in ['admin', 'pantryHead']:
        abort(403)

    record = FloorLendBorrow.query.get_or_404(record_id)
    floor = _get_active_floor(user)

    # Only borrower can mark as returned
    if user.role != 'admin' and record.borrower_floor != floor:
        abort(403)

    if record.status != 'pending':
        flash('Only pending items can be marked as returned.', 'error')
        return redirect(url_for('lend_borrow'))

    record.status = 'returned'
    record.borrower_marked_at = datetime.utcnow()
    db.session.commit()
    flash('Item marked as returned. Lender must now verify.', 'success')
    return redirect(url_for('lend_borrow'))


@app.route('/lend-borrow/<int:record_id>/verify', methods=['POST'])
def verify_return(record_id):
    user = _require_user()
    if not user:
        abort(401)

    if user.role not in ['admin', 'pantryHead']:
        abort(403)

    record = FloorLendBorrow.query.get_or_404(record_id)
    floor = _get_active_floor(user)
    action = request.form.get('action')

    # Only lender can verify
    if user.role != 'admin' and record.lender_floor != floor:
        abort(403)

    if record.status != 'returned':
        flash('Only returned items can be verified.', 'error')
        return redirect(url_for('lend_borrow'))

    if action == 'confirm':
        record.status = 'completed'
        record.lender_verified_at = datetime.utcnow()
        flash('Return verified and completed.', 'success')
    elif action == 'reject':
        record.status = 'pending'
        record.borrower_marked_at = None
        flash('Return rejected. Transaction reverted to pending.', 'warning')
    
    db.session.commit()
    return redirect(url_for('lend_borrow'))
