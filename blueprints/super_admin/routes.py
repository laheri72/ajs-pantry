from flask import render_template, request, redirect, url_for, session, flash, abort, g
from werkzeug.security import check_password_hash, generate_password_hash
from app import db
from models import User, Tenant, Menu, TeaTask, ProcurementItem, Feedback, Expense, PlatformAudit, Budget, FloorLendBorrow
from . import super_admin_bp
from ..utils import require_super_admin
from sqlalchemy import func
from datetime import datetime, timedelta

def log_platform_action(action, description):
    audit = PlatformAudit(
        action=action,
        description=description,
        performed_by_id=session.get('user_id')
    )
    db.session.add(audit)
    db.session.commit()

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
    total_budget = db.session.query(func.sum(Budget.amount_allocated)).scalar() or 0
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
    
    floor_stats = []
    for f in range(1, tenant.floor_count + 1):
        u_count = User.query.filter_by(tenant_id=tenant_id, floor=f).count()
        m_count = Menu.query.filter_by(tenant_id=tenant_id, floor=f).count()
        floor_stats.append({'floor': f, 'users': u_count, 'menus': m_count})
        
    return render_template('super_admin/tenant_view.html', tenant=tenant, users=users, floor_stats=floor_stats)

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
    tenant.floor_count = int(request.form.get('floor_count'))
    tenant.subscription_status = request.form.get('subscription_status')
    db.session.commit()
    log_platform_action('config_update', f'Updated tenant "{tenant.name}": Floors {old_floors}->{tenant.floor_count}, Tier: {tenant.subscription_status}')
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
