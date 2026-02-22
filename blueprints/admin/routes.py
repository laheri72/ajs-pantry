from flask import render_template, request, redirect, url_for, flash, jsonify, abort, session
from werkzeug.security import generate_password_hash
from app import db
from models import User, Team, TeamMember, Announcement, Garamat, Budget, ProcurementItem, Expense, Feedback, Menu, TeaTask, Request, Suggestion
from datetime import datetime, date
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from . import admin_bp
from ..utils import (
    _require_user,
    _get_active_floor,
    _require_team_access,
    _get_floor_options_for_admin,
    FLOOR_MIN,
    FLOOR_MAX
)

@admin_bp.route('/admin/active-floor', methods=['POST'])
def set_active_floor():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    if user.role != 'admin':
        abort(403)

    try:
        new_floor = int(request.form.get('floor') or '')
    except Exception:
        flash('Invalid floor', 'error')
        return redirect(request.referrer or url_for('pantry.dashboard'))

    if new_floor < FLOOR_MIN or new_floor > FLOOR_MAX:
        flash('Invalid floor', 'error')
        return redirect(request.referrer or url_for('pantry.dashboard'))

    session['active_floor'] = new_floor
    flash(f'Now viewing Floor {new_floor}', 'success')
    return redirect(request.referrer or url_for('pantry.dashboard'))

@admin_bp.route('/admin', methods=['GET', 'POST'])
def admin():
    user = _require_user()
    if not user or user.role != 'admin':
        return redirect(url_for('pantry.dashboard'))
    
    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        
        if action == 'add_user':
            role = (request.form.get('role') or '').strip()
            if role != 'member':
                flash('Only members can be created from the admin panel now.', 'error')
                return redirect(url_for('admin_panel.admin'))

            try:
                floor = int(request.form.get('floor', user.floor) or user.floor or FLOOR_MIN)
            except Exception:
                floor = user.floor or FLOOR_MIN

            if floor < FLOOR_MIN or floor > FLOOR_MAX:
                flash('Invalid floor selected', 'error')
                return redirect(url_for('admin_panel.admin'))

            tr_number = (request.form.get('tr_number') or '').strip()
            if not tr_number:
                flash('TR Number is required', 'error')
                return redirect(url_for('admin_panel.admin'))

            email = f"{tr_number}@jameasaifiyah.edu"
            if User.query.filter(or_(User.email == email, User.tr_number == tr_number)).first():
                flash('A user with this TR number/email already exists', 'error')
                return redirect(url_for('admin_panel.admin'))
            
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
            return redirect(url_for('admin_panel.admin'))

        if action == 'bulk_add_users':
            try:
                floor = int(request.form.get('floor') or '')
                tr_input = (request.form.get('tr_list') or '').strip()
                if not tr_input:
                    flash('No TR numbers provided', 'error')
                    return redirect(url_for('admin_panel.admin'))
                
                import re
                tr_numbers = re.split(r'[,\s]+', tr_input)
                tr_numbers = [t.strip() for t in tr_numbers if t.strip()]
                
                if not tr_numbers:
                    flash('No valid TR numbers found', 'error')
                    return redirect(url_for('admin_panel.admin'))

                added_count = 0
                skipped_count = 0
                
                for tr in tr_numbers:
                    email = f"{tr}@jameasaifiyah.edu"
                    if User.query.filter(or_(User.email == email, User.tr_number == tr)).first():
                        skipped_count += 1
                        continue
                    
                    new_user = User()
                    new_user.role = 'member'
                    new_user.floor = floor
                    new_user.tr_number = tr
                    new_user.email = email
                    new_user.password_hash = generate_password_hash('maskan1447')
                    new_user.is_first_login = True
                    db.session.add(new_user)
                    added_count += 1
                
                db.session.commit()
                flash(f'Successfully added {added_count} members to Floor {floor}. {skipped_count} skipped (already exist).', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error during bulk add: {str(e)}', 'error')
            return redirect(url_for('admin_panel.admin'))

        if action == 'assign_role':
            role = (request.form.get('role') or '').strip()
            if role not in {'pantryHead', 'teaManager'}:
                flash('Invalid role selected', 'error')
                return redirect(url_for('admin_panel.admin'))

            try:
                floor = int(request.form.get('floor') or '')
            except Exception:
                flash('Invalid floor selected', 'error')
                return redirect(url_for('admin_panel.admin'))

            if floor < FLOOR_MIN or floor > FLOOR_MAX:
                flash('Invalid floor selected', 'error')
                return redirect(url_for('admin_panel.admin'))

            try:
                target_user_id = int(request.form.get('user_id') or '')
            except Exception:
                flash('Invalid user selected', 'error')
                return redirect(url_for('admin_panel.admin'))

            target = User.query.get(target_user_id)
            if not target:
                flash('User not found', 'error')
                return redirect(url_for('admin_panel.admin'))

            if target.role == 'admin':
                flash('Admin users cannot be reassigned.', 'error')
                return redirect(url_for('admin_panel.admin'))

            if target.floor != floor:
                flash('Selected user must be on the selected floor', 'error')
                return redirect(url_for('admin_panel.admin'))

            if target.role != 'member':
                flash('Only members can be assigned to staff roles.', 'error')
                return redirect(url_for('admin_panel.admin'))

            target.role = role
            db.session.commit()
            flash('Role assigned successfully', 'success')
            return redirect(url_for('admin_panel.admin'))

        if action == 'delete_user':
            try:
                target_user_id = int(request.form.get('user_id') or '')
            except Exception:
                flash('Invalid user selected', 'error')
                return redirect(url_for('admin_panel.admin'))

            target = User.query.get(target_user_id)
            if not target:
                flash('User not found', 'error')
                return redirect(url_for('admin_panel.admin'))

            if target.id == user.id:
                flash('You cannot delete your own account.', 'error')
                return redirect(url_for('admin_panel.admin'))

            if target.role == 'admin':
                flash('Admin users cannot be deleted from this panel.', 'error')
                return redirect(url_for('admin_panel.admin'))

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
                return redirect(url_for('admin_panel.admin'))

            flash('User deleted successfully', 'success')
            return redirect(url_for('admin_panel.admin'))
            
    all_users = User.query.all()
    
    total_users = User.query.count()
    total_budget_all = float(db.session.query(func.sum(Budget.amount_allocated)).scalar() or 0)
    
    total_spent_proc = float(db.session.query(func.sum(ProcurementItem.actual_cost)).filter(ProcurementItem.status == 'completed').scalar() or 0)
    total_spent_legacy = float(db.session.query(func.sum(Expense.amount)).scalar() or 0)
    total_spent_all = total_spent_proc + total_spent_legacy
    
    system_avg_rating = db.session.query(func.avg(Feedback.rating)).scalar() or 0
    
    floor_data = []
    for f in range(FLOOR_MIN, FLOOR_MAX + 1):
        ph = User.query.filter_by(floor=f, role='pantryHead').first()
        f_user_count = User.query.filter_by(floor=f).count()
        f_budget = float(db.session.query(func.sum(Budget.amount_allocated)).filter(Budget.floor == f).scalar() or 0)
        f_spent_proc = float(db.session.query(func.sum(ProcurementItem.actual_cost)).filter(ProcurementItem.floor == f, ProcurementItem.status == 'completed').scalar() or 0)
        f_spent_legacy = float(db.session.query(func.sum(Expense.amount)).filter(Expense.floor == f).scalar() or 0)
        f_spent = f_spent_proc + f_spent_legacy
        f_rating = db.session.query(func.avg(Feedback.rating)).filter(Feedback.floor == f).scalar() or 0
        
        floor_data.append({
            'floor': f,
            'user_count': f_user_count,
            'pantry_head': ph.full_name if ph and ph.full_name else (ph.username if ph else 'Not Assigned'),
            'budget': f_budget,
            'spent': f_spent,
            'remaining': f_budget - f_spent,
            'avg_rating': round(float(f_rating), 1)
        })

    return render_template(
        'admin.html', 
        user=user, 
        all_users=all_users, 
        total_users=total_users,
        total_budget_all=total_budget_all,
        total_spent_all=total_spent_all,
        system_avg_rating=round(float(system_avg_rating), 1),
        floor_data=floor_data,
        current_user=user
    )

@admin_bp.route('/admin/floor-members', methods=['GET'])
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

@admin_bp.route('/floor-admin', methods=['GET', 'POST'])
def floor_admin():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    if user.role not in {'admin', 'pantryHead'}:
        abort(403)

    floor = _get_active_floor(user)
    floor_users = User.query.filter_by(floor=floor).order_by(User.role.asc(), User.email.asc()).all()
    tea_managers = [u for u in floor_users if u.role == 'teaManager']
    active_announcements = Announcement.query.filter_by(floor=floor, is_archived=False).order_by(Announcement.created_at.desc()).all()
    archived_announcements = Announcement.query.filter_by(floor=floor, is_archived=True).order_by(Announcement.created_at.desc()).all()
    
    floor_teams = Team.query.filter_by(floor=floor).order_by(Team.name.asc()).all()
    garamat_records = Garamat.query.filter_by(floor=floor).order_by(Garamat.date.desc()).all()

    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()

        if action == 'add_garamat':
            user_id = request.form.get('user_id')
            team_id = request.form.get('team_id')
            amount = request.form.get('amount')
            reason = request.form.get('reason')
            date_val = request.form.get('date')

            if not amount or not reason or not date_val:
                flash('Amount, reason and date are required', 'error')
                return redirect(url_for('admin_panel.floor_admin'))
            
            try:
                dt_obj = datetime.strptime(date_val, '%Y-%m-%d').date()
            except Exception:
                flash('Invalid date format', 'error')
                return redirect(url_for('admin_panel.floor_admin'))

            new_g = Garamat(
                user_id=int(user_id) if user_id and user_id.strip() else None,
                team_id=int(team_id) if team_id and team_id.strip() else None,
                amount=float(amount),
                reason=reason,
                date=dt_obj,
                floor=floor,
                created_by_id=user.id
            )
            db.session.add(new_g)
            db.session.commit()
            flash('Penalty record added successfully', 'success')
            return redirect(url_for('admin_panel.floor_admin'))

        if action == 'delete_garamat':
            g_id = request.form.get('garamat_id')
            g = Garamat.query.get(g_id)
            if g and (g.floor == floor or user.role == 'admin'):
                db.session.delete(g)
                db.session.commit()
                flash('Penalty record deleted', 'success')
            return redirect(url_for('admin_panel.floor_admin'))

        if action == 'add_announcement':
            title = request.form.get('title')
            content = request.form.get('content')
            if not title or not content:
                flash('Title and content are required', 'error')
                return redirect(url_for('admin_panel.floor_admin'))
            
            new_ann = Announcement(
                title=title,
                content=content,
                floor=floor,
                created_by_id=user.id
            )
            db.session.add(new_ann)
            db.session.commit()
            flash('Announcement posted successfully', 'success')
            return redirect(url_for('admin_panel.floor_admin'))

        if action == 'archive_announcement':
            ann_id = request.form.get('announcement_id')
            ann = Announcement.query.get(ann_id)
            if ann and (ann.floor == floor or user.role == 'admin'):
                ann.is_archived = True
                db.session.commit()
                flash('Announcement archived', 'success')
            return redirect(url_for('admin_panel.floor_admin'))

        if action == 'delete_announcement':
            ann_id = request.form.get('announcement_id')
            ann = Announcement.query.get(ann_id)
            if ann and (ann.floor == floor or user.role == 'admin'):
                db.session.delete(ann)
                db.session.commit()
                flash('Announcement deleted', 'success')
            return redirect(url_for('admin_panel.floor_admin'))

        if action == 'assign_tea_manager':
            try:
                target_user_id = int(request.form.get('user_id') or '')
            except Exception:
                flash('Invalid user selected', 'error')
                return redirect(url_for('admin_panel.floor_admin'))

            target = User.query.get(target_user_id)
            if not target:
                flash('User not found', 'error')
                return redirect(url_for('admin_panel.floor_admin'))

            if user.role == 'pantryHead' and target.floor != user.floor:
                abort(403)

            if target.floor != floor:
                flash('User must be on the selected floor', 'error')
                return redirect(url_for('admin_panel.floor_admin'))

            if target.role != 'member':
                flash('Only members can be assigned as tea manager', 'error')
                return redirect(url_for('admin_panel.floor_admin'))

            target.role = 'teaManager'
            db.session.commit()
            flash('Tea manager assigned successfully', 'success')
            return redirect(url_for('admin_panel.floor_admin'))

        if action == 'remove_tea_manager':
            try:
                target_user_id = int(request.form.get('user_id') or '')
            except Exception:
                flash('Invalid user selected', 'error')
                return redirect(url_for('admin_panel.floor_admin'))

            target = User.query.get(target_user_id)
            if not target:
                flash('User not found', 'error')
                return redirect(url_for('admin_panel.floor_admin'))

            if user.role == 'pantryHead' and target.floor != user.floor:
                abort(403)

            if target.floor != floor:
                flash('User must be on the selected floor', 'error')
                return redirect(url_for('admin_panel.floor_admin'))

            if target.role != 'teaManager':
                flash('Selected user is not a tea manager', 'error')
                return redirect(url_for('admin_panel.floor_admin'))

            target.role = 'member'
            db.session.commit()
            flash('Tea manager removed successfully', 'success')
            return redirect(url_for('admin_panel.floor_admin'))

        flash('Unknown action', 'error')
        return redirect(url_for('admin_panel.floor_admin'))

    return render_template(
        'floor_admin.html',
        floor=floor,
        floor_users=floor_users,
        tea_managers=tea_managers,
        active_announcements=active_announcements,
        archived_announcements=archived_announcements,
        floor_teams=floor_teams,
        garamat_records=garamat_records,
        current_user=user,
        today=date.today(),
    )

@admin_bp.route('/teams', methods=['POST'])
def create_team():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    if user.role not in {'admin', 'pantryHead'}:
        abort(403)

    floor = _get_active_floor(user)
    if user.role == 'pantryHead':
        floor = user.floor

    name = (request.form.get('name') or '').strip()
    icon = (request.form.get('icon') or '').strip() or None
    if not name:
        flash('Team name is required', 'error')
        return redirect(url_for('pantry.people'))

    existing = Team.query.filter_by(floor=floor, name=name).first()
    if existing:
        flash('Team name already exists on this floor', 'error')
        return redirect(url_for('pantry.people'))

    team = Team(name=name, icon=icon, floor=floor, created_by_id=user.id)
    db.session.add(team)
    db.session.commit()
    flash('Team created', 'success')
    return redirect(url_for('pantry.people'))

@admin_bp.route('/teams/<int:team_id>/update', methods=['POST'])
def update_team(team_id):
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

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
        return redirect(url_for('pantry.people'))

    if Team.query.filter(Team.floor == team.floor, Team.name == name, Team.id != team.id).first():
        flash('Team name already exists on this floor', 'error')
        return redirect(url_for('pantry.people'))

    team.name = name
    team.icon = icon
    db.session.commit()
    flash('Team updated', 'success')
    return redirect(url_for('pantry.people'))

@admin_bp.route('/teams/<int:team_id>/delete', methods=['POST'])
def delete_team(team_id):
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

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
    return redirect(url_for('pantry.people'))

@admin_bp.route('/teams/<int:team_id>/members/add', methods=['POST'])
def add_team_member(team_id):
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

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
        return redirect(url_for('pantry.people'))

    member = User.query.get(member_id)
    if not member or member.floor != team.floor or member.role == 'admin':
        flash('User must be on this floor', 'error')
        return redirect(url_for('pantry.people'))

    if TeamMember.query.filter_by(team_id=team.id, user_id=member.id).first():
        flash('User is already in this team', 'error')
        return redirect(url_for('pantry.people'))

    db.session.add(TeamMember(team_id=team.id, user_id=member.id))
    db.session.commit()
    flash('Member added to team', 'success')
    return redirect(url_for('pantry.people'))

@admin_bp.route('/teams/<int:team_id>/members/remove', methods=['POST'])
def remove_team_member(team_id):
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

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
        return redirect(url_for('pantry.people'))

    TeamMember.query.filter_by(team_id=team.id, user_id=member_id).delete(synchronize_session=False)
    db.session.commit()
    flash('Member removed', 'success')
    return redirect(url_for('pantry.people'))
