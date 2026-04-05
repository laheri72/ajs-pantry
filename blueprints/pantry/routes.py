from flask import render_template, request, redirect, url_for, session, flash, abort, jsonify, g
from app import db
from models import User, Dish, Menu, Feedback, Request, ProcurementItem, Team, TeamMember, TeaTask, FloorLendBorrow, SpecialEvent, Announcement, Suggestion, SuggestionVote, Expense, Budget
from datetime import datetime, date, timedelta
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload
from . import pantry_bp
from ..utils import (
    _require_user,
    _get_active_floor,
    _require_staff_for_floor,
    _display_name_for,
    tenant_filter,
    send_push_notification,
    send_email_notification,
    FLOOR_MIN,
    FLOOR_MAX
)

@pantry_bp.route('/dashboard')
def dashboard():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    floor = _get_active_floor(user)
    
    # IST is UTC+5:30
    now_utc = datetime.utcnow()
    ist_now = now_utc + timedelta(hours=5, minutes=30)
    today = ist_now.date()
    
    upcoming_until = today + timedelta(days=2)
    since_dt = now_utc - timedelta(days=2)
    stars_since_dt = now_utc - timedelta(days=7)
    
    # Stats and restricted data
    is_privileged = user.role in ['admin', 'pantryHead']
    pending_lend_borrow_count = 0
    weekly_expenses = 0

    if is_privileged:
        # Total spent: Legacy Expenses + Billed Procurement Costs
        total_spent_proc = tenant_filter(db.session.query(func.sum(ProcurementItem.actual_cost))).filter(
            ProcurementItem.floor == floor, 
            ProcurementItem.status == 'completed',
            ProcurementItem.bill_id.isnot(None)
        ).scalar() or 0
        total_spent_legacy = tenant_filter(db.session.query(func.sum(Expense.amount))).filter(Expense.floor == floor).scalar() or 0
        weekly_expenses = float(total_spent_proc) + float(total_spent_legacy)

        # Pending Lend/Borrow for this floor (either as lender or borrower)
        pending_lend_borrow_count = tenant_filter(FloorLendBorrow.query).filter(
            or_(FloorLendBorrow.lender_floor == floor, FloorLendBorrow.borrower_floor == floor),
            FloorLendBorrow.status == 'pending'
        ).count()

    stats = {
        'user_count': tenant_filter(User.query).filter_by(floor=floor).count(),
        'pending_requests': tenant_filter(Request.query).filter_by(floor=floor, status='pending').count(),
        'weekly_expenses': weekly_expenses,
        'stars_7d': int(
            (
                tenant_filter(db.session.query(func.coalesce(func.sum(Feedback.rating), 0)))
                .filter(Feedback.floor == floor, Feedback.created_at >= stars_since_dt, Feedback.menu_id.isnot(None))
                .scalar()
            )
            or 0
        ),
    }

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

    top_team_row = (
        tenant_filter(db.session.query(Menu.assigned_team_id.label('team_id'), func.sum(Feedback.rating).label('stars')))
        .join(Feedback, Feedback.menu_id == Menu.id)
        .filter(Menu.floor == floor, Feedback.created_at >= stars_since_dt, Menu.assigned_team_id.isnot(None))
        .group_by(Menu.assigned_team_id)
        .order_by(func.sum(Feedback.rating).desc())
        .first()
    )
    if top_team_row and top_team_row.team_id:
        t = tenant_filter(Team.query).filter_by(id=top_team_row.team_id).first()
        stats['top_team_7d'] = f"{(t.icon or '').strip()} {(t.name or '').strip()}".strip() if t else None
    else:
        stats['top_team_7d'] = None

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
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        # Get all budgets that overlap with the current week
        active_budgets = tenant_filter(Budget.query).filter(
            Budget.floor == floor,
            Budget.start_date <= end_of_week,
            or_(Budget.end_date >= start_of_week, Budget.end_date.is_(None))
        ).all()
        
        if active_budgets:
            total_allocated = sum(float(b.amount_allocated) for b in active_budgets)
            
            # Spent this week: Legacy Expenses + Finalized Procurement
            spent_proc = tenant_filter(db.session.query(func.sum(ProcurementItem.actual_cost))).filter(
                ProcurementItem.floor == floor,
                ProcurementItem.status == 'completed',
                ProcurementItem.bill_id.isnot(None),
                ProcurementItem.expense_recorded_at >= datetime.combine(start_of_week, datetime.min.time())
            ).scalar() or 0
            
            spent_legacy = tenant_filter(db.session.query(func.sum(Expense.amount))).filter(
                Expense.floor == floor,
                Expense.date >= start_of_week
            ).scalar() or 0
            
            total_spent = float(spent_proc) + float(spent_legacy)
            
            if total_allocated > 0:
                morning_brief['budget_usage_pct'] = min(100, round((total_spent / total_allocated) * 100))
            
            # Days remaining in the current week or until the earliest end_date
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
            
            if not dish_id and not new_dish_name: continue 

            # Handle Main Dish creation
            if not dish_id and new_dish_name:
                existing = tenant_filter(Dish.query).filter(func.lower(Dish.name) == new_dish_name.lower()).first()
                if existing:
                    dish_id = existing.id
                else:
                    new_dish = Dish(name=new_dish_name, category='main', created_by_id=user.id, tenant_id=getattr(g, 'tenant_id', None))
                    db.session.add(new_dish)
                    db.session.flush()
                    dish_id = new_dish.id

            # Handle Side Dish creation
            side_dish_id = item.get('side_dish_id')
            if isinstance(side_dish_id, str) and side_dish_id.strip():
                try: side_dish_id = int(side_dish_id)
                except: side_dish_id = None
            else: side_dish_id = None if not side_dish_id else side_dish_id

            new_side_dish_name = item.get('new_side_dish_name')
            if not side_dish_id and new_side_dish_name:
                existing_side = tenant_filter(Dish.query).filter(func.lower(Dish.name) == new_side_dish_name.lower()).first()
                if existing_side:
                    side_dish_id = existing_side.id
                else:
                    new_side = Dish(name=new_side_dish_name, category='side', created_by_id=user.id, tenant_id=getattr(g, 'tenant_id', None))
                    db.session.add(new_side)
                    db.session.flush()
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
            
            dish_obj = tenant_filter(Dish.query).filter_by(id=dish_id).first() if dish_id else None
            side_obj = tenant_filter(Dish.query).filter_by(id=side_dish_id).first() if side_dish_id else None
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
    users = tenant_filter(User.query).filter_by(floor=floor).all()
    users.sort(key=lambda u: (u.full_name or u.username or u.email or "").lower())
    teams = tenant_filter(Team.query).filter_by(floor=floor).order_by(Team.name.asc()).all()

    team_memberships = tenant_filter(TeamMember.query).options(joinedload(TeamMember.user)).join(Team, TeamMember.team_id == Team.id).filter(Team.floor == floor).all()
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
        tenant_filter(db.session.query(
            Team.id.label('team_id'),
            Team.name.label('team_name'),
            Team.icon.label('team_icon'),
            func.coalesce(func.sum(Feedback.rating), 0).label('stars'),
            func.count(Feedback.id).label('ratings_count'),
            func.coalesce(func.avg(Feedback.rating), 0).label('avg_rating'),
        ))
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
        tenant_filter(db.session.query(
            User.id.label('user_id'),
            User.full_name.label('full_name'),
            User.username.label('username'),
            User.email.label('email'),
            func.coalesce(func.sum(Feedback.rating), 0).label('stars'),
            func.count(Feedback.id).label('ratings_count'),
            func.coalesce(func.avg(Feedback.rating), 0).label('avg_rating'),
        ))
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
        tenant_filter(db.session.query(
            dish_name_expr.label('dish_name'),
            func.coalesce(func.sum(Feedback.rating), 0).label('stars'),
            func.count(Feedback.id).label('ratings_count'),
            func.coalesce(func.avg(Feedback.rating), 0).label('avg_rating'),
        ))
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
        tenant_filter(db.session.query(
            dish_name_expr.label('dish_name'),
            Team.id.label('team_id'),
            Team.name.label('team_name'),
            Team.icon.label('team_icon'),
            func.coalesce(func.sum(Feedback.rating), 0).label('stars'),
        ))
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

    return render_template('calendar.html', 
                           menus=menus, 
                           tea_tasks=tea_tasks, 
                           special_events=special_events, 
                           current_user=user, 
                           active_floor=floor,
                           current_year=current_year,
                           current_month=current_month)

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
    floor_users = tenant_filter(User.query).filter_by(floor=floor).all()
    floor_teams = tenant_filter(Team.query).filter_by(floor=floor).order_by(Team.name.asc()).all()
    
    # Standardize on 'Dish' (singular) as per models.py
    main_dishes = tenant_filter(Dish.query).filter(Dish.category.in_(['main', 'both'])).order_by(func.lower(Dish.name).asc()).all()
    side_dishes = tenant_filter(Dish.query).filter(Dish.category.in_(['side', 'both'])).order_by(func.lower(Dish.name).asc()).all()
    all_dishes = tenant_filter(Dish.query).order_by(func.lower(Dish.name).asc()).all()

    if request.method == 'POST' and user.role in ['admin', 'pantryHead']:
        try:
            menu_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
            meal_type = request.form.get('meal_type', 'breakfast')
        except Exception:
            flash('Invalid menu date or type', 'error')
            return redirect(url_for('pantry.menus'))

        # Prevention: Check if this meal time is already scheduled for this date
        existing_meal = tenant_filter(Menu.query).filter_by(floor=floor, date=menu_date, meal_type=meal_type).first()
        if existing_meal:
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
                flash('Invalid dish selected', 'error')
                return redirect(url_for('pantry.menus'))
            dish = tenant_filter(Dish.query).filter_by(id=dish_id_val).first()
        elif new_dish_name:
            existing = tenant_filter(Dish.query).filter(func.lower(Dish.name) == new_dish_name.lower()).first()
            if existing:
                dish = existing
            else:
                dish = Dish(name=new_dish_name, category='main', created_by_id=user.id, tenant_id=getattr(g, 'tenant_id', None))
                db.session.add(dish)
                db.session.flush()
        else:
            flash('Please select a main dish', 'error')
            return redirect(url_for('pantry.menus'))

        # Side Dish
        side_dish_id = request.form.get('side_dish_id') or None
        new_side_dish_name = (request.form.get('new_side_dish_name') or '').strip()

        if new_side_dish_name:
            existing_side = tenant_filter(Dish.query).filter(func.lower(Dish.name) == new_side_dish_name.lower()).first()
            if existing_side:
                side_dish_id = existing_side.id
            else:
                side_dish = Dish(name=new_side_dish_name, category='side', created_by_id=user.id, tenant_id=getattr(g, 'tenant_id', None))
                db.session.add(side_dish)
                db.session.flush()
                side_dish_id = side_dish.id
        elif side_dish_id:
            try:
                side_dish_id = int(side_dish_id)
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
            flash('Assigned team must be on your floor', 'error')
            assigned_team_id = None

        if assigned_team_id:
            assigned_to_id = None

        if assigned_to_id and not tenant_filter(User.query).filter_by(id=assigned_to_id, floor=floor).first():
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
            created_by_id=user.id,
            tenant_id=getattr(g, 'tenant_id', None)
        )
        db.session.add(menu)
        db.session.commit()

        if assigned_to_id:
            send_push_notification(
                user_id=assigned_to_id,
                title="New Menu Assignment",
                body=f"You have been assigned to prepare: {menu_title}.",
                icon="/static/icons/icon-192.png",
                url="/menus"
            )

        flash('Menu added successfully', 'success')
        return redirect(url_for('pantry.menus'))

    # Prepare Weekly View Data
    week_offset = request.args.get('week_offset', 0, type=int)
    today = date.today()
    target_date = today + timedelta(weeks=week_offset)
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=7)
    
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

    return render_template(
        'menus.html', 
        menus=floor_menus,
        pagination=menus_pagination,
        weekly_days=weekly_days,
        is_next_week_planned=is_next_week_planned,
        floor_users=floor_users, 
        floor_teams=floor_teams, 
        main_dishes=main_dishes,
        side_dishes=side_dishes,
        dishes=all_dishes, 
        current_user=user,
        today=today,
        week_offset=week_offset,
        active_floor=floor
    )

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
    flash('Menu deleted successfully', 'success')
    return redirect(url_for('pantry.menus'))

@pantry_bp.route('/suggestions', methods=['GET', 'POST'])
def suggestions():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    floor = _get_active_floor(user)
    dishes = tenant_filter(Dish.query).order_by(func.lower(Dish.name).asc()).all()

    if request.method == 'POST':
        suggestion = Suggestion(
            title=request.form.get('title'),
            description=request.form.get('description'),
            dish_id=request.form.get('dish_id') or None,
            user_id=user.id,
            floor=floor,
            tenant_id=getattr(g, 'tenant_id', None)
        )
        db.session.add(suggestion)
        db.session.commit()
        flash('Suggestion submitted successfully.', 'success')
        return redirect(url_for('pantry.suggestions'))

    # Correlated subquery for vote counts to avoid GROUP BY issues with joinedload
    vote_count_subquery = (
        db.session.query(func.count(SuggestionVote.id))
        .filter(SuggestionVote.suggestion_id == Suggestion.id)
        .correlate(Suggestion)
        .as_scalar()
    )

    # Fetch suggestions with relationships and vote count
    suggestions_with_votes = (
        tenant_filter(db.session.query(Suggestion, vote_count_subquery.label('vote_count')))
        .options(joinedload(Suggestion.user), joinedload(Suggestion.dish))
        .filter(Suggestion.floor == floor)
        .order_by(vote_count_subquery.desc(), Suggestion.created_at.desc())
        .all()
    )

    # Get the IDs of suggestions the current user has voted for
    user_voted_ids = {v.suggestion_id for v in tenant_filter(SuggestionVote.query).filter_by(user_id=user.id).all()}

    return render_template(
        'suggestions.html', 
        suggestions_with_votes=suggestions_with_votes, 
        user_voted_ids=user_voted_ids,
        current_user=user,
        dishes=dishes,
        active_floor=floor
    )

@pantry_bp.route('/menus/dish-insights/<int:dish_id>')
def get_dish_insights(dish_id):
    """
    Expert Intelligence: Returns rating, champion team, and top suggestions for a dish.
    """
    user = _require_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    floor = _get_active_floor(user)

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
        'suggestions': [s[0] for s in suggestions]
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
                tenant_id=getattr(g, 'tenant_id', None)
            )
            db.session.add(feedback)

        db.session.commit()
        flash('Evaluation saved successfully.', 'success')
        return redirect(url_for('pantry.feedbacks'))

    floor = _get_active_floor(user)
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

    return render_template('feedbacks.html', feedbacks=visible_feedbacks, pagination=feedbacks_pagination, menu_options=menu_options, rated_menu_ids=rated_menu_ids, current_user=user)

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
    return ('', 204)
