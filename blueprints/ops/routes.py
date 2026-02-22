from flask import render_template, request, redirect, url_for, flash, jsonify, abort
from app import db
from models import User, TeaTask, Request, ProcurementItem
from datetime import datetime, date
from sqlalchemy import or_, func
from . import ops_bp
from ..utils import (
    _require_user,
    _get_active_floor,
    _require_staff_for_floor,
    _display_name_for
)

@ops_bp.route('/tea', methods=['GET', 'POST'])
def tea():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    _require_staff_for_floor(user)

    floor = _get_active_floor(user)
    floor_users = User.query.filter_by(floor=floor).all()

    if request.method == 'POST' and user.role in ['admin', 'teaManager']:
        try:
            task_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        except Exception:
            flash('Invalid tea task date', 'error')
            return redirect(url_for('ops.tea'))

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
        return redirect(url_for('ops.tea'))

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
            return redirect(url_for('ops.tea'))
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

@ops_bp.route('/tea/complete/<int:task_id>', methods=['POST'])
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

@ops_bp.route('/requests', methods=['GET', 'POST'])
def requests():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
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
            return redirect(url_for('ops.requests'))

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
        return redirect(url_for('ops.requests'))

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

@ops_bp.route('/requests/<int:request_id>/status', methods=['POST'])
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

@ops_bp.route('/requests/<int:request_id>/delete', methods=['POST'])
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

@ops_bp.route('/procurement', methods=['GET', 'POST'])
def procurement():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

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
                    return redirect(url_for('ops.procurement'))

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
                return redirect(url_for('ops.procurement'))

            db.session.add_all(items_to_add)
            db.session.commit()
            flash(f'Added {len(items_to_add)} procurement items successfully.', 'success')
            return redirect(url_for('ops.procurement'))

        item_name = (request.form.get('item_name') or '').strip()
        quantity = (request.form.get('quantity') or '').strip()
        if not item_name or not quantity:
            flash('Item name and quantity are required.', 'error')
            return redirect(url_for('ops.procurement'))

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
        return redirect(url_for('ops.procurement'))

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

@ops_bp.route('/procurement/complete/<int:item_id>', methods=['POST'])
def complete_procurement_item(item_id):
    user = _require_user()
    if not user:
        if request.accept_mimetypes.accept_html:
            return redirect(url_for('auth.login'))
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
        return redirect(url_for('ops.procurement'))
    return ('', 204)

@ops_bp.route('/procurement/revoke/<int:item_id>', methods=['POST'])
def revoke_procurement_item(item_id):
    user = _require_user()
    if not user:
        if request.accept_mimetypes.accept_html:
            return redirect(url_for('auth.login'))
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

    item.status = 'pending'
    item.actual_cost = None
    item.expense_recorded_at = None
    db.session.commit()

    if request.accept_mimetypes.accept_html:
        flash('Item reverted to pending', 'success')
        return redirect(url_for('ops.procurement'))
    return ('', 204)

@ops_bp.route('/procurement/delete/<int:item_id>', methods=['POST'])
def delete_procurement_item(item_id):
    user = _require_user()
    if not user:
        if request.accept_mimetypes.accept_html:
            return redirect(url_for('auth.login'))
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

    db.session.delete(item)
    db.session.commit()

    if request.accept_mimetypes.accept_html:
        flash('Procurement item deleted successfully.', 'success')
        return redirect(url_for('ops.procurement'))
    return ('', 204)

@ops_bp.route('/procurement/suggest', methods=['GET'])
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

@ops_bp.route('/procurement/suggest-qty', methods=['GET'])
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
