from flask import render_template, request, redirect, url_for, session, flash, abort, jsonify, g
from app import db
from models import User, Dish, DishAuditLog, Menu, MenuSuggestion, Feedback, Request, ProcurementItem, Team, TeamMember, TeaTask, FloorLendBorrow, SpecialEvent, Announcement, Suggestion, SuggestionVote, Expense, Budget, FacultyBudgetCycle, FacultyReportSubmission, FacultyMessage, FacultyMessageFloor, normalize_dish_name
from datetime import datetime, date, timedelta
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload
from . import pantry_bp
from ..budgeting import build_floor_budget_ledger
from ..utils import (
    current_tenant_faculty_workflow_enabled,
    _require_user,
    _get_active_floor,
    _require_staff_for_floor,
    _display_name_for,
    tenant_filter,
    send_push_notification,
    send_email_worker,
    FLOOR_MIN,
    FLOOR_MAX,
)
from app import db, cache

def _clear_dashboard_cache(tenant_id, floor):
    """Helper to clear cached dashboard stats for a specific tenant and floor."""
    cache.delete_memoized(_get_dashboard_stats, tenant_id, floor)

def _active_dish_query():
    return Dish.query.filter(Dish.is_archived == False)

def _find_global_dish_by_name(name, category=None):
    normalized = normalize_dish_name(name)
    if not normalized:
        return None
    query = _active_dish_query().filter(Dish.normalized_name == normalized)
    if category == 'main':
        query = query.filter(Dish.category.in_(['main', 'both']))
    elif category == 'side':
        query = query.filter(Dish.category.in_(['side', 'both']))
    return query.order_by(Dish.id.asc()).first()

def _log_dish_action(action, dish, user, description, details=None, target_dish_id=None):
    db.session.add(DishAuditLog(
        action=action,
        dish_id=dish.id if dish else None,
        target_dish_id=target_dish_id,
        description=description,
        details_json=details or {},
        performed_by_id=user.id if user else None,
        actor_tenant_id=getattr(g, 'tenant_id', None),
    ))

def _create_global_dish(name, category, user):
    dish = Dish(
        name=(name or '').strip(),
        category=category,
        created_by_id=user.id if user else None,
        origin_tenant_id=getattr(g, 'tenant_id', None),
    )
    db.session.add(dish)
    db.session.flush()
    _log_dish_action(
        'create',
        dish,
        user,
        f'Created global dish "{dish.name}" from menu scheduling.',
        {'category': category},
    )
    return dish

def _estimate_payload_for(dish):
    estimate = getattr(dish, 'estimate', None)
    if not estimate:
        return {
            'available': False,
            'serving_count': 30,
            'summary': '',
            'ingredients': [],
            'tips': [],
            'updated_at': None,
        }
    return {
        'available': True,
        'serving_count': estimate.serving_count or 30,
        'summary': estimate.summary or '',
        'ingredients': estimate.ingredients_json or [],
        'tips': estimate.tips_json or [],
        'updated_at': estimate.updated_at.isoformat() if estimate.updated_at else None,
    }


def _menu_notification_candidates(floor, assigned_to_id=None, assigned_team_id=None):
    recipients = []

    if assigned_to_id:
        user = tenant_filter(User.query).filter_by(id=assigned_to_id, floor=floor).first()
        if user:
            recipients.append(user)
    elif assigned_team_id:
        team_member_rows = (
            tenant_filter(TeamMember.query)
            .filter_by(team_id=assigned_team_id)
            .all()
        )
        team_member_ids = [row.user_id for row in team_member_rows if row.user_id]
        if team_member_ids:
            recipients = (
                tenant_filter(User.query)
                .filter(User.id.in_(team_member_ids), User.floor == floor)
                .order_by(User.full_name.asc(), User.username.asc(), User.id.asc())
                .all()
            )

    unique_recipients = []
    seen_ids = set()
    for recipient in recipients:
        if recipient.id in seen_ids:
            continue
        seen_ids.add(recipient.id)
        unique_recipients.append(recipient)

    return unique_recipients

@cache.memoize(timeout=300) # 5-minute cache
def _get_dashboard_stats(tenant_id, floor):
    """Heavy aggregate queries moved to a memoized function."""
    now_utc = datetime.utcnow()
    stars_since_dt = now_utc - timedelta(days=7)
    
    # Total spent: Legacy Expenses + Billed Procurement Costs
    total_spent_proc = tenant_filter(db.session.query(func.sum(ProcurementItem.actual_cost))).filter(
        ProcurementItem.floor == floor, 
        ProcurementItem.status == 'completed',
        ProcurementItem.bill_id.isnot(None)
    ).scalar() or 0
    total_spent_legacy = tenant_filter(db.session.query(func.sum(Expense.amount))).filter(Expense.floor == floor).scalar() or 0
    weekly_expenses = float(total_spent_proc) + float(total_spent_legacy)

    # Pending Lend/Borrow for this floor
    pending_lend_borrow_count = tenant_filter(FloorLendBorrow.query).filter(
        or_(FloorLendBorrow.lender_floor == floor, FloorLendBorrow.borrower_floor == floor),
        FloorLendBorrow.status == 'pending'
    ).count()

    user_count = tenant_filter(User.query).filter_by(floor=floor).count()
    pending_requests = tenant_filter(Request.query).filter_by(floor=floor, status='pending').count()
    
    stars_7d = int(
        (
            tenant_filter(db.session.query(func.coalesce(func.sum(Feedback.rating), 0)))
            .filter(Feedback.floor == floor, Feedback.created_at >= stars_since_dt, Feedback.menu_id.isnot(None))
            .scalar()
        )
        or 0
    )

    # Top Team logic
    top_team_label = None
    top_team_row = (
        tenant_filter(db.session.query(Menu.assigned_team_id.label('team_id'), func.sum(Feedback.rating).label('stars')))
        .join(Feedback, Feedback.menu_id == Menu.id)
        .filter(Menu.floor == floor, Feedback.created_at >= stars_since_dt, Menu.assigned_team_id.isnot(None))
        .group_by(Menu.assigned_team_id)
        .order_by(func.sum(Feedback.rating).desc())
        .first()
    )
    if top_team_row and top_team_row.team_id:
        t = Team.query.get(top_team_row.team_id)
        if t:
            top_team_label = f"{(t.icon or '').strip()} {(t.name or '').strip()}".strip()

    return {
        'user_count': user_count,
        'pending_requests': pending_requests,
        'weekly_expenses': weekly_expenses,
        'stars_7d': stars_7d,
        'pending_lend_borrow_count': pending_lend_borrow_count,
        'top_team_7d': top_team_label
    }

@pantry_bp.route('/dashboard')
def dashboard():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    floor = _get_active_floor(user)
    tenant_id = getattr(g, 'tenant_id', None)
    
    # IST is UTC+5:30
    now_utc = datetime.utcnow()
    ist_now = now_utc + timedelta(hours=5, minutes=30)
    today = ist_now.date()
    
    upcoming_until = today + timedelta(days=2)
    since_dt = now_utc - timedelta(days=2)
    
    # Get Cached Stats
    cached_stats = _get_dashboard_stats(tenant_id, floor)
    
    is_privileged = user.role in ['admin', 'pantryHead']
    
    stats = {
        'user_count': cached_stats['user_count'],
        'pending_requests': cached_stats['pending_requests'],
        'weekly_expenses': cached_stats['weekly_expenses'] if is_privileged else 0,
        'stars_7d': cached_stats['stars_7d'],
        'top_team_7d': cached_stats['top_team_7d']
    }
    pending_lend_borrow_count = cached_stats['pending_lend_borrow_count'] if is_privileged else 0
    faculty_workflow_enabled = current_tenant_faculty_workflow_enabled()

    # Upcoming Dish Logic: Show today's dish only if before 8 AM IST, else show next day's
    dish_query_date = today
    if ist_now.hour >= 8:
        dish_query_date = today + timedelta(days=1)

    upcoming_dish = (
        tenant_filter(Menu.query).options(joinedload(Menu.dish)).filter_by(floor=floor)
        .filter(Menu.date >= dish_query_date)
        .order_by(Menu.date.asc())
        .first()
    )



    upcoming_tea_duties = (
        tenant_filter(TeaTask.query).options(joinedload(TeaTask.assigned_to)).filter_by(floor=floor, assigned_to_id=user.id)
        .filter(TeaTask.status != 'completed', TeaTask.date >= today, TeaTask.date <= upcoming_until)
        .order_by(TeaTask.date.asc())
        .all()
    )

    upcoming_procurement_assignments = (
        tenant_filter(ProcurementItem.query).options(joinedload(ProcurementItem.assigned_to)).filter_by(floor=floor, assigned_to_id=user.id)
        .filter(ProcurementItem.status != 'completed', ProcurementItem.created_at >= since_dt)
        .order_by(ProcurementItem.created_at.desc())
        .all()
    )

    team_ids = [
        tid
        for (tid,) in (
            tenant_filter(db.session.query(TeamMember.team_id))
            .join(Team, TeamMember.team_id == Team.id)
            .filter(Team.floor == floor, TeamMember.user_id == user.id)
            .all()
        )
    ]
    menu_filters = [Menu.assigned_to_id == user.id]
    if team_ids:
        menu_filters.append(Menu.assigned_team_id.in_(team_ids))

    upcoming_menu_assignments = (
        tenant_filter(Menu.query).options(joinedload(Menu.assigned_to), joinedload(Menu.assigned_team)).filter_by(floor=floor)
        .filter(Menu.date >= today, Menu.date <= upcoming_until)
        .filter(or_(*menu_filters))
        .order_by(Menu.date.asc())
        .all()
    )

    active_cycle = None
    active_cycle_allocation = None
    current_cycle_submission = None
    if is_privileged and faculty_workflow_enabled:
        active_cycle = (
            tenant_filter(FacultyBudgetCycle.query)
            .filter_by(status='active')
            .order_by(FacultyBudgetCycle.start_date.desc())
            .first()
        )
        if active_cycle:
            active_cycle_allocation = tenant_filter(Budget.query).filter(
                Budget.cycle_id == active_cycle.id,
                Budget.floor == floor,
            ).first()
            if active_cycle_allocation:
                current_cycle_submission = tenant_filter(FacultyReportSubmission.query).filter_by(
                    cycle_id=active_cycle.id,
                    floor=floor,
                ).first()

    # Notifications logic
    notifications = []
    
    # 1. Announcements (last 7 days)
    announcement_since = datetime.utcnow() - timedelta(days=7)
    recent_announcements = tenant_filter(Announcement.query).options(joinedload(Announcement.created_by)).filter(
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
    upcoming_events = tenant_filter(SpecialEvent.query).options(joinedload(SpecialEvent.created_by)).filter(
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

    if is_privileged and active_cycle and active_cycle_allocation:
        notifications.append({
            'type': 'faculty',
            'icon': 'fas fa-layer-group',
            'title': f"Faculty Cycle Active: {active_cycle.title}",
            'content': f"Allocated budget: INR {float(active_cycle_allocation.amount_allocated):.2f}. Deadline: {active_cycle.submission_deadline.strftime('%Y-%m-%d')}.",
            'time': active_cycle.activated_at or active_cycle.created_at,
            'category': 'Faculty Cycle',
        })

        days_to_deadline = (active_cycle.submission_deadline - today).days
        if current_cycle_submission is None:
            notifications.append({
                'type': 'faculty',
                'icon': 'fas fa-file-upload',
                'title': 'No Faculty report uploaded yet',
                'content': f"Your floor has not submitted a report for {active_cycle.title} yet.",
                'time': datetime.combine(active_cycle.submission_deadline, datetime.min.time()),
                'category': 'Faculty Cycle',
            })
            if days_to_deadline < 0:
                notifications.append({
                    'type': 'faculty',
                    'icon': 'fas fa-triangle-exclamation',
                    'title': 'Faculty report is overdue',
                    'content': f"The submission deadline was {active_cycle.submission_deadline.strftime('%Y-%m-%d')}. Please upload the report urgently.",
                    'time': datetime.combine(active_cycle.submission_deadline, datetime.min.time()),
                    'category': 'Faculty Cycle',
                })
            elif days_to_deadline <= 3:
                notifications.append({
                    'type': 'faculty',
                    'icon': 'fas fa-hourglass-half',
                    'title': 'Faculty report deadline approaching',
                    'content': f"{days_to_deadline} day(s) left before the submission deadline for {active_cycle.title}.",
                    'time': datetime.combine(active_cycle.submission_deadline, datetime.min.time()),
                    'category': 'Faculty Cycle',
                })
        elif current_cycle_submission.status == 'submitted':
            notifications.append({
                'type': 'faculty',
                'icon': 'fas fa-user-clock',
                'title': 'Faculty review pending',
                'content': f"Your report for {active_cycle.title} has been submitted and is awaiting Faculty review.",
                'time': current_cycle_submission.submitted_at,
                'category': 'Faculty Cycle',
            })
        elif current_cycle_submission.status == 'rejected':
            notifications.append({
                'type': 'faculty',
                'icon': 'fas fa-rotate-left',
                'title': 'Faculty requested a resubmission',
                'content': current_cycle_submission.review_notes or f"Your report for {active_cycle.title} was rejected and needs revision.",
                'time': current_cycle_submission.updated_at or current_cycle_submission.submitted_at,
                'category': 'Faculty Cycle',
            })

    if user.role == 'pantryHead' and faculty_workflow_enabled:
        faculty_messages = (
            tenant_filter(FacultyMessage.query)
            .options(joinedload(FacultyMessage.created_by), joinedload(FacultyMessage.target_floors))
            .filter(
                FacultyMessage.is_archived == False,
                or_(
                    FacultyMessage.target_scope == 'all_pantry_heads',
                    FacultyMessage.target_floors.any(FacultyMessageFloor.floor == floor),
                ),
            )
            .order_by(FacultyMessage.created_at.desc())
            .limit(10)
            .all()
        )
        for message in faculty_messages:
            notifications.append({
                'type': 'faculty_message',
                'icon': 'fas fa-building-columns',
                'title': message.title,
                'content': message.content,
                'time': message.created_at,
                'category': 'Faculty Message',
            })

    # 4. Pending Suggestions (Pantry Head / Admin only)
    if is_privileged:
        pending_suggestions_count = tenant_filter(MenuSuggestion.query).filter(
            MenuSuggestion.floor == floor,
            MenuSuggestion.date >= today
        ).count()
        if pending_suggestions_count > 0:
            notifications.append({
                'type': 'suggestion',
                'icon': 'fas fa-lightbulb',
                'title': 'New Menu Suggestions',
                'content': f"You have {pending_suggestions_count} pending suggestion(s) from members waiting for review.",
                'time': datetime.combine(today, datetime.min.time()),
                'category': 'Community',
                'url': url_for('pantry.menus')
            })

    # Sort notifications by time
    notifications.sort(key=lambda x: x['time'], reverse=True)
    
    # Morning Brief for Pantry Heads
    morning_brief = None
    if user.role == 'pantryHead':
        morning_brief = {
            'absent_staff_count': 0,
            'breakfast_rating': 0,
            'breakfast_feedback_count': 0,
            'budget_usage_pct': 0,
            'budget_remaining_days': 0,
            'pending_procurement_count': 0,
            'breakfast_dish_name': 'Breakfast'
        }
        
        # 1. Staff Absent today
        morning_brief['absent_staff_count'] = tenant_filter(Request.query).filter(
            Request.floor == floor,
            Request.request_type == 'absence',
            Request.status == 'approved',
            Request.start_date <= today,
            Request.end_date >= today
        ).count()
        
        # 2. Breakfast Feedback (Most recent breakfast today or yesterday)
        recent_breakfast = tenant_filter(Menu.query).filter(
            Menu.floor == floor,
            Menu.meal_type == 'breakfast',
            Menu.date <= today
        ).order_by(Menu.date.desc()).first()
        
        if recent_breakfast:
            morning_brief['breakfast_dish_name'] = recent_breakfast.title
            feedback_stats = tenant_filter(db.session.query(
                func.avg(Feedback.rating),
                func.count(Feedback.id)
            )).filter(Feedback.menu_id == recent_breakfast.id).first()
            
            if feedback_stats and feedback_stats[1] > 0:
                morning_brief['breakfast_rating'] = round(float(feedback_stats[0]), 1)
                morning_brief['breakfast_feedback_count'] = feedback_stats[1]
        
        # 3. Budget Alert
        floor_budget_ledger = build_floor_budget_ledger(
            floor=floor,
            faculty_workflow_enabled=faculty_workflow_enabled,
        )
        current_budget_period = floor_budget_ledger['current_period']
        available_budget = floor_budget_ledger['current_available_budget']
        current_spent = floor_budget_ledger['current_spent_amount']

        if available_budget > 0:
            morning_brief['budget_usage_pct'] = min(100, round((current_spent / available_budget) * 100))

        if current_budget_period and current_budget_period.get('effective_end_date'):
            remaining_days = (current_budget_period['effective_end_date'] - today).days
        else:
            end_of_week = today - timedelta(days=today.weekday()) + timedelta(days=6)
            remaining_days = (end_of_week - today).days
        morning_brief['budget_remaining_days'] = max(0, remaining_days)
                
        # 4. Procurement Pending
        morning_brief['pending_procurement_count'] = tenant_filter(ProcurementItem.query).filter(
            ProcurementItem.floor == floor,
            ProcurementItem.status != 'completed'
        ).count()

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
        morning_brief=morning_brief
    )

def _get_next_team_in_rotation(floor):
    """
    Finds the next team in rotation based on non-buffer menu history.
    """
    all_teams = tenant_filter(Team.query).filter_by(floor=floor).all()
    if not all_teams:
        return None
    
    # Get last assignment date for each team (only from non-buffer days)
    team_last_served = (
        db.session.query(Menu.assigned_team_id, func.max(Menu.date).label('last_date'))
        .filter(Menu.floor == floor, Menu.assigned_team_id.isnot(None), Menu.is_buffer == False)
        .group_by(Menu.assigned_team_id)
        .all()
    )
    
    last_served_map = {row.assigned_team_id: row.last_date for row in team_last_served}
    
    # Sort teams by last_served_date (None first, then oldest date)
    def sort_key(team):
        last_date = last_served_map.get(team.id)
        if last_date is None:
            return date(1900, 1, 1) # Long ago
        return last_date

    sorted_teams = sorted(all_teams, key=sort_key)
    return sorted_teams[0] if sorted_teams else None

@pantry_bp.route('/menus/rotation-sequence')
def get_rotation_sequence():
    """
    Returns a sequence of 7 teams for a rolling week starting from the next team in line.
    """
    user = _require_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    floor = _get_active_floor(user)
    all_teams = tenant_filter(Team.query).filter_by(floor=floor).order_by(Team.id.asc()).all()
    if not all_teams:
        return jsonify({'sequence': []})

    # Find the single next team
    next_team = _get_next_team_in_rotation(floor)
    
    # Find its index in the sorted list
    start_idx = 0
    if next_team:
        for i, t in enumerate(all_teams):
            if t.id == next_team.id:
                start_idx = i
                break
    
    # Generate 7-day sequence
    sequence = []
    for i in range(7):
        target_date = date.today() + timedelta(days=i) # Approximation for sequence
        team = all_teams[(start_idx + i) % len(all_teams)]
        
        # Conflict Check: Are any team members absent?
        absent_members = db.session.query(User.full_name).join(TeamMember, TeamMember.user_id == User.id).join(Request, Request.user_id == User.id).filter(
            TeamMember.team_id == team.id,
            Request.status == 'approved',
            Request.request_type == 'absence',
            Request.start_date <= target_date,
            Request.end_date >= target_date
        ).all()
        
        sequence.append({
            'id': team.id,
            'name': team.name,
            'icon': team.icon,
            'conflicts': [m[0] for m in absent_members]
        })
        
    return jsonify({'sequence': sequence})

@pantry_bp.route('/menus/next-team')
def get_next_team():
    """
    Expert Logic: Returns the single next team in rotation with conflict check for a given date.
    """
    user = _require_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    floor = _get_active_floor(user)
    target_date_str = request.args.get('date')
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    team = _get_next_team_in_rotation(floor)
    if not team:
        return jsonify({'error': 'No teams found'})

    # Conflict Check: Are any team members absent?
    absent_members = db.session.query(User.full_name).join(TeamMember, TeamMember.user_id == User.id).join(Request, Request.user_id == User.id).filter(
        TeamMember.team_id == team.id,
        Request.status == 'approved',
        Request.request_type == 'absence',
        Request.start_date <= target_date,
        Request.end_date >= target_date
    ).all()

    return jsonify({
        'id': team.id,
        'name': team.name,
        'icon': team.icon,
        'conflicts': [m[0] for m in absent_members]
    })

@pantry_bp.route('/menus/bulk-schedule', methods=['POST'])
def bulk_schedule():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json # List of meal objects
    if not data or not isinstance(data, list):
        return jsonify({'error': 'Invalid data format'}), 400
        
    floor = _get_active_floor(user)
    
    try:
        # Pre-cleanup: Delete existing menus for the range if we are doing a full week refresh
        if len(data) >= 5:
            dates = [datetime.strptime(item.get('date'), '%Y-%m-%d').date() for item in data if item.get('date')]
            if dates:
                start_d, end_d = min(dates), max(dates)
                tenant_filter(Menu.query).filter(
                    Menu.floor == floor,
                    Menu.date >= start_d,
                    Menu.date <= end_d
                ).delete(synchronize_session=False)

        # Assignment map for consolidated mailing: {user_id: [menu_details]}
        recipient_map = {}

        for item in data:
            # Basic validation
            menu_date = datetime.strptime(item.get('date'), '%Y-%m-%d').date()
            
            dish_id = item.get('dish_id')
            if isinstance(dish_id, str) and dish_id.strip():
                try: dish_id = int(dish_id)
                except: dish_id = None
            else: dish_id = None if not dish_id else dish_id

            new_dish_name = item.get('new_dish_name')
            
            if dish_id and not _active_dish_query().filter_by(id=dish_id).first():
                dish_id = None

            if not dish_id and not new_dish_name: continue 

            # Handle Main Dish creation
            if not dish_id and new_dish_name:
                existing = _find_global_dish_by_name(new_dish_name, category='main')
                if existing:
                    dish_id = existing.id
                else:
                    new_dish = _create_global_dish(new_dish_name, 'main', user)
                    dish_id = new_dish.id

            # Handle Side Dish creation
            side_dish_id = item.get('side_dish_id')
            if isinstance(side_dish_id, str) and side_dish_id.strip():
                try: side_dish_id = int(side_dish_id)
                except: side_dish_id = None
            else: side_dish_id = None if not side_dish_id else side_dish_id

            new_side_dish_name = item.get('new_side_dish_name')
            if side_dish_id and not _active_dish_query().filter_by(id=side_dish_id).first():
                side_dish_id = None
            if not side_dish_id and new_side_dish_name:
                existing_side = _find_global_dish_by_name(new_side_dish_name, category='side')
                if existing_side:
                    side_dish_id = existing_side.id
                else:
                    new_side = _create_global_dish(new_side_dish_name, 'side', user)
                    side_dish_id = new_side.id

            assigned_team_id = item.get('assigned_team_id')
            if isinstance(assigned_team_id, str) and assigned_team_id.strip():
                try: assigned_team_id = int(assigned_team_id)
                except: assigned_team_id = None
            
            assigned_to_id = item.get('assigned_to_id')
            if isinstance(assigned_to_id, str) and assigned_to_id.strip():
                try: assigned_to_id = int(assigned_to_id)
                except: assigned_to_id = None

            menu = Menu(
                title=item.get('title') or 'Bulk Scheduled',
                description=item.get('description') or '',
                date=menu_date,
                meal_type='breakfast',
                dish_id=dish_id,
                side_dish_id=side_dish_id,
                assigned_team_id=assigned_team_id,
                assigned_to_id=assigned_to_id,
                is_buffer=item.get('is_buffer', False),
                floor=floor,
                skip_notifications=True, # Disable individual Supabase triggers
                created_by_id=user.id,
                tenant_id=getattr(g, 'tenant_id', None)
            )
            db.session.add(menu)

            # --- Consolidate Assignments for Mailing ---
            recipients = []
            if assigned_to_id:
                recipients.append(assigned_to_id)
            elif assigned_team_id:
                # RESOLVED: Use tenant_filter for safety and consistent data access
                members = tenant_filter(TeamMember.query).filter_by(team_id=assigned_team_id).all()
                recipients.extend([m.user_id for m in members])
            
            dish_obj = Dish.query.filter_by(id=dish_id).first() if dish_id else None
            side_obj = Dish.query.filter_by(id=side_dish_id).first() if side_dish_id else None
            dish_label = f"{dish_obj.name if dish_obj else menu.title}{' + ' + side_obj.name if side_obj else ''}"

            print(f"DEBUG: Found {len(recipients)} recipients for date {menu_date}")
            for rid in set(recipients):
                if rid not in recipient_map: recipient_map[rid] = []
                recipient_map[rid].append({
                    'date': menu_date,
                    'meal': dish_label,
                    'note': menu.description or ''
                })
            
        db.session.commit()

        # --- Trigger Consolidated Edge Function ---
        if recipient_map:
            payload = {"recipient_map": {}}
            for rid, assignments in recipient_map.items():
                target_user = db.session.get(User, rid)
                if target_user and target_user.email:
                    payload["recipient_map"][rid] = {
                        "email": target_user.email,
                        "name": target_user.full_name or target_user.username,
                        "assignments": [
                            {
                                "date": a['date'].isoformat(),
                                "meal": a['meal'],
                                "note": a['note']
                            } for a in assignments
                        ]
                    }
            
            try:
                import requests
                import os
                
                # Retrieve the key
                sb_key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
                
                if not sb_key:
                    print("WARNING: SUPABASE_SERVICE_ROLE_KEY not found in environment!")
                    # Try to fallback to any other supabase key if available
                    sb_key = os.environ.get('SUPABASE_ANON_KEY') or os.environ.get('SUPABASE_KEY')

                headers = {
                    "Content-Type": "application/json"
                }
                
                if sb_key:
                    headers["Authorization"] = f"Bearer {sb_key}"
                    print(f"DEBUG: Triggering bulk function with Auth header (Key length: {len(sb_key)})")
                else:
                    print("ERROR: No Supabase key found. Request will likely fail with 401.")

                response = requests.post(
                    "https://nowdhtfvhrhdkmwnerth.supabase.co/functions/v1/notify-bulk-menu-assignment",
                    json=payload,
                    headers=headers,
                    timeout=15
                )
                print(f"DEBUG: Bulk function response status: {response.status_code}")
                if response.status_code != 200:
                    print(f"DEBUG: Bulk function error body: {response.text}")
                    
            except Exception as e:
                print(f"ERROR: Failed to trigger bulk edge function: {e}")

        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

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
    tenant_id = getattr(g, 'tenant_id', None)
    users = tenant_filter(User.query).filter_by(floor=floor).all()
    users.sort(key=lambda u: (u.full_name or u.username or u.email or "").lower())
    teams = tenant_filter(Team.query).filter_by(floor=floor).order_by(Team.name.asc()).all()

    team_memberships = tenant_filter(TeamMember.query).options(joinedload(TeamMember.user)).join(Team, TeamMember.team_id == Team.id).filter(Team.floor == floor).all()
    members_by_team_id = {}
    for tm in team_memberships:
        if tm.user is not None:
            members_by_team_id.setdefault(tm.team_id, []).append(tm.user)

    for team_id, members in members_by_team_id.items():
        members.sort(key=lambda u: (u.full_name or u.username or u.email or "").lower())

    my_team_ids = [tm.team_id for tm in team_memberships if tm.user_id == user.id]
    my_teams = [t for t in teams if t.id in set(my_team_ids)]

    leaderboard_since = datetime.utcnow() - timedelta(days=30)

    team_leaderboard = []
    team_query = db.session.query(
            Team.id.label('team_id'),
            Team.name.label('team_name'),
            Team.icon.label('team_icon'),
            func.coalesce(func.sum(Feedback.rating), 0).label('stars'),
            func.count(Feedback.id).label('ratings_count'),
            func.coalesce(func.avg(Feedback.rating), 0).label('avg_rating'),
        )
    if tenant_id:
        team_query = team_query.filter(Menu.tenant_id == tenant_id)
    team_rows = (
        team_query
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
    individual_query = db.session.query(
            User.id.label('user_id'),
            User.full_name.label('full_name'),
            User.username.label('username'),
            User.email.label('email'),
            func.coalesce(func.sum(Feedback.rating), 0).label('stars'),
            func.count(Feedback.id).label('ratings_count'),
            func.coalesce(func.avg(Feedback.rating), 0).label('avg_rating'),
        )
    if tenant_id:
        individual_query = individual_query.filter(Menu.tenant_id == tenant_id)
    individual_rows = (
        individual_query
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
    dish_query = db.session.query(
            dish_name_expr.label('dish_name'),
            func.coalesce(func.sum(Feedback.rating), 0).label('stars'),
            func.count(Feedback.id).label('ratings_count'),
            func.coalesce(func.avg(Feedback.rating), 0).label('avg_rating'),
        )
    if tenant_id:
        dish_query = dish_query.filter(Menu.tenant_id == tenant_id)
    dish_rows = (
        dish_query
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

    dish_champion_query = db.session.query(
            dish_name_expr.label('dish_name'),
            Team.id.label('team_id'),
            Team.name.label('team_name'),
            Team.icon.label('team_icon'),
            func.coalesce(func.sum(Feedback.rating), 0).label('stars'),
        )
    if tenant_id:
        dish_champion_query = dish_champion_query.filter(Menu.tenant_id == tenant_id)
    dish_champion_rows = (
        dish_champion_query
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
        active_floor=floor
    )

@pantry_bp.route('/calendar')
def calendar():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    floor = _get_active_floor(user)
    
    # Get year and month from query params or default to current date
    now = datetime.now()
    try:
        current_year = int(request.args.get('year', now.year))
        current_month = int(request.args.get('month', now.month))
    except (ValueError, TypeError):
        current_year = now.year
        current_month = now.month

    # Handle month rollover safely (e.g. month=0 or month=13)
    if current_month < 1:
        current_month = 12
        current_year -= 1
    elif current_month > 12:
        current_month = 1
        current_year += 1

    # Calculate range for calendar grid (roughly 6 weeks)
    start_bound = date(current_year, current_month, 1) - timedelta(days=7)
    if current_month == 12:
        next_month_start = date(current_year + 1, 1, 1)
    else:
        next_month_start = date(current_year, current_month + 1, 1)
    end_bound = next_month_start + timedelta(days=14)

    floor_menus = tenant_filter(Menu.query).options(
        joinedload(Menu.assigned_to), 
        joinedload(Menu.assigned_team),
        joinedload(Menu.dish),
        joinedload(Menu.side_dish)
    ).filter(
        Menu.floor == floor,
        Menu.date >= start_bound,
        Menu.date <= end_bound
    ).all()
    
    floor_tea_tasks = tenant_filter(TeaTask.query).options(
        joinedload(TeaTask.assigned_to)
    ).filter(
        TeaTask.floor == floor,
        TeaTask.date >= start_bound,
        TeaTask.date <= end_bound
    ).all()

    floor_special_events = tenant_filter(SpecialEvent.query).options(
        joinedload(SpecialEvent.created_by)
    ).filter(
        SpecialEvent.floor == floor,
        SpecialEvent.date >= start_bound,
        SpecialEvent.date <= end_bound
    ).all()

    menus = [
        {
            "id": m.id,
            "type": "menu",
            "title": m.title,
            "dish_id": m.dish_id,
            "side_dish_name": m.side_dish.name if m.side_dish else None,
            "description": m.description,
            "date": m.date.isoformat() if m.date else None,
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

    menu_suggestions_db = tenant_filter(MenuSuggestion.query).options(
        joinedload(MenuSuggestion.suggested_by),
        joinedload(MenuSuggestion.dish),
        joinedload(MenuSuggestion.side_dish),
        joinedload(MenuSuggestion.suggested_team)
    ).filter(
        MenuSuggestion.floor == floor,
        MenuSuggestion.date >= start_bound,
        MenuSuggestion.date <= end_bound
    ).all()

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
    
    menu_suggestions = [
        {
            "id": s.id,
            "type": "suggestion",
            "title": (s.dish.name if s.dish else s.new_dish_name) or 'Suggested Meal',
            "description": s.description,
            "date": s.date.isoformat() if s.date else None,
            "created_by": (s.suggested_by.full_name or s.suggested_by.username) if s.suggested_by else "System",
            "suggested_by_id": s.suggested_by_id,
            "side_dish_name": s.side_dish.name if s.side_dish else s.new_side_dish_name,
            "team_name": s.suggested_team.name if s.suggested_team else None
        }
        for s in menu_suggestions_db
    ]

    main_dishes = _active_dish_query().filter(Dish.category.in_(['main', 'both'])).order_by(func.lower(Dish.name).asc()).all()
    side_dishes = _active_dish_query().filter(Dish.category.in_(['side', 'both'])).order_by(func.lower(Dish.name).asc()).all()
    floor_teams = tenant_filter(Team.query).filter_by(floor=floor).order_by(Team.name.asc()).all()

    return render_template('calendar.html', 
                           menus=menus, 
                           tea_tasks=tea_tasks, 
                           special_events=special_events, 
                           menu_suggestions=menu_suggestions,
                           main_dishes=main_dishes,
                           side_dishes=side_dishes,
                           floor_teams=floor_teams,
                           current_user=user, 
                           active_floor=floor,
                           current_year=current_year,
                           current_month=current_month)

@pantry_bp.route('/menus/suggest', methods=['POST'])
def suggest_menu():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    floor = _get_active_floor(user)
    tenant_id = getattr(g, 'tenant_id', None)
    
    try:
        menu_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
    except Exception:
        flash('Invalid date', 'error')
        return redirect(url_for('pantry.calendar'))
        
    if menu_date < date.today():
        flash('Cannot suggest menus for past dates.', 'error')
        return redirect(url_for('pantry.calendar'))

    # 1. Edge Case: Daily limit (max 2 suggestions per day per floor)
    daily_count = tenant_filter(MenuSuggestion.query).filter_by(
        date=menu_date, 
        floor=floor
    ).count()
    if daily_count >= 2:
        flash('This day already has enough suggestions (max 2).', 'warning')
        return redirect(url_for('pantry.calendar'))

    # 2. Edge Case: User limit (max 2 suggestions per user per week)
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    weekly_user_count = tenant_filter(MenuSuggestion.query).filter(
        MenuSuggestion.suggested_by_id == user.id,
        MenuSuggestion.date >= start_of_week
    ).count()
    if weekly_user_count >= 2:
        flash('You have reached your limit of 2 suggestions for this week.', 'warning')
        return redirect(url_for('pantry.calendar'))

    dish_id_raw = (request.form.get('dish_id') or '').strip()
    new_dish_name = (request.form.get('new_dish_name') or '').strip()
    side_dish_id_raw = (request.form.get('side_dish_id') or '').strip()
    new_side_dish_name = (request.form.get('new_side_dish_name') or '').strip()
    # suggested_team_id removed as per refactor
    description = (request.form.get('description') or '').strip()

    dish_id = None
    if dish_id_raw:
        try: dish_id = int(dish_id_raw)
        except ValueError: pass
        
    side_dish_id = None
    if side_dish_id_raw:
        try: side_dish_id = int(side_dish_id_raw)
        except ValueError: pass

    if not dish_id and not new_dish_name:
        flash('Please select a main dish or suggest a new one.', 'error')
        return redirect(url_for('pantry.calendar'))

    suggestion = MenuSuggestion(
        date=menu_date,
        dish_id=dish_id,
        new_dish_name=new_dish_name,
        side_dish_id=side_dish_id,
        new_side_dish_name=new_side_dish_name,
        suggested_team_id=None, # Explicitly nullified
        description=description,
        floor=floor,
        suggested_by_id=user.id,
        tenant_id=tenant_id
    )
    
    db.session.add(suggestion)
    db.session.commit()
    flash('Menu suggestion submitted successfully.', 'success')
    return redirect(url_for('pantry.calendar'))

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
        created_by_id=user.id,
        tenant_id=getattr(g, 'tenant_id', None)
    )
    db.session.add(new_event)
    db.session.commit()
    _clear_dashboard_cache(getattr(g, 'tenant_id', None), floor)

    # Notify users on the floor via Push
    floor_users = tenant_filter(User.query).filter_by(floor=floor).all()
    for fu in floor_users:
        if fu.id != user.id: # Don't notify the creator
            send_push_notification(
                user_id=fu.id,
                title="New Special Event",
                body=f"{title} on {event_date.strftime('%b %d')}",
                icon="/static/icons/icon-192.png",
                url="/calendar"
            )

    flash('Special event added to calendar.', 'success')
    return redirect(url_for('pantry.calendar'))

@pantry_bp.route('/special-events/<int:event_id>/delete', methods=['POST'])
def delete_special_event(event_id):
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)

    event = tenant_filter(SpecialEvent.query).filter_by(id=event_id).first_or_404()
    
    # Ensure the event belongs to the user's floor
    floor = _get_active_floor(user)
    if event.floor != floor:
        abort(403)

    db.session.delete(event)
    db.session.commit()
    flash('Special event deleted.', 'success')
    return redirect(url_for('pantry.calendar'))

@pantry_bp.route('/special-events/<int:event_id>/update', methods=['POST'])
def update_special_event(event_id):
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)

    event = tenant_filter(SpecialEvent.query).filter_by(id=event_id).first_or_404()
    
    floor = _get_active_floor(user)
    if event.floor != floor:
        abort(403)

    try:
        event.title = request.form.get('title')
        event.description = request.form.get('description')
        event.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        db.session.commit()
        flash('Special event updated.', 'success')
    except Exception:
        flash('Invalid event data', 'error')

    return redirect(url_for('pantry.calendar'))

@pantry_bp.route('/menus', methods=['GET', 'POST'])
def menus():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    # Expert UI decision: Members use the Calendar for all meal viewing.
    if user.role == 'member':
        return redirect(url_for('pantry.calendar'))

    floor = _get_active_floor(user)
    tenant_id = getattr(g, 'tenant_id', None)
    floor_users = tenant_filter(User.query).filter_by(floor=floor).all()
    floor_user_directory = {}
    for floor_user in floor_users:
        floor_user_directory[str(floor_user.id)] = {
            'id': floor_user.id,
            'label': (floor_user.full_name or floor_user.username or floor_user.email or f'User {floor_user.id}').strip(),
            'email': floor_user.email or '',
        }
    floor_teams = tenant_filter(Team.query).filter_by(floor=floor).order_by(Team.name.asc()).all()
    team_members_by_team_id = {}
    team_memberships = (
        tenant_filter(TeamMember.query)
        .join(Team, TeamMember.team_id == Team.id)
        .filter(Team.floor == floor)
        .all()
    )
    for membership in team_memberships:
        team_members_by_team_id.setdefault(membership.team_id, []).append(membership.user_id)
    
    # Dishes are global platform catalog entries; floor data remains tenant scoped.
    main_dishes = _active_dish_query().filter(Dish.category.in_(['main', 'both'])).order_by(func.lower(Dish.name).asc()).all()
    side_dishes = _active_dish_query().filter(Dish.category.in_(['side', 'both'])).order_by(func.lower(Dish.name).asc()).all()
    all_dishes = _active_dish_query().order_by(func.lower(Dish.name).asc()).all()

    if request.method == 'POST' and user.role in ['admin', 'pantryHead']:
        expects_json = 'application/json' in (request.headers.get('Accept') or '').lower()

        try:
            menu_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
            meal_type = request.form.get('meal_type', 'breakfast')
        except Exception:
            if expects_json:
                return jsonify({'error': 'Invalid menu date or type'}), 400
            flash('Invalid menu date or type', 'error')
            return redirect(url_for('pantry.menus'))

        # Prevention: Check if this meal time is already scheduled for this date
        existing_meal = tenant_filter(Menu.query).filter_by(floor=floor, date=menu_date, meal_type=meal_type).first()
        if existing_meal:
            if expects_json:
                return jsonify({'error': f'A {meal_type} is already scheduled for {menu_date}.'}), 409
            flash(f'A {meal_type} is already scheduled for {menu_date}. Please edit or delete the existing one.', 'warning')
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
                if expects_json:
                    return jsonify({'error': 'Invalid dish selected'}), 400
                flash('Invalid dish selected', 'error')
                return redirect(url_for('pantry.menus'))
            dish = _active_dish_query().filter_by(id=dish_id_val).first()
            if not dish:
                if expects_json:
                    return jsonify({'error': 'Selected dish is no longer available'}), 400
                flash('Selected dish is no longer available', 'error')
                return redirect(url_for('pantry.menus'))
        elif new_dish_name:
            existing = _find_global_dish_by_name(new_dish_name, category='main')
            if existing:
                dish = existing
            else:
                dish = _create_global_dish(new_dish_name, 'main', user)
        else:
            if expects_json:
                return jsonify({'error': 'Please select a main dish'}), 400
            flash('Please select a main dish', 'error')
            return redirect(url_for('pantry.menus'))

        # Side Dish
        side_dish_id = request.form.get('side_dish_id') or None
        new_side_dish_name = (request.form.get('new_side_dish_name') or '').strip()

        if new_side_dish_name:
            existing_side = _find_global_dish_by_name(new_side_dish_name, category='side')
            if existing_side:
                side_dish_id = existing_side.id
            else:
                side_dish = _create_global_dish(new_side_dish_name, 'side', user)
                side_dish_id = side_dish.id
        elif side_dish_id:
            try:
                side_dish_id = int(side_dish_id)
                if not _active_dish_query().filter_by(id=side_dish_id).first():
                    side_dish_id = None
            except ValueError:
                side_dish_id = None

        is_buffer = request.form.get('is_buffer') == 'true'
        assigned_to_id = request.form.get('assigned_to_id') or None
        assigned_team_id = request.form.get('assigned_team_id') or None
        
        # ... logic for assignments continues
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

        if assigned_team_id and not tenant_filter(Team.query).filter_by(id=assigned_team_id, floor=floor).first():
            if expects_json:
                return jsonify({'error': 'Assigned team must be on your floor'}), 400
            flash('Assigned team must be on your floor', 'error')
            assigned_team_id = None

        if assigned_team_id:
            assigned_to_id = None

        if assigned_to_id and not tenant_filter(User.query).filter_by(id=assigned_to_id, floor=floor).first():
            if expects_json:
                return jsonify({'error': 'Assigned user must be on your floor'}), 400
            flash('Assigned user must be on your floor', 'error')
            assigned_to_id = None

        menu_title = (dish.name or '').strip() if dish else 'Menu'

        menu = Menu(
            title=menu_title[:100],
            description=request.form.get('description'),
            date=menu_date,
            meal_type=meal_type,
            dish_type=request.form.get('dish_type') or 'main',
            dish_id=dish.id if dish else None,
            side_dish_id=side_dish_id,
            is_buffer=is_buffer,
            assigned_to_id=assigned_to_id,
            assigned_team_id=assigned_team_id,
            floor=floor,
            # Single-menu notifications are handled by the explicit UI pipeline
            # (create without informing OR selected recipients via notify_single).
            # Keep DB-triggered Supabase edge mails disabled here to avoid duplicates.
            skip_notifications=True,
            created_by_id=user.id,
            tenant_id=tenant_id
        )
        db.session.add(menu)
        db.session.commit()
        _clear_dashboard_cache(tenant_id, floor)

        notify_mode = (request.form.get('notify_mode') or 'legacy').strip()
        recipients = _menu_notification_candidates(
            floor=floor,
            assigned_to_id=assigned_to_id,
            assigned_team_id=assigned_team_id,
        )

        suggestion_id_raw = request.form.get('suggestion_id')
        if suggestion_id_raw:
            try:
                suggestion_id = int(suggestion_id_raw)
                suggestion_to_delete = tenant_filter(MenuSuggestion.query).filter_by(id=suggestion_id, floor=floor).first()
                if suggestion_to_delete:
                    db.session.delete(suggestion_to_delete)
                    db.session.commit()
            except ValueError:
                pass

        selected_notify_ids = []
        for raw_user_id in request.form.getlist('notify_user_ids'):
            try:
                selected_notify_ids.append(int(raw_user_id))
            except (TypeError, ValueError):
                continue
        if selected_notify_ids:
            selected_id_set = set(selected_notify_ids)
            recipients = [r for r in recipients if r.id in selected_id_set]

        if expects_json:
            recipient_payload = [
                {
                    'id': r.id,
                    'name': (r.full_name or r.username or r.email or f'User {r.id}').strip(),
                    'has_email': bool(r.email),
                }
                for r in recipients
            ]
            return jsonify({
                'menu_id': menu.id,
                'menu_label': menu_title,
                'notify_mode': notify_mode,
                'recipients': recipient_payload,
            })

        if notify_mode != 'none' and assigned_to_id:
            send_push_notification(
                user_id=assigned_to_id,
                title="New Menu Assignment",
                body=f"You have been assigned to prepare: {menu_title}.",
                icon="/static/icons/icon-192.png",
                url="/menus"
            )

        if notify_mode == 'none':
            flash('Menu scheduled without sending notifications.', 'success')
        else:
            flash('Menu added successfully', 'success')
        return redirect(url_for('pantry.menus'))

    # Prepare Weekly View Data
    week_offset = request.args.get('week_offset', 0, type=int)
    today = date.today()
    target_date = today + timedelta(weeks=week_offset)
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=7)

    # Fetch suggestions for indicators
    all_suggestions = tenant_filter(MenuSuggestion.query).filter_by(floor=floor).all()
    suggestions_by_date = {}
    for sug in all_suggestions:
        if sug.date:
            date_str = sug.date.strftime('%Y-%m-%d')
            suggestions_by_date.setdefault(date_str, []).append(sug)
    
    # Fetch menus for target week
    weekly_menus = (
        tenant_filter(Menu.query)
        .options(joinedload(Menu.assigned_to), joinedload(Menu.assigned_team), joinedload(Menu.dish))
        .filter(Menu.floor == floor, Menu.date >= start_of_week, Menu.date < end_of_week)
        .all()
    )
    
    # Fetch all menus with pagination for history
    page = request.args.get('page', 1, type=int)
    menus_pagination = (
        tenant_filter(Menu.query)
        .options(joinedload(Menu.assigned_to), joinedload(Menu.assigned_team), joinedload(Menu.dish), joinedload(Menu.side_dish))
        .filter_by(floor=floor)
        .order_by(Menu.date.desc())
        .paginate(page=page, per_page=15, error_out=False)
    )
    floor_menus = menus_pagination.items
    
    weekly_days = []
    for i in range(7):
        day_date = start_of_week + timedelta(days=i)
        day_menus = [m for m in weekly_menus if m.date == day_date]
        weekly_days.append({
            "date": day_date,
            "is_today": day_date == today,
            "menus": day_menus
        })

    # Calculate if the UPCOMING week (starting next Monday) is already planned
    next_monday = (today - timedelta(days=today.weekday())) + timedelta(days=7)
    next_sunday = next_monday + timedelta(days=6)
    
    is_next_week_planned = (
        tenant_filter(Menu.query)
        .filter(Menu.floor == floor, Menu.date >= next_monday, Menu.date <= next_sunday)
        .first() is not None
    )

    pending_suggestions = tenant_filter(MenuSuggestion.query).options(
        joinedload(MenuSuggestion.suggested_by),
        joinedload(MenuSuggestion.dish),
        joinedload(MenuSuggestion.side_dish),
        joinedload(MenuSuggestion.suggested_team)
    ).filter(
        MenuSuggestion.floor == floor,
        MenuSuggestion.date >= today
    ).order_by(MenuSuggestion.date.asc()).all()

    return render_template(
        'menus.html', 
        menus=floor_menus,
        pagination=menus_pagination,
        weekly_days=weekly_days,
        is_next_week_planned=is_next_week_planned,
        pending_suggestions=pending_suggestions,
        floor_users=floor_users, 
        floor_teams=floor_teams, 
        floor_user_directory=floor_user_directory,
        team_members_by_team_id=team_members_by_team_id,
        main_dishes=main_dishes,
        side_dishes=side_dishes,
        dishes=all_dishes, 
        current_user=user,
        today=today,
        week_offset=week_offset,
        active_floor=floor
    )

@pantry_bp.route('/menus/suggestions/<int:suggestion_id>/delete', methods=['POST'])
def delete_menu_suggestion(suggestion_id):
    user = _require_user()
    if not user:
        abort(401)

    suggestion = tenant_filter(MenuSuggestion.query).filter_by(id=suggestion_id).first_or_404()

    # Permission: Admin, PantryHead, or the creator themselves
    is_creator = suggestion.suggested_by_id == user.id
    is_staff = user.role in ['admin', 'pantryHead']

    if not (is_creator or is_staff):
        abort(403)

    if suggestion.floor != _get_active_floor(user):
        abort(403)

    db.session.delete(suggestion)
    db.session.commit()

    if is_creator and not is_staff:
        flash('Your menu suggestion has been removed.', 'success')
    else:
        flash('Menu suggestion removed.', 'success')

    # Redirect back to where they came from
    referrer = request.referrer or ''
    if 'calendar' in referrer:
        return redirect(url_for('pantry.calendar'))
    return redirect(url_for('pantry.menus'))

@pantry_bp.route('/menus/<int:menu_id>/notify_single', methods=['POST'])
def send_single_menu_notification(menu_id):
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

    menu = tenant_filter(Menu.query).filter_by(id=menu_id).first_or_404()
    if user.role == 'pantryHead' and menu.floor != _get_active_floor(user):
        return jsonify({'status': 'error', 'message': 'Forbidden'}), 403

    data = request.get_json(silent=True) or {}
    recipient_id = data.get('user_id')
    try:
        recipient_id = int(recipient_id)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'user_id is required'}), 400

    eligible_recipients = _menu_notification_candidates(
        floor=menu.floor,
        assigned_to_id=menu.assigned_to_id,
        assigned_team_id=menu.assigned_team_id,
    )
    eligible_ids = {r.id for r in eligible_recipients}
    if recipient_id not in eligible_ids:
        return jsonify({'status': 'error', 'message': 'User is not eligible for this menu notification'}), 400

    recipient = tenant_filter(User.query).filter_by(id=recipient_id, floor=menu.floor).first()
    if not recipient:
        return jsonify({'status': 'error', 'message': 'Recipient not found'}), 404

    try:
        meal_label = menu.dish.name if menu.dish else menu.title
        if menu.side_dish:
            meal_label = f"{meal_label} + {menu.side_dish.name}"
        menu_date = menu.date.strftime('%d %b %Y') if menu.date else 'upcoming day'

        send_push_notification(
            user_id=recipient.id,
            title='New Meal Schedule',
            body=f"{meal_label} assigned for {menu_date}.",
            icon='/static/icons/icon-192.png',
            url='/menus',
        )

        if recipient.email:
            tenant_name = getattr(g, 'tenant_name', 'Maskan')
            email_subject = f"[{tenant_name}] Meal Assignment: {meal_label}"
            
            # Fetch dish estimation for premium display
            estimate_main = _estimate_payload_for(menu.dish) if menu.dish else None
            
            # Check if created by pantry head or admin for conditional instructions
            creator = menu.created_by
            is_created_by_pantry_head = creator and creator.role in ['pantryHead', 'admin']
            creator_name = (creator.full_name or creator.username) if creator else 'Chef'
            
            # Build estimation section HTML (ingredients table + tips)
            estimation_html = ""
            if estimate_main and estimate_main.get('available'):
                summary = estimate_main.get('summary', '').strip()
                ingredients = estimate_main.get('ingredients', []) or []
                tips = estimate_main.get('tips', []) or []
                serving_count = estimate_main.get('serving_count', 30)
                
                # Build ingredients table
                ingredients_table_html = ""
                if ingredients:
                    ingredients_rows = "".join([
                        f"<tr><td style=\"padding: 10px; border-bottom: 1px solid #e8e8e8; color: #333; font-size: 14px;\">{ing.get('name', '').strip()}</td>"
                        f"<td style=\"padding: 10px; border-bottom: 1px solid #e8e8e8; color: #333; text-align: center; font-size: 14px;\">{ing.get('qty', '')}</td>"
                        f"<td style=\"padding: 10px; border-bottom: 1px solid #e8e8e8; color: #333; font-size: 14px;\">{ing.get('unit', '').strip()}</td></tr>"
                        for ing in ingredients
                    ])
                    ingredients_table_html = f"""
                    <table style="width: 100%; border-collapse: collapse; margin: 15px 0; background-color: #fafbfc; border: 1px solid #e0e0e0; border-radius: 4px; overflow: hidden;">
                        <thead>
                            <tr style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;">
                                <th style="padding: 12px; text-align: left; font-weight: 600; font-size: 14px;">Ingredient</th>
                                <th style="padding: 12px; text-align: center; font-weight: 600; font-size: 14px;">Qty</th>
                                <th style="padding: 12px; text-align: left; font-weight: 600; font-size: 14px;">Unit</th>
                            </tr>
                        </thead>
                        <tbody>{ingredients_rows}</tbody>
                    </table>
                    <p style="font-size: 12px; color: #666; font-style: italic; margin: 8px 0; text-align: center;">Serves approximately {serving_count} people</p>
                    """
                
                # Build tips section
                tips_html = ""
                if tips:
                    tips_list = "".join([
                        f"<li style=\"margin: 8px 0; color: #333; font-size: 14px; line-height: 1.5;\">{tip.strip()}</li>"
                        for tip in tips
                    ])
                    tips_html = f"""
                    <div style="margin: 20px 0;">
                        <h4 style="color: #2c3e50; margin: 12px 0 15px 0; font-size: 15px; font-weight: 600;">💡 Cooking Tips</h4>
                        <ul style="margin: 0; padding-left: 20px; color: #333;">{tips_list}</ul>
                    </div>
                    """
                
                # Combine estimation section
                estimation_html = f"""
                <div style="background-color: #f0f8ff; border-left: 4px solid #667eea; padding: 20px; margin: 25px 0; border-radius: 4px; border: 1px solid #d4e9f7;">
                    <h3 style="color: #2c3e50; font-size: 18px; margin-top: 0; margin-bottom: 15px; font-weight: 600;">🍳 Dish Preparation Guide</h3>
                    {f'<p style="color: #666; font-style: italic; margin-bottom: 20px; line-height: 1.6; font-size: 14px;">{summary}</p>' if summary else ''}
                    {ingredients_table_html}
                    {tips_html}
                </div>
                """
            
            # Build pantry-head instructions section (conditional)
            pantry_head_section = ""
            if is_created_by_pantry_head:
                pantry_head_section = f"""
                <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; border-radius: 4px; border: 1px solid #ffeaa7;">
                    <h3 style="color: #856404; margin-top: 0; margin-bottom: 10px; font-size: 15px; font-weight: 600;">👨‍🍳 Chef's Special Instructions</h3>
                    <p style="color: #856404; font-size: 14px; margin: 8px 0; line-height: 1.5;">
                        This meal has been thoughtfully prepared by <strong>{creator_name}</strong> from your pantry team. 
                        Please refer to the preparation guide below for detailed ingredients and cooking tips.
                    </p>
                </div>
                """
            
            # Build complete premium email HTML
            email_html = f"""
            <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto; background-color: #f5f5f5; padding: 0;">
                <!-- Header with Gradient -->
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px 20px; text-align: center; color: white;">
                    <h1 style="margin: 0; font-size: 28px; font-weight: 600; letter-spacing: 0.5px;">Your Next Meal Assignment</h1>
                </div>
                
                <!-- Main Content -->
                <div style="background-color: white; padding: 30px 20px; margin: 15px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                    <!-- Meal Highlight -->
                    <div style="background: linear-gradient(to right, #f0f4f8, #ffffff); border-left: 5px solid #667eea; padding: 20px; border-radius: 4px; margin-bottom: 25px;">
                        <h2 style="color: #2c3e50; margin-top: 0; margin-bottom: 12px; font-size: 22px; font-weight: 600;">{meal_label}</h2>
                        <p style="margin: 8px 0; font-size: 15px; color: #666;"><strong>📅 Date:</strong> {menu_date}</p>
                        {f'<p style="margin: 8px 0; font-size: 14px; color: #666; line-height: 1.5;"><strong>📝 Description:</strong> {menu.description}</p>' if menu.description else ''}
                    </div>
                    
                    {pantry_head_section}
                    {estimation_html}
                    
                    <!-- Login Button (Prominent CTA) -->
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://140-245-12-63.sslip.io/login" style="display: inline-block; background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 16px 50px; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 600; box-shadow: 0 4px 12px rgba(40, 167, 69, 0.3); transition: transform 0.2s ease, box-shadow 0.2s ease; cursor: pointer;" onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 6px 16px rgba(40, 167, 69, 0.4)';" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 12px rgba(40, 167, 69, 0.3)';">
                            ✓ View Full Details on Dashboard
                        </a>
                    </div>
                </div>
                
                <!-- Footer -->
                <div style="background-color: #f5f5f5; padding: 20px; text-align: center; color: #888; font-size: 12px; line-height: 1.6;">
                    <p style="margin: 8px 0;">
                        This is an automated message from <strong>{tenant_name}</strong> pantry scheduling system.
                    </p>
                    <p style="margin: 8px 0; color: #aaa;">
                        © 2026 Pantry Management. All rights reserved.
                    </p>
                </div>
            </div>
            """
            email_sent = send_email_worker(recipient.email, email_subject, email_html)
            if not email_sent:
                return jsonify({'status': 'error', 'message': 'Email delivery failed'}), 500

            return jsonify({'status': 'success'})

        return jsonify({'status': 'warning', 'message': 'Recipient has no email address'})
    except Exception:
        return jsonify({'status': 'error', 'message': 'Failed to dispatch notification'}), 500

@pantry_bp.route('/menus/<int:menu_id>/delete', methods=['POST'])
def delete_menu(menu_id):
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    if user.role not in ['admin', 'pantryHead']:
        abort(403)

    menu = tenant_filter(Menu.query).filter_by(id=menu_id).first()
    if not menu:
        abort(404)
    if user.role == 'pantryHead' and menu.floor != user.floor:
        abort(404)

    db.session.delete(menu)
    db.session.commit()
    _clear_dashboard_cache(getattr(g, 'tenant_id', None), menu.floor)
    flash('Menu deleted successfully', 'success')
    return redirect(url_for('pantry.menus'))

@pantry_bp.route('/suggestions', methods=['GET', 'POST'])
def suggestions():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    if request.method == 'GET':
        return redirect(url_for('pantry.feedbacks') + '#suggestions')

    floor = _get_active_floor(user)
    dish_id = request.form.get('dish_id') or None
    if dish_id:
        try:
            dish_id_val = int(dish_id)
        except (TypeError, ValueError):
            dish_id_val = None
        dish_id = dish_id_val if dish_id_val and _active_dish_query().filter_by(id=dish_id_val).first() else None

    suggestion = Suggestion(
        title=(request.form.get('title') or '').strip(),
        description=(request.form.get('description') or '').strip(),
        dish_id=dish_id,
        user_id=user.id,
        floor=floor,
        tenant_id=getattr(g, 'tenant_id', None)
    )

    if not suggestion.title or not suggestion.description:
        flash('Please provide both a title and description for your suggestion.', 'error')
        return redirect(url_for('pantry.feedbacks') + '#suggestions')

    db.session.add(suggestion)
    db.session.commit()
    flash('Suggestion submitted successfully.', 'success')
    return redirect(url_for('pantry.feedbacks') + '#suggestions')

@pantry_bp.route('/menus/dish-insights/<int:dish_id>')
def get_dish_insights(dish_id):
    """
    Expert Intelligence: Returns rating, champion team, and top suggestions for a dish.
    """
    user = _require_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    floor = _get_active_floor(user)
    dish = Dish.query.filter_by(id=dish_id).first()
    if not dish:
        return jsonify({'error': 'Dish not found'}), 404

    # 1. Overall Avg Rating for this dish on this floor
    avg_rating = db.session.query(func.avg(Feedback.rating)).join(Menu).filter(
        Menu.dish_id == dish_id, 
        Menu.floor == floor
    ).scalar() or 0
    
    # 2. Dish Champion: The team with the highest avg rating for this SPECIFIC dish
    champion_row = (
        db.session.query(Team.name, func.avg(Feedback.rating).label('avg_score'))
        .join(Menu, Menu.assigned_team_id == Team.id)
        .join(Feedback, Feedback.menu_id == Menu.id)
        .filter(Menu.dish_id == dish_id, Menu.floor == floor)
        .group_by(Team.id)
        .order_by(func.avg(Feedback.rating).desc())
        .first()
    )
    
    champion_name = champion_row[0] if champion_row else "No champion yet"
    
    # 3. Top Suggestions: Sorted by votes
    # Use the same correlated subquery logic for stability
    vote_count_sub = db.session.query(func.count(SuggestionVote.id)).filter(SuggestionVote.suggestion_id == Suggestion.id).correlate(Suggestion).as_scalar()
    
    suggestions = (
        tenant_filter(db.session.query(Suggestion.description, vote_count_sub.label('v_count')))
        .filter(Suggestion.dish_id == dish_id, Suggestion.floor == floor)
        .order_by(vote_count_sub.desc())
        .limit(3)
        .all()
    )
    
    return jsonify({
        'avg_rating': round(float(avg_rating), 1),
        'champion': champion_name,
        'suggestions': [s[0] for s in suggestions],
        'estimate': _estimate_payload_for(dish),
    })

@pantry_bp.route('/suggestions/<int:suggestion_id>/vote', methods=['POST'])
def vote_suggestion(suggestion_id):
    user = _require_user()
    if not user:
        return ('', 401)

    suggestion = tenant_filter(Suggestion.query).filter_by(id=suggestion_id).first_or_404()
    if suggestion.floor != user.floor:
        abort(403)

    existing_vote = tenant_filter(SuggestionVote.query).filter_by(suggestion_id=suggestion_id, user_id=user.id).first()
    
    if existing_vote:
        # If user already voted, remove the vote (toggle)
        db.session.delete(existing_vote)
        db.session.commit()
        # Count votes explicitly after commit
        vote_count = tenant_filter(SuggestionVote.query).filter_by(suggestion_id=suggestion_id).count()
        return jsonify({"voted": False, "votes": vote_count})
    else:
        # Add new vote
        new_vote = SuggestionVote(suggestion_id=suggestion_id, user_id=user.id, tenant_id=getattr(g, 'tenant_id', None))
        db.session.add(new_vote)
        db.session.commit()
        # Count votes explicitly after commit
        vote_count = tenant_filter(SuggestionVote.query).filter_by(suggestion_id=suggestion_id).count()
        return jsonify({"voted": True, "votes": vote_count})

@pantry_bp.route('/suggestions/<int:suggestion_id>/delete', methods=['POST'])
def delete_suggestion(suggestion_id):
    user = _require_user()
    if not user:
        return ('', 401)

    if user.role not in {'admin', 'pantryHead'}:
        return ('', 403)

    suggestion = tenant_filter(Suggestion.query).filter_by(id=suggestion_id).first()
    if not suggestion:
        return ('', 404)

    if user.role == 'pantryHead' and suggestion.floor != user.floor:
        return ('', 403)

    db.session.delete(suggestion)
    db.session.commit()
    return ('', 204)

@pantry_bp.route('/people/teams/<int:team_id>/icon', methods=['POST'])
def update_team_icon(team_id):
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    team = tenant_filter(Team.query).filter_by(id=team_id).first()
    if not team:
        abort(404)

    # Verify user is a member of this team or has admin rights
    is_member = tenant_filter(TeamMember.query).filter_by(team_id=team.id, user_id=user.id).first() is not None
    if not is_member and user.role not in {'admin', 'pantryHead'}:
        abort(403, description="You must be a member of this team to edit its icon.")

    icon = (request.form.get('icon') or '').strip()
    
    # Optional basic validation/sanitization could go here
    if len(icon) > 10:
        icon = icon[:10]
        
    team.icon = icon if icon else None
    
    db.session.commit()
    flash(f"Room icon updated successfully", 'success')
    return redirect(url_for('pantry.people'))

@pantry_bp.route('/feedbacks', methods=['GET', 'POST'])
def feedbacks():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    floor = _get_active_floor(user)
    tenant_id = getattr(g, 'tenant_id', None)

    if request.method == 'POST':
        form_type = (request.form.get('form_type') or 'feedback').strip()

        if form_type == 'suggestion':
            title = (request.form.get('title') or '').strip()
            description = (request.form.get('description') or '').strip()
            dish_id = request.form.get('dish_id') or None
            if dish_id:
                try:
                    dish_id_val = int(dish_id)
                except (TypeError, ValueError):
                    dish_id_val = None
                dish_id = dish_id_val if dish_id_val and _active_dish_query().filter_by(id=dish_id_val).first() else None

            if not title or not description:
                flash('Please provide both a title and description for your suggestion.', 'error')
                return redirect(url_for('pantry.feedbacks') + '#suggestions')

            suggestion = Suggestion(
                title=title,
                description=description,
                dish_id=dish_id,
                user_id=user.id,
                floor=floor,
                tenant_id=tenant_id
            )
            db.session.add(suggestion)
            db.session.commit()
            flash('Suggestion submitted successfully.', 'success')
            return redirect(url_for('pantry.feedbacks') + '#suggestions')

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

        menu = tenant_filter(Menu.query).filter_by(id=menu_id_val).first()
        if not menu or menu.floor != floor:
            flash('Menu not found on this floor', 'error')
            return redirect(url_for('pantry.feedbacks'))

        if menu.date and menu.date > date.today():
            flash('You can only evaluate menus from today or earlier', 'error')
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

        existing = tenant_filter(Feedback.query).filter_by(menu_id=menu.id, user_id=user.id).first()
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
                tenant_id=tenant_id
            )
            db.session.add(feedback)

        db.session.commit()
        _clear_dashboard_cache(tenant_id, floor)
        flash('Evaluation saved successfully.', 'success')
        return redirect(url_for('pantry.feedbacks'))

    page = request.args.get('page', 1, type=int)
    
    feedbacks_pagination = (
        tenant_filter(Feedback.query)
        .options(joinedload(Feedback.user), joinedload(Feedback.menu).joinedload(Menu.dish))
        .filter_by(floor=floor)
        .order_by(Feedback.created_at.desc())
        .paginate(page=page, per_page=15, error_out=False)
    )
    visible_feedbacks = feedbacks_pagination.items

    today = date.today()
    menu_window_start = today - timedelta(days=14)
    menu_options = (
        tenant_filter(Menu.query).filter_by(floor=floor)
        .filter(Menu.date >= menu_window_start, Menu.date <= today)
        .order_by(Menu.date.desc())
        .limit(80)
        .all()
    )

    rated_menu_ids = {
        f.menu_id for f in tenant_filter(Feedback.query).filter_by(user_id=user.id).filter(Feedback.menu_id.isnot(None)).all()
    }

    dishes = _active_dish_query().order_by(func.lower(Dish.name).asc()).all()
    vote_count_subquery = (
        db.session.query(func.count(SuggestionVote.id))
        .filter(SuggestionVote.suggestion_id == Suggestion.id)
        .correlate(Suggestion)
        .as_scalar()
    )
    suggestions_with_votes = (
        tenant_filter(db.session.query(Suggestion, vote_count_subquery.label('vote_count')))
        .options(joinedload(Suggestion.user), joinedload(Suggestion.dish))
        .filter(Suggestion.floor == floor)
        .order_by(vote_count_subquery.desc(), Suggestion.created_at.desc())
        .all()
    )
    user_voted_ids = {v.suggestion_id for v in tenant_filter(SuggestionVote.query).filter_by(user_id=user.id).all()}

    return render_template(
        'feedbacks.html',
        feedbacks=visible_feedbacks,
        pagination=feedbacks_pagination,
        menu_options=menu_options,
        rated_menu_ids=rated_menu_ids,
        suggestions_with_votes=suggestions_with_votes,
        user_voted_ids=user_voted_ids,
        dishes=dishes,
        active_floor=floor,
        current_user=user
    )

@pantry_bp.route('/feedbacks/<int:feedback_id>/delete', methods=['POST'])
def delete_feedback(feedback_id):
    user = _require_user()
    if not user:
        return ('', 401)

    if user.role not in {'admin', 'pantryHead'}:
        return ('', 403)

    feedback = tenant_filter(Feedback.query).filter_by(id=feedback_id).first()
    if not feedback:
        return ('', 404)

    if user.role == 'pantryHead' and feedback.floor != user.floor:
        return ('', 403)

    db.session.delete(feedback)
    db.session.commit()
    _clear_dashboard_cache(getattr(g, 'tenant_id', None), feedback.floor)
    return ('', 204)
