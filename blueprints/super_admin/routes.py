from flask import render_template, request, redirect, url_for, session, flash, abort, g
from werkzeug.security import check_password_hash, generate_password_hash
from app import db
from models import User, Tenant, Dish, DishEstimate, DishAuditLog, Menu, TeaTask, ProcurementItem, Feedback, Expense, PlatformAudit, Budget, FloorLendBorrow, Suggestion, normalize_dish_name, TenantAuditLog
from . import super_admin_bp
from ..utils import require_super_admin, visible_budget_condition
from sqlalchemy import func, or_
from datetime import datetime, timedelta

def log_platform_action(action, description):
    audit = PlatformAudit(
        action=action,
        description=description,
        performed_by_id=session.get('user_id')
    )
    db.session.add(audit)
    db.session.commit()

def _super_admin_user():
    return User.query.get(session.get('user_id'))

def _log_dish_audit(action, description, dish=None, details=None, target_dish=None):
    user = _super_admin_user()
    db.session.add(DishAuditLog(
        action=action,
        dish_id=dish.id if dish else None,
        target_dish_id=target_dish.id if target_dish else None,
        description=description,
        details_json=details or {},
        performed_by_id=user.id if user else None,
        actor_tenant_id=user.tenant_id if user else None,
    ))

def _parse_ingredient_lines(raw_text):
    items = []
    for line in (raw_text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        if ':' in line:
            name, quantity = line.split(':', 1)
            items.append({'item': name.strip(), 'quantity': quantity.strip()})
        else:
            items.append({'item': line, 'quantity': ''})
    return items

def _parse_tip_lines(raw_text):
    return [line.strip() for line in (raw_text or '').splitlines() if line.strip()]

def _dish_reference_counts(dish_ids):
    if not dish_ids:
        return {}
    main_rows = db.session.query(Menu.dish_id, func.count(Menu.id)).filter(Menu.dish_id.in_(dish_ids)).group_by(Menu.dish_id).all()
    side_rows = db.session.query(Menu.side_dish_id, func.count(Menu.id)).filter(Menu.side_dish_id.in_(dish_ids)).group_by(Menu.side_dish_id).all()
    suggestion_rows = db.session.query(Suggestion.dish_id, func.count(Suggestion.id)).filter(Suggestion.dish_id.in_(dish_ids)).group_by(Suggestion.dish_id).all()
    counts = {dish_id: {'main_menus': 0, 'side_menus': 0, 'suggestions': 0} for dish_id in dish_ids}
    for dish_id, count in main_rows:
        counts.setdefault(dish_id, {'main_menus': 0, 'side_menus': 0, 'suggestions': 0})['main_menus'] = count
    for dish_id, count in side_rows:
        counts.setdefault(dish_id, {'main_menus': 0, 'side_menus': 0, 'suggestions': 0})['side_menus'] = count
    for dish_id, count in suggestion_rows:
        counts.setdefault(dish_id, {'main_menus': 0, 'side_menus': 0, 'suggestions': 0})['suggestions'] = count
    return counts

@super_admin_bp.route('/platform-admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username, role='super_admin').first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['role'] = 'super_admin'
            session.permanent = True
            log_platform_action('login', f'Super Admin {username} logged in.')
            return redirect(url_for('super_admin.dashboard'))
        
        flash('Invalid platform credentials', 'error')
    
    return render_template('super_admin/login.html')

@super_admin_bp.route('/platform-admin/dashboard')
def dashboard():
    require_super_admin()
    
    # 1. Platform-Wide KPIs
    total_tenants = Tenant.query.count()
    total_users = User.query.filter(User.tenant_id.isnot(None)).count()
    active_infrastructure = db.session.query(func.sum(Tenant.floor_count)).scalar() or 0
    
    # 2. Financial Utilization
    total_budget = db.session.query(func.sum(Budget.amount_allocated)).filter(
        visible_budget_condition()
    ).scalar() or 0
    total_spent_proc = db.session.query(func.sum(ProcurementItem.actual_cost)).filter(ProcurementItem.status == 'completed').scalar() or 0
    total_spent_legacy = db.session.query(func.sum(Expense.amount)).scalar() or 0
    total_spent = float(total_spent_proc or 0) + float(total_spent_legacy or 0)
    financial_utilization = (total_spent / float(total_budget) * 100) if total_budget and total_budget > 0 else 0

    # 3. Operational Completion Rate
    total_tea = TeaTask.query.count()
    completed_tea = TeaTask.query.filter_by(status='completed').count()
    total_proc = ProcurementItem.query.count()
    completed_proc = ProcurementItem.query.filter_by(status='completed').count()
    
    total_tasks = total_tea + total_proc
    completed_tasks = completed_tea + completed_proc
    completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    # 4. Satisfaction Index
    avg_rating = db.session.query(func.avg(Feedback.rating)).scalar() or 0
    
    # 5. Activity Heatbeat (Last 30 Days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    def get_daily_counts(model):
        return db.session.query(
            func.date(model.created_at), 
            func.count(model.id)
        ).filter(model.created_at >= thirty_days_ago)\
         .group_by(func.date(model.created_at)).all()

    activity_trend = {}
    for date_obj, count in get_daily_counts(Menu): activity_trend[str(date_obj)] = activity_trend.get(str(date_obj), 0) + count
    for date_obj, count in get_daily_counts(TeaTask): activity_trend[str(date_obj)] = activity_trend.get(str(date_obj), 0) + count
    for date_obj, count in get_daily_counts(ProcurementItem): activity_trend[str(date_obj)] = activity_trend.get(str(date_obj), 0) + count
    for date_obj, count in get_daily_counts(Feedback): activity_trend[str(date_obj)] = activity_trend.get(str(date_obj), 0) + count
    
    sorted_dates = sorted(activity_trend.keys())
    activity_labels = [datetime.strptime(d, '%Y-%m-%d').strftime('%b %d') for d in sorted_dates]
    activity_values = [activity_trend[d] for d in sorted_dates]

    # 6. Financial Category Breakdown
    categories = db.session.query(
        ProcurementItem.category, 
        func.sum(ProcurementItem.actual_cost)
    ).filter(ProcurementItem.status == 'completed')\
     .group_by(ProcurementItem.category).all()
    
    cat_labels = [c[0] for c in categories]
    cat_values = [float(c[1] or 0) for c in categories]

    # 7. Resource Sharing
    total_shared = FloorLendBorrow.query.filter(FloorLendBorrow.created_at >= thirty_days_ago).count()

    # 8. Tenant Performance Matrix & At-Risk
    tenants_list = Tenant.query.all()
    tenant_stats = []
    at_risk_tenants = []
    
    for t in tenants_list:
        u_count = User.query.filter_by(tenant_id=t.id).count()
        f_rating = db.session.query(func.avg(Feedback.rating)).filter_by(tenant_id=t.id).scalar() or 0
        t_spent_proc = db.session.query(func.sum(ProcurementItem.actual_cost)).filter_by(tenant_id=t.id, status='completed').scalar() or 0
        t_spent_legacy = db.session.query(func.sum(Expense.amount)).filter_by(tenant_id=t.id).scalar() or 0
        t_spent = float(t_spent_proc or 0) + float(t_spent_legacy or 0)
        
        last_activity = db.session.query(func.max(PlatformAudit.created_at)).filter_by(performed_by_id=User.id).join(User).filter(User.tenant_id == t.id).scalar()
        
        stat = {
            'id': t.id,
            'name': t.name,
            'users': u_count,
            'rating': round(float(f_rating), 1),
            'spent': t_spent
        }
        tenant_stats.append(stat)
        
        # At-Risk logic
        is_inactive = not last_activity or last_activity < (datetime.utcnow() - timedelta(days=7))
        if f_rating > 0 and f_rating < 3.0 or is_inactive:
            at_risk_tenants.append({
                'name': t.name,
                'reason': 'Low Satisfaction' if f_rating < 3.0 and f_rating > 0 else 'Inactivity',
                'id': t.id
            })

    stats = {
        'tenant_count': total_tenants,
        'user_count': total_users,
        'active_infra': active_infrastructure,
        'financial_util': round(financial_utilization, 1),
        'completion_rate': round(completion_rate, 1),
        'avg_rating': round(float(avg_rating), 1),
        'activity_labels': activity_labels,
        'activity_values': activity_values,
        'cat_labels': cat_labels,
        'cat_values': cat_values,
        'total_shared': total_shared,
        'tenant_matrix': tenant_stats
    }
    
    recent_tenants = Tenant.query.order_by(Tenant.created_at.desc()).limit(5).all()
    recent_audits = PlatformAudit.query.order_by(PlatformAudit.created_at.desc()).limit(10).all()
        
    return render_template('super_admin/dashboard.html', 
                           tenants=recent_tenants, 
                           stats=stats, 
                           audits=recent_audits,
                           at_risk=at_risk_tenants)

@super_admin_bp.route('/platform-admin/dishes')
def global_dishes():
    # Allow super_admins here; other roles should use the pantry menus flow.
    user = _super_admin_user()
    if not user:
        abort(403)
    if user.role != 'super_admin':
        if user.role in {'admin', 'pantryHead'}:
            flash('Use Menus to view and edit dish estimates.', 'success')
            return redirect(url_for('pantry.menus'))
        abort(403)

    q = (request.args.get('q') or '').strip()
    category = (request.args.get('category') or 'all').strip()
    status = (request.args.get('status') or 'active').strip()
    page = request.args.get('page', 1, type=int)

    query = Dish.query
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(func.lower(Dish.name).like(like), Dish.normalized_name.like(like)))
    if category in {'main', 'side', 'both'}:
        query = query.filter(Dish.category == category)
    if status == 'active':
        query = query.filter(Dish.is_archived == False)
    elif status == 'archived':
        query = query.filter(Dish.is_archived == True)

    dishes_pagination = query.order_by(Dish.is_archived.asc(), func.lower(Dish.name).asc()).paginate(
        page=page,
        per_page=40,
        error_out=False,
    )
    dishes = dishes_pagination.items
    dish_ids = [dish.id for dish in dishes]
    reference_counts = _dish_reference_counts(dish_ids)

    duplicate_rows = (
        db.session.query(Dish.normalized_name, func.count(Dish.id).label('dish_count'))
        .filter(Dish.is_archived == False, Dish.normalized_name.isnot(None), Dish.normalized_name != '')
        .group_by(Dish.normalized_name)
        .having(func.count(Dish.id) > 1)
        .order_by(func.count(Dish.id).desc(), Dish.normalized_name.asc())
        .limit(20)
        .all()
    )
    duplicate_groups = []
    for normalized_name, dish_count in duplicate_rows:
        group_dishes = (
            Dish.query
            .filter(Dish.is_archived == False, Dish.normalized_name == normalized_name)
            .order_by(Dish.id.asc())
            .all()
        )
        group_counts = _dish_reference_counts([dish.id for dish in group_dishes])
        duplicate_groups.append({
            'normalized_name': normalized_name,
            'dish_count': dish_count,
            'dishes': group_dishes,
            'counts': group_counts,
        })

    usage_rows = (
        db.session.query(Dish.id, Dish.name, func.count(Menu.id).label('menu_count'))
        .outerjoin(Menu, or_(Menu.dish_id == Dish.id, Menu.side_dish_id == Dish.id))
        .filter(Dish.is_archived == False)
        .group_by(Dish.id, Dish.name)
        .order_by(func.count(Menu.id).desc(), func.lower(Dish.name).asc())
        .limit(8)
        .all()
    )

    stats = {
        'total': Dish.query.count(),
        'active': Dish.query.filter(Dish.is_archived == False).count(),
        'archived': Dish.query.filter(Dish.is_archived == True).count(),
        'with_estimates': DishEstimate.query.count(),
        'duplicate_groups': len(duplicate_rows),
    }
    audit_logs = DishAuditLog.query.order_by(DishAuditLog.created_at.desc()).limit(20).all()

    return render_template(
        'super_admin/dishes.html',
        dishes=dishes,
        pagination=dishes_pagination,
        reference_counts=reference_counts,
        duplicate_groups=duplicate_groups,
        usage_rows=usage_rows,
        stats=stats,
        audit_logs=audit_logs,
        filters={'q': q, 'category': category, 'status': status},
    )

@super_admin_bp.route('/platform-admin/dishes/add', methods=['POST'])
def add_global_dish():
    require_super_admin()
    name = (request.form.get('name') or '').strip()
    category = (request.form.get('category') or 'main').strip()
    if category not in {'main', 'side', 'both'}:
        category = 'main'
    normalized_name = normalize_dish_name(name)

    if not name or not normalized_name:
        flash('Dish name is required.', 'error')
        return redirect(url_for('super_admin.global_dishes'))

    existing = Dish.query.filter(Dish.is_archived == False, Dish.normalized_name == normalized_name).first()
    if existing:
        flash(f'An active global dish named "{existing.name}" already exists.', 'error')
        return redirect(url_for('super_admin.global_dishes', q=name))

    user = _super_admin_user()
    dish = Dish(name=name, category=category, normalized_name=normalized_name, created_by_id=user.id if user else None)
    db.session.add(dish)
    db.session.flush()
    _log_dish_audit('create', f'Created global dish "{dish.name}".', dish=dish, details={'category': category})
    db.session.commit()
    flash('Global dish created.', 'success')
    return redirect(url_for('super_admin.global_dishes', q=name))

@super_admin_bp.route('/platform-admin/dishes/<int:dish_id>/edit', methods=['POST'])
def edit_global_dish(dish_id):
    require_super_admin()
    dish = Dish.query.get_or_404(dish_id)
    name = (request.form.get('name') or '').strip()
    category = (request.form.get('category') or dish.category or 'main').strip()
    if category not in {'main', 'side', 'both'}:
        category = dish.category or 'main'
    normalized_name = normalize_dish_name(name)

    if not name or not normalized_name:
        flash('Dish name is required.', 'error')
        return redirect(url_for('super_admin.global_dishes'))

    duplicate = (
        Dish.query
        .filter(Dish.id != dish.id, Dish.is_archived == False, Dish.normalized_name == normalized_name)
        .first()
    )
    if duplicate and not dish.is_archived:
        flash(f'Rename blocked because "{duplicate.name}" already uses that exact normalized name.', 'error')
        return redirect(url_for('super_admin.global_dishes', q=name))

    old_state = {'name': dish.name, 'category': dish.category, 'normalized_name': dish.normalized_name}
    dish.name = name
    dish.category = category
    dish.normalized_name = normalized_name
    _log_dish_audit('edit', f'Edited global dish "{dish.name}".', dish=dish, details={'before': old_state, 'after': {'name': name, 'category': category, 'normalized_name': normalized_name}})
    db.session.commit()
    flash('Global dish updated.', 'success')
    return redirect(url_for('super_admin.global_dishes', q=name))

@super_admin_bp.route('/platform-admin/dishes/<int:dish_id>/archive', methods=['POST'])
def archive_global_dish(dish_id):
    require_super_admin()
    dish = Dish.query.get_or_404(dish_id)
    archive = (request.form.get('archive') or '1') == '1'
    dish.is_archived = archive
    action = 'archive' if archive else 'unarchive'
    _log_dish_audit(action, f'{"Archived" if archive else "Restored"} global dish "{dish.name}".', dish=dish)
    db.session.commit()
    flash('Dish archived.' if archive else 'Dish restored.', 'success')
    return redirect(request.referrer or url_for('super_admin.global_dishes'))

@super_admin_bp.route('/platform-admin/dishes/<int:dish_id>/estimate', methods=['POST'])
def update_dish_estimate(dish_id):
    """Allow super_admin, admin, and pantryHead users to update dish estimates."""
    from app import db
    import json
    
    user = _super_admin_user()
    if not user:
        abort(403)
    
    # Allow super_admin globally, and tenant admin/pantryHead users within their tenant.
    if user.role not in {'super_admin', 'admin', 'pantryHead'}:
        abort(403)
    
    dish = Dish.query.get_or_404(dish_id)
    
    try:
        serving_count = int(request.form.get('serving_count') or 30)
    except ValueError:
        serving_count = 30
    serving_count = max(1, min(serving_count, 1000))

    summary = (request.form.get('summary') or '').strip()
    
    # Parse ingredients from JSON or fallback to text format
    ingredients = []
    ingredients_json_str = request.form.get('ingredients_json', '[]')
    try:
        ingredients = json.loads(ingredients_json_str)
        if not isinstance(ingredients, list):
            ingredients = []
    except (json.JSONDecodeError, ValueError):
        # Fallback to old text format
        ingredients = _parse_ingredient_lines(request.form.get('ingredients_text', ''))
    
    # Parse tips from JSON or fallback to text format
    tips = []
    tips_json_str = request.form.get('tips_json', '[]')
    try:
        tips = json.loads(tips_json_str)
        if not isinstance(tips, list):
            tips = []
    except (json.JSONDecodeError, ValueError):
        # Fallback to old text format
        tips = _parse_tip_lines(request.form.get('tips_text', ''))

    estimate = dish.estimate
    if not estimate:
        estimate = DishEstimate(dish=dish)
        db.session.add(estimate)

    estimate.serving_count = serving_count
    estimate.summary = summary
    estimate.ingredients_json = ingredients
    estimate.tips_json = tips
    estimate.updated_by_id = user.id if user else None
    estimate.updated_by_tenant_id = user.tenant_id if user else None
    
    _log_dish_audit(
        'estimate_update',
        f'Updated estimate for "{dish.name}".{"" if user.role == "super_admin" else " (Edited by Pantry Head)"}',
        dish=dish,
        details={
            'serving_count': serving_count,
            'ingredient_count': len(ingredients),
            'tip_count': len(tips),
            'edited_by_role': user.role,
        },
    )
    db.session.commit()
    flash('Dish estimate updated.', 'success')
    return redirect(url_for('super_admin.global_dishes', q=dish.name))

@super_admin_bp.route('/platform-admin/dishes/merge/preview', methods=['POST'])
def preview_dish_merge():
    require_super_admin()
    try:
        canonical_id = int(request.form.get('canonical_id') or 0)
    except ValueError:
        canonical_id = 0
    source_ids = []
    for raw_id in request.form.getlist('source_ids'):
        try:
            source_ids.append(int(raw_id))
        except ValueError:
            continue
    source_ids = sorted({source_id for source_id in source_ids if source_id != canonical_id})

    canonical = Dish.query.get(canonical_id)
    sources = Dish.query.filter(Dish.id.in_(source_ids)).order_by(Dish.id.asc()).all() if source_ids else []
    if not canonical or not sources:
        flash('Choose one canonical dish and at least one duplicate to merge.', 'error')
        return redirect(url_for('super_admin.global_dishes'))

    counts = _dish_reference_counts([dish.id for dish in sources])
    totals = {
        'main_menus': sum(c['main_menus'] for c in counts.values()),
        'side_menus': sum(c['side_menus'] for c in counts.values()),
        'suggestions': sum(c['suggestions'] for c in counts.values()),
    }
    return render_template(
        'super_admin/dish_merge_preview.html',
        canonical=canonical,
        sources=sources,
        counts=counts,
        totals=totals,
    )

@super_admin_bp.route('/platform-admin/dishes/merge/confirm', methods=['POST'])
def confirm_dish_merge():
    require_super_admin()
    try:
        canonical_id = int(request.form.get('canonical_id') or 0)
    except ValueError:
        canonical_id = 0
    source_ids = []
    for raw_id in request.form.getlist('source_ids'):
        try:
            source_ids.append(int(raw_id))
        except ValueError:
            continue
    source_ids = sorted({source_id for source_id in source_ids if source_id != canonical_id})

    canonical = Dish.query.get(canonical_id)
    sources = Dish.query.filter(Dish.id.in_(source_ids)).order_by(Dish.id.asc()).all() if source_ids else []
    if not canonical or not sources:
        flash('Merge confirmation failed because the selected dishes were not found.', 'error')
        return redirect(url_for('super_admin.global_dishes'))

    main_count = Menu.query.filter(Menu.dish_id.in_(source_ids)).update({Menu.dish_id: canonical.id}, synchronize_session=False)
    side_count = Menu.query.filter(Menu.side_dish_id.in_(source_ids)).update({Menu.side_dish_id: canonical.id}, synchronize_session=False)
    suggestion_count = Suggestion.query.filter(Suggestion.dish_id.in_(source_ids)).update({Suggestion.dish_id: canonical.id}, synchronize_session=False)
    canonical.is_archived = False

    for source in sources:
        source.is_archived = True
        _log_dish_audit(
            'merge',
            f'Merged "{source.name}" into canonical dish "{canonical.name}".',
            dish=source,
            target_dish=canonical,
            details={
                'canonical_id': canonical.id,
                'main_menus_updated': main_count,
                'side_menus_updated': side_count,
                'suggestions_updated': suggestion_count,
            },
        )

    _log_dish_audit(
        'merge_canonical',
        f'Selected "{canonical.name}" as canonical dish for {len(sources)} duplicate(s).',
        dish=canonical,
        details={'source_ids': source_ids},
    )
    db.session.commit()
    flash(f'Merge complete. Updated {main_count + side_count} menu references and {suggestion_count} suggestions.', 'success')
    return redirect(url_for('super_admin.global_dishes', q=canonical.name))

@super_admin_bp.route('/platform-admin/tenants')
def tenants_list():
    require_super_admin()
    all_tenants = Tenant.query.order_by(Tenant.name.asc()).all()
    for t in all_tenants:
        t.user_count = User.query.filter_by(tenant_id=t.id).count()
        t.activity_count = Menu.query.filter_by(tenant_id=t.id).count() + ProcurementItem.query.filter_by(tenant_id=t.id).count()
    
    return render_template('super_admin/tenants.html', tenants=all_tenants)

@super_admin_bp.route('/platform-admin/tenants/<uuid:tenant_id>')
def tenant_detail(tenant_id):
    require_super_admin()
    tenant = Tenant.query.get_or_404(tenant_id)
    users = User.query.filter_by(tenant_id=tenant_id).order_by(User.role.asc()).all()
    faculty_users = User.query.filter_by(tenant_id=tenant_id, role='faculty').order_by(User.created_at.asc()).all()
    
    floor_stats = []
    for f in range(1, tenant.floor_count + 1):
        u_count = User.query.filter_by(tenant_id=tenant_id, floor=f).count()
        m_count = Menu.query.filter_by(tenant_id=tenant_id, floor=f).count()
        floor_stats.append({'floor': f, 'users': u_count, 'menus': m_count})
        
    return render_template('super_admin/tenant_view.html', tenant=tenant, users=users, floor_stats=floor_stats, faculty_users=faculty_users)

@super_admin_bp.route('/platform-admin/tenants/provision', methods=['POST'])
def provision_tenant():
    require_super_admin()
    name = request.form.get('name')
    floor_count = int(request.form.get('floor_count', 11))
    
    admin_username = request.form.get('admin_username')
    admin_email = request.form.get('admin_email')
    admin_password = request.form.get('admin_password')

    if User.query.filter((User.username == admin_username) | (User.email == admin_email)).first():
        flash('Admin username or email already exists.', 'error')
        return redirect(url_for('super_admin.dashboard'))

    try:
        new_tenant = Tenant(name=name, floor_count=floor_count)
        db.session.add(new_tenant)
        db.session.flush()
        
        new_admin = User(
            username=admin_username, email=admin_email,
            password_hash=generate_password_hash(admin_password),
            role='admin', floor=1, is_verified=True, is_first_login=False,
            tenant_id=new_tenant.id
        )
        db.session.add(new_admin)
        db.session.commit()
        log_platform_action('provision_tenant', f'Provisioned tenant "{name}" with admin "{admin_username}".')
        flash(f'Successfully provisioned {name}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Provisioning Error: {str(e)}', 'error')
        
    return redirect(url_for('super_admin.dashboard'))

@super_admin_bp.route('/platform-admin/tenants/<uuid:tenant_id>/config', methods=['POST'])
def update_config(tenant_id):
    require_super_admin()
    tenant = Tenant.query.get_or_404(tenant_id)
    old_floors = tenant.floor_count
    old_faculty_workflow = bool(getattr(tenant, 'faculty_workflow_enabled', True))
    tenant.floor_count = int(request.form.get('floor_count'))
    tenant.subscription_status = request.form.get('subscription_status')
    tenant.faculty_workflow_enabled = '1' in request.form.getlist('faculty_workflow_enabled')
    db.session.commit()
    log_platform_action(
        'config_update',
        (
            f'Updated tenant "{tenant.name}": Floors {old_floors}->{tenant.floor_count}, '
            f'Tier: {tenant.subscription_status}, '
            f'Faculty workflow {old_faculty_workflow}->{tenant.faculty_workflow_enabled}'
        )
    )
    flash('Configuration updated', 'success')
    return redirect(url_for('super_admin.tenant_detail', tenant_id=tenant_id))

@super_admin_bp.route('/platform-admin/tenants/<uuid:tenant_id>/toggle', methods=['POST'])
def toggle_tenant(tenant_id):
    require_super_admin()
    tenant = Tenant.query.get_or_404(tenant_id)
    tenant.is_active = not tenant.is_active
    status = "Active" if tenant.is_active else "Suspended"
    log_platform_action('toggle_tenant', f'Set tenant "{tenant.name}" to {status}.')
    db.session.commit()
    return redirect(request.referrer or url_for('super_admin.dashboard'))


@super_admin_bp.route('/platform-admin/tenants/<uuid:tenant_id>/faculty', methods=['POST'])
def manage_faculty(tenant_id):
    require_super_admin()
    tenant = Tenant.query.get_or_404(tenant_id)
    if not getattr(tenant, 'faculty_workflow_enabled', True):
        flash('Enable the Faculty workflow for this tenant before provisioning or updating Faculty accounts.', 'error')
        return redirect(url_for('super_admin.tenant_detail', tenant_id=tenant_id))

    action = (request.form.get('action') or 'provision').strip()
    faculty_user_id = request.form.get('faculty_user_id')
    faculty_user = None
    if faculty_user_id:
        try:
            faculty_user = User.query.filter_by(id=int(faculty_user_id), tenant_id=tenant_id, role='faculty').first()
        except (TypeError, ValueError):
            faculty_user = None

    email = (request.form.get('faculty_email') or '').strip()
    if email and '@' not in email:
        email = f"{email}@jameasaifiyah.edu"
    password = (request.form.get('faculty_password') or '').strip()
    full_name = (request.form.get('faculty_name') or '').strip() or None
    tr_number = (request.form.get('faculty_tr_number') or '').strip() or None

    if action == 'provision':
        if not email or not password:
            flash('Faculty email and password are required.', 'error')
            return redirect(url_for('super_admin.tenant_detail', tenant_id=tenant_id))
        if User.query.filter(User.email == email).first():
            flash('That Faculty email is already in use.', 'error')
            return redirect(url_for('super_admin.tenant_detail', tenant_id=tenant_id))
        if tr_number and User.query.filter(User.tr_number == tr_number).first():
            flash('That Faculty TR number is already in use.', 'error')
            return redirect(url_for('super_admin.tenant_detail', tenant_id=tenant_id))

        faculty_user = User(
            email=email,
            password_hash=generate_password_hash(password),
            role='faculty',
            floor=None,
            is_verified=True,
            is_first_login=True,
            full_name=full_name,
            tr_number=tr_number,
            tenant_id=tenant.id,
        )
        db.session.add(faculty_user)
        db.session.commit()
        log_platform_action('provision_faculty', f'Provisioned Faculty account "{email}" for tenant "{tenant.name}".')
        flash('Faculty account provisioned successfully.', 'success')
        return redirect(url_for('super_admin.tenant_detail', tenant_id=tenant_id))

    if action == 'reset_password':
        if not faculty_user:
            flash('No Faculty account exists for this tenant yet.', 'error')
            return redirect(url_for('super_admin.tenant_detail', tenant_id=tenant_id))
        if not password:
            flash('Please provide a new Faculty password.', 'error')
            return redirect(url_for('super_admin.tenant_detail', tenant_id=tenant_id))

        faculty_user.password_hash = generate_password_hash(password)
        faculty_user.is_first_login = True
        if email and email != faculty_user.email:
            if User.query.filter(User.email == email, User.id != faculty_user.id).first():
                flash('That Faculty email is already in use.', 'error')
                return redirect(url_for('super_admin.tenant_detail', tenant_id=tenant_id))
            faculty_user.email = email
        if tr_number and tr_number != faculty_user.tr_number:
            if User.query.filter(User.tr_number == tr_number, User.id != faculty_user.id).first():
                flash('That Faculty TR number is already in use.', 'error')
                return redirect(url_for('super_admin.tenant_detail', tenant_id=tenant_id))
            faculty_user.tr_number = tr_number
        faculty_user.full_name = full_name or faculty_user.full_name
        db.session.commit()
        log_platform_action('reset_faculty_password', f'Reset Faculty password for tenant "{tenant.name}".')
        flash('Faculty password reset successfully.', 'success')
        return redirect(url_for('super_admin.tenant_detail', tenant_id=tenant_id))

    flash('Invalid Faculty action.', 'error')
    return redirect(url_for('super_admin.tenant_detail', tenant_id=tenant_id))

from sqlalchemy.orm import joinedload

@super_admin_bp.route('/platform-admin/logs')
def tenant_audit_logs():
    require_super_admin()
    
    tenant_id_filter = request.args.get('tenant_id')
    action_filter = request.args.get('action')
    page = request.args.get('page', 1, type=int)
    
    query = TenantAuditLog.query.options(joinedload(TenantAuditLog.tenant), joinedload(TenantAuditLog.actor_user))
    
    if tenant_id_filter:
        query = query.filter(TenantAuditLog.tenant_id == tenant_id_filter)
    if action_filter:
        query = query.filter(TenantAuditLog.action == action_filter)
        
    logs_pagination = query.order_by(TenantAuditLog.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    
    # Analytics / Trends
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # Total logs
    total_logs = TenantAuditLog.query.count()
    
    # Action distribution
    action_counts = db.session.query(
        TenantAuditLog.action, func.count(TenantAuditLog.id)
    ).group_by(TenantAuditLog.action).all()
    action_labels = [a[0] for a in action_counts]
    action_values = [a[1] for a in action_counts]
    
    # Daily trend over last 30 days
    daily_counts = db.session.query(
        func.date(TenantAuditLog.created_at), func.count(TenantAuditLog.id)
    ).filter(TenantAuditLog.created_at >= thirty_days_ago)\
     .group_by(func.date(TenantAuditLog.created_at)).all()
     
    trend_dict = {}
    for date_obj, count in daily_counts:
        trend_dict[str(date_obj)] = count
        
    sorted_dates = sorted(trend_dict.keys())
    trend_labels = [datetime.strptime(d, '%Y-%m-%d').strftime('%b %d') for d in sorted_dates]
    trend_values = [trend_dict[d] for d in sorted_dates]
    
    tenants = Tenant.query.order_by(Tenant.name.asc()).all()
    actions = [a[0] for a in db.session.query(TenantAuditLog.action).distinct().all()]
    
    stats = {
        'total_logs': total_logs,
        'action_labels': action_labels,
        'action_values': action_values,
        'trend_labels': trend_labels,
        'trend_values': trend_values
    }
    
    return render_template(
        'super_admin/logs.html',
        pagination=logs_pagination,
        stats=stats,
        tenants=tenants,
        actions=actions,
        filters={'tenant_id': tenant_id_filter, 'action': action_filter}
    )
