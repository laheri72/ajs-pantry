from flask import render_template, request, redirect, url_for, session, flash, abort, jsonify
from app import db
from models import User, Dish, Menu, Feedback, Request, ProcurementItem, Team, TeamMember, TeaTask, FloorLendBorrow, SpecialEvent, Announcement, Suggestion, SuggestionVote, Expense
from datetime import datetime, date, timedelta
from sqlalchemy import or_, func
from . import pantry_bp
from ..utils import (
    _require_user,
    _get_active_floor,
    _require_staff_for_floor,
    _display_name_for,
    FLOOR_MIN,
    FLOOR_MAX
)

@pantry_bp.route('/dashboard')
def dashboard():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

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

    # Notifications logic
    notifications = []
    
    # 1. Announcements (last 7 days)
    announcement_since = datetime.utcnow() - timedelta(days=7)
    recent_announcements = Announcement.query.filter(
        Announcement.floor == floor,
        Announcement.created_at >= announcement_since,
        Announcement.is_archived == False
    ).order_by(Announcement.created_at.desc()).all()
    
    for ann in recent_announcements:
        notifications.append({
            'type': 'announcement',
            'icon': 'fas fa-bullhorn',
            'title': ann.title,
            'content': ann.content,
            'time': ann.created_at,
            'category': 'Announcement'
        })
    
    # 2. Upcoming Assignments
    for m in upcoming_menu_assignments:
        notifications.append({
            'type': 'assignment',
            'icon': 'fas fa-utensils',
            'title': f"Menu: {m.title}",
            'content': f"You have a menu assignment on {m.date.strftime('%Y-%m-%d')}",
            'time': datetime.combine(m.date, datetime.min.time()),
            'category': 'Menu Assignment'
        })
    
    for t in upcoming_tea_duties:
        notifications.append({
            'type': 'assignment',
            'icon': 'fas fa-coffee',
            'title': "Tea Duty",
            'content': f"Scheduled for {t.date.strftime('%Y-%m-%d')}",
            'time': datetime.combine(t.date, datetime.min.time()),
            'category': 'Tea Duty'
        })

    for p in upcoming_procurement_assignments:
        notifications.append({
            'type': 'assignment',
            'icon': 'fas fa-shopping-cart',
            'title': f"Procurement: {p.item_name}",
            'content': f"Quantity: {p.quantity} - {p.status.title()}",
            'time': p.created_at,
            'category': 'Procurement'
        })

    # 3. Special Events (upcoming 7 days)
    event_until = today + timedelta(days=7)
    upcoming_events = SpecialEvent.query.filter(
        SpecialEvent.floor == floor,
        SpecialEvent.date >= today,
        SpecialEvent.date <= event_until
    ).order_by(SpecialEvent.date.asc()).all()
    
    for event in upcoming_events:
        notifications.append({
            'type': 'event',
            'icon': 'fas fa-calendar-day',
            'title': event.title,
            'content': event.description or "Special floor event scheduled.",
            'time': datetime.combine(event.date, datetime.min.time()),
            'category': 'Special Event'
        })

    # Sort notifications by time (newest first for announcements, soonest first for assignments if we mixed them)
    # Actually, let's keep it simple: Announcements first, then assignments
    notifications.sort(key=lambda x: x['time'], reverse=True)
    
    return render_template(
        'dashboard.html',
        user=user,
        stats=stats,
        upcoming_dish=upcoming_dish,
        pending_lend_borrow_count=pending_lend_borrow_count,
        notifications=notifications,
        upcoming_tea_duties=upcoming_tea_duties,
        upcoming_procurement_assignments=upcoming_procurement_assignments,
        upcoming_menu_assignments=upcoming_menu_assignments,
        upcoming_events=upcoming_events,
        today=today,
        upcoming_until=upcoming_until,
        current_user=user,
    )

@pantry_bp.route('/home')
def home():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    return redirect(url_for('pantry.dashboard'))

@pantry_bp.route('/people')
def people():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

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

@pantry_bp.route('/calendar')
def calendar():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

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

@pantry_bp.route('/special-events', methods=['POST'])
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
        return redirect(url_for('pantry.calendar'))

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
    return redirect(url_for('pantry.calendar'))

@pantry_bp.route('/menus', methods=['GET', 'POST'])
def menus():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    floor = _get_active_floor(user)
    floor_users = User.query.filter_by(floor=floor).all()
    floor_teams = Team.query.filter_by(floor=floor).order_by(Team.name.asc()).all()
    dishes = Dish.query.order_by(func.lower(Dish.name).asc()).all()

    if request.method == 'POST' and user.role in ['admin', 'pantryHead']:
        try:
            menu_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        except Exception:
            flash('Invalid menu date', 'error')
            return redirect(url_for('pantry.menus'))

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
                return redirect(url_for('pantry.menus'))
            dish = Dish.query.get(dish_id_val)
            if not dish:
                flash('Dish not found', 'error')
                return redirect(url_for('pantry.menus'))
        elif new_dish_name:
            if len(new_dish_name) > 120:
                flash('Dish name is too long', 'error')
                return redirect(url_for('pantry.menus'))
            existing = Dish.query.filter(func.lower(Dish.name) == new_dish_name.lower()).first()
            if existing:
                dish = existing
            else:
                dish = Dish(name=new_dish_name, created_by_id=user.id)
                db.session.add(dish)
                db.session.flush()
        else:
            flash('Please select a dish (or create a new one)', 'error')
            return redirect(url_for('pantry.menus'))

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

@pantry_bp.route('/menus/<int:menu_id>/delete', methods=['POST'])
def delete_menu(menu_id):
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

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
    return redirect(url_for('pantry.menus'))

@pantry_bp.route('/suggestions', methods=['GET', 'POST'])
def suggestions():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

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
        return redirect(url_for('pantry.suggestions'))

    floor = _get_active_floor(user)
    
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

@pantry_bp.route('/suggestions/<int:suggestion_id>/vote', methods=['POST'])
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

@pantry_bp.route('/suggestions/<int:suggestion_id>/delete', methods=['POST'])
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

@pantry_bp.route('/feedbacks', methods=['GET', 'POST'])
def feedbacks():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        floor = _get_active_floor(user)
        menu_id_raw = (request.form.get('menu_id') or '').strip()
        if not menu_id_raw:
            flash('Please select a menu to evaluate', 'error')
            return redirect(url_for('pantry.feedbacks'))

        try:
            menu_id_val = int(menu_id_raw)
        except Exception:
            menu_id_val = None

        if not menu_id_val:
            flash('Invalid menu selected', 'error')
            return redirect(url_for('pantry.feedbacks'))

        menu = Menu.query.get(menu_id_val)
        if not menu or menu.floor != floor:
            flash('Menu not found on this floor', 'error')
            return redirect(url_for('pantry.feedbacks'))

        if menu.date and menu.date > date.today():
            flash('You can only evaluate menus from today or earlier', 'error')
            return redirect(url_for('pantry.feedbacks'))

        if not (menu.assigned_team_id or menu.assigned_to_id):
            flash('This menu is not assigned to a team/person yet', 'error')
            return redirect(url_for('pantry.feedbacks'))

        try:
            rating = int(request.form.get('rating') or 0)
        except ValueError:
            rating = 0

        if rating < 1 or rating > 5:
            flash('Rating must be between 1 and 5', 'error')
            return redirect(url_for('pantry.feedbacks'))

        description = (request.form.get('description') or '').strip()
        if not description:
            flash('Please add a short comment', 'error')
            return redirect(url_for('pantry.feedbacks'))

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
        return redirect(url_for('pantry.feedbacks'))

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

@pantry_bp.route('/feedbacks/<int:feedback_id>/delete', methods=['POST'])
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
