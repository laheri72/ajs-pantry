from flask import render_template, request, redirect, url_for, session, flash, abort, g
from werkzeug.security import check_password_hash, generate_password_hash
from app import db
from models import User, Tenant, Menu, TeaTask, ProcurementItem, Feedback, Expense, PlatformAudit
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
    
    # Platform-Wide Metrics
    total_tenants = Tenant.query.count()
    total_users = User.query.filter(User.tenant_id.isnot(None)).count()
    
    # Activity Distribution
    activity = {
        'menus': Menu.query.count(),
        'tea_tasks': TeaTask.query.count(),
        'procurements': ProcurementItem.query.count(),
        'feedbacks': Feedback.query.count()
    }
    
    # Growth Calculation
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    new_tenants_30d = Tenant.query.filter(Tenant.created_at >= thirty_days_ago).count()
    
    stats = {
        'tenant_count': total_tenants,
        'user_count': total_users,
        'activity_total': sum(activity.values()),
        'growth_rate': new_tenants_30d,
        'activity_data': [activity['menus'], activity['tea_tasks'], activity['procurements'], activity['feedbacks']]
    }
    
    recent_tenants = Tenant.query.order_by(Tenant.created_at.desc()).limit(5).all()
    recent_audits = PlatformAudit.query.order_by(PlatformAudit.created_at.desc()).limit(10).all()
        
    return render_template('super_admin/dashboard.html', tenants=recent_tenants, stats=stats, audits=recent_audits)

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
