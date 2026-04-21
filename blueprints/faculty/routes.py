import os
import re
from datetime import date, datetime

from flask import (
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from sqlalchemy import func
from werkzeug.exceptions import Forbidden, Unauthorized
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from models import (
    Bill,
    Budget,
    Expense,
    ExpensePrintReport,
    ExpensePrintReportBill,
    FacultyBudgetCycle,
    FacultyMessage,
    FacultyMessageFloor,
    FacultyReportSubmission,
    Feedback,
    FloorLendBorrow,
    Menu,
    ProcurementItem,
    User,
)
from . import faculty_bp
from ..budgeting import build_floor_budget_ledger
from ..utils import (
    _ensure_username_from_full_name,
    _get_active_floor,
    _get_tenant_floor_options,
    current_tenant_faculty_workflow_enabled,
    faculty_workflow_enabled_for_user,
    _require_faculty,
    _require_user,
    send_email_notification,
    send_push_notification,
    tenant_filter,
    visible_budget_condition,
)


@faculty_bp.before_request
def _faculty_auth_guard():
    shared_staff_endpoints = {
        'faculty.reports_page', 
        'faculty.download_floor_submission',
        'faculty.download_adhoc_report',
        'faculty.delete_adhoc_report'
    }
    if request.endpoint == 'faculty.login' or request.endpoint in shared_staff_endpoints:
        return None

    user = _require_user()
    if not user:
        session.clear()
        flash('Your Faculty session expired. Please sign in again.', 'error')
        return redirect(url_for('faculty.login'))

    if not faculty_workflow_enabled_for_user(user):
        session.clear()
        flash('Faculty workflow is disabled for this tenant right now.', 'error')
        return redirect(url_for('faculty.login'))

    if user.role != 'faculty':
        flash('Please sign in with a Faculty account to access the Faculty portal.', 'error')
        return redirect(url_for('faculty.login'))

    return None


@faculty_bp.errorhandler(Unauthorized)
@faculty_bp.errorhandler(401)
def _faculty_unauthorized(_error):
    session.clear()
    flash('Your Faculty session expired. Please sign in again.', 'error')
    return redirect(url_for('faculty.login'))


@faculty_bp.errorhandler(Forbidden)
@faculty_bp.errorhandler(403)
def _faculty_forbidden(_error):
    user = _require_user()
    if user and user.role == 'faculty':
        flash('You do not have permission to access that Faculty page.', 'error')
    else:
        session.clear()
        flash('Please sign in with a Faculty account to access the Faculty portal.', 'error')
    return redirect(url_for('faculty.login'))


def _tenant_slug():
    tenant_name = getattr(g, 'tenant_name', None) or 'tenant'
    slug = re.sub(r'[^a-z0-9]+', '-', tenant_name.lower()).strip('-')
    return slug or 'tenant'


def _report_storage_dir():
    base_dir = current_app.config["REPORT_STORAGE_ROOT"]
    path = os.path.join(base_dir, _tenant_slug())
    os.makedirs(path, exist_ok=True)
    return path


def _build_report_filename(cycle, floor, revision_no):
    return (
        f"{_tenant_slug()}_Floor-{floor}_"
        f"{cycle.start_date.strftime('%Y%m%d')}_to_{cycle.end_date.strftime('%Y%m%d')}"
        f"_v{revision_no}.pdf"
    )


def _current_active_cycle():
    if not current_tenant_faculty_workflow_enabled():
        return None
    return (
        tenant_filter(FacultyBudgetCycle.query)
        .filter_by(status='active')
        .order_by(FacultyBudgetCycle.start_date.desc())
        .first()
    )


def _cycle_for_floor(cycle_id, floor):
    return (
        tenant_filter(Budget.query)
        .filter(
            Budget.cycle_id == cycle_id,
            Budget.floor == floor,
            visible_budget_condition(),
        )
        .first()
    )


def _is_cycle_fully_verified(cycle):
    if not cycle:
        return True
    budgets = tenant_filter(Budget.query).filter_by(cycle_id=cycle.id).all()
    if not budgets:
        return True
    submissions = tenant_filter(FacultyReportSubmission.query).filter_by(cycle_id=cycle.id).all()
    submissions_by_floor = {s.floor: s for s in submissions}
    for budget in budgets:
        try:
            val = float(budget.amount_allocated)
        except (ValueError, TypeError):
            val = 0.0
        if val == 0.0:
            continue
        sub = submissions_by_floor.get(budget.floor)
        if not sub or sub.status != 'verified':
            return False
    return True


def _parse_selected_ids(values):
    parsed = []
    for raw in values:
        try:
            parsed.append(int(raw))
        except (TypeError, ValueError):
            continue
    return parsed


def _cycle_form_floor_options(user, cycle=None):
    floor_values = set(_get_tenant_floor_options(user))
    if cycle:
        existing_floors = (
            tenant_filter(Budget.query)
            .filter_by(cycle_id=cycle.id)
            .with_entities(Budget.floor)
            .all()
        )
        floor_values.update(floor for (floor,) in existing_floors)
    return sorted(floor_values)


def _parse_cycle_form(floor_options):
    title = (request.form.get('title') or '').strip()
    start_date_raw = request.form.get('start_date')
    end_date_raw = request.form.get('end_date')
    deadline_raw = request.form.get('submission_deadline')
    cycle_notes = (request.form.get('notes') or '').strip()

    if not title or not start_date_raw or not end_date_raw or not deadline_raw:
        return None, 'Cycle title, term dates, and deadline are required.'

    try:
        start_date = datetime.strptime(start_date_raw, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date()
        submission_deadline = datetime.strptime(deadline_raw, '%Y-%m-%d').date()
    except ValueError:
        return None, 'Invalid cycle date provided.'

    if end_date < start_date:
        return None, 'Cycle end date must be after the start date.'

    if submission_deadline < start_date:
        return None, 'Submission deadline cannot be before the cycle starts.'

    allocations = []
    for floor in floor_options:
        amount_raw = request.form.get(f'amount_{floor}', '0')
        faculty_note = (request.form.get(f'faculty_note_{floor}') or '').strip()
        try:
            amount = float(amount_raw or 0)
        except ValueError:
            amount = 0

        allocations.append({
            'floor': floor,
            'amount': amount,
            'faculty_note': faculty_note,
        })

    return {
        'title': title,
        'start_date': start_date,
        'end_date': end_date,
        'submission_deadline': submission_deadline,
        'notes': cycle_notes,
        'allocations': allocations,
    }, None


def _sync_cycle_budgets(cycle, user, allocations):
    budget_note = cycle.notes or f'Faculty cycle {cycle.title}'
    existing_budgets = (
        tenant_filter(Budget.query)
        .filter_by(cycle_id=cycle.id)
        .all()
    )
    budgets_by_floor = {budget.floor: budget for budget in existing_budgets}

    for allocation in allocations:
        budget = budgets_by_floor.get(allocation['floor'])
        if not budget:
            budget = Budget(
                floor=allocation['floor'],
                cycle_id=cycle.id,
                tenant_id=getattr(g, 'tenant_id', None),
            )
            db.session.add(budget)

        budget.allocated_by_id = user.id
        budget.amount_allocated = allocation['amount']
        budget.allocation_type = 'faculty_cycle'
        budget.start_date = cycle.start_date
        budget.end_date = cycle.end_date
        budget.notes = budget_note
        budget.faculty_note = allocation['faculty_note']
        budget.is_faculty_allocation = True


def _submission_selectable_bills(floor, existing_submission=None):
    query = tenant_filter(Bill.query).filter(Bill.floor == floor)
    if existing_submission:
        query = query.filter(
            (Bill.report_submission_id.is_(None))
            | (Bill.report_submission_id == existing_submission.id)
        )
    else:
        query = query.filter(Bill.report_submission_id.is_(None))
    return query.order_by(Bill.bill_date.desc(), Bill.created_at.desc()).all()

def _saved_print_reports_for_floor(floor, cycle_id=None):
    query = tenant_filter(ExpensePrintReport.query).filter_by(floor=floor)
    if cycle_id:
        query = query.filter(ExpensePrintReport.cycle_id == cycle_id)
    return query.order_by(ExpensePrintReport.created_at.desc()).all()


def _save_submission_file(file_storage, cycle, floor, revision_no):
    filename = _build_report_filename(cycle, floor, revision_no)
    path = os.path.join(_report_storage_dir(), filename)
    file_storage.save(path)
    relative_path = f"{_tenant_slug()}/{filename}"
    return filename, relative_path, os.path.getsize(path)


def _safe_remove_file(path):
    if not path:
        current_app.logger.warning('Skipping PDF cleanup because no storage path was provided.')
        return
    try:
        if os.path.isabs(path):
            abs_path = path
        else:
            abs_path = os.path.normpath(os.path.join(current_app.config["REPORT_STORAGE_ROOT"], path))

        if os.path.exists(abs_path):
            os.remove(abs_path)
            current_app.logger.info('Deleted stored Faculty PDF during cleanup: %s', abs_path)
        else:
            current_app.logger.warning('Faculty PDF cleanup skipped because file was already missing: %s', abs_path)
    except OSError:
        current_app.logger.exception('Faculty PDF cleanup failed for path: %s', path)


def _message_target_floors(message):
    if message.target_scope == 'selected_floors':
        return sorted({target.floor for target in message.target_floors})
    return []


def _build_submission_verification_data(submission, linked_bills):
    allocation = _cycle_for_floor(submission.cycle_id, submission.floor)
    if submission.allocated_amount is not None:
        allocated_budget = float(submission.allocated_amount)
    else:
        allocated_budget = float(allocation.amount_allocated) if allocation else 0
    
    linked_bills_total = float(sum(float(bill.total_amount or 0) for bill in linked_bills))
    difference_amount = round(abs(allocated_budget - linked_bills_total), 2)
    verification_state = 'matched'
    if linked_bills_total < allocated_budget:
        verification_state = 'remaining'
    elif linked_bills_total > allocated_budget:
        verification_state = 'overspent'

    return {
        'allocation': allocation,
        'allocated_budget': allocated_budget,
        'linked_bills_total': linked_bills_total,
        'difference_amount': difference_amount,
        'verification_state': verification_state,
    }


def _delete_cycle_related_data(cycle):
    submissions = tenant_filter(FacultyReportSubmission.query).filter_by(cycle_id=cycle.id).all()
    for submission in submissions:
        for bill in list(submission.bills):
            bill.report_submission_id = None
        for expense in list(submission.expenses):
            expense.report_submission_id = None
        _safe_remove_file(submission.storage_path)
        db.session.delete(submission)

    print_reports = tenant_filter(ExpensePrintReport.query).filter_by(cycle_id=cycle.id).all()
    for report in print_reports:
        for link in list(report.bill_links):
            db.session.delete(link)
        db.session.delete(report)

    tenant_filter(Budget.query).filter_by(cycle_id=cycle.id).delete(synchronize_session=False)
    db.session.delete(cycle)


def _sync_submission_links(submission, selected_bills, selected_expenses):
    for bill in submission.bills:
        bill.report_submission_id = None
    for expense in submission.expenses:
        expense.report_submission_id = None

    for bill in selected_bills:
        bill.report_submission_id = submission.id
    for expense in selected_expenses:
        expense.report_submission_id = submission.id


@faculty_bp.route('/faculty/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        password = (request.form.get('password') or '').strip()

        if email and '@' not in email:
            email = f"{email}@jameasaifiyah.edu"

        user = User.query.filter_by(email=email, role='faculty').first()
        if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
            flash('Invalid Faculty credentials', 'error')
            return render_template('faculty/login.html')
        if not faculty_workflow_enabled_for_user(user):
            flash('Faculty workflow is disabled for this tenant right now.', 'error')
            return render_template('faculty/login.html')

        if _ensure_username_from_full_name(user, db.session):
            db.session.commit()

        if user.is_first_login:
            session['temp_user_id'] = user.id
            return redirect(url_for('auth.change_password'))

        session['user_id'] = user.id
        session['role'] = user.role
        session['floor'] = user.floor
        session.permanent = True
        return redirect(url_for('faculty.dashboard'))

    return render_template('faculty/login.html')


@faculty_bp.route('/faculty/dashboard')
def dashboard():
    user = _require_faculty()
    today = date.today()
    active_cycle = _current_active_cycle()
    cycle_allocations = []
    submissions_by_floor = {}

    if active_cycle:
        cycle_allocations = (
            tenant_filter(Budget.query)
            .filter(Budget.cycle_id == active_cycle.id, visible_budget_condition())
            .order_by(Budget.floor.asc())
            .all()
        )
        submissions = (
            tenant_filter(FacultyReportSubmission.query)
            .filter_by(cycle_id=active_cycle.id)
            .all()
        )
        submissions_by_floor = {s.floor: s for s in submissions}

    cycle_total_allocated = float(sum(float(b.amount_allocated) for b in cycle_allocations)) if cycle_allocations else 0

    cycle_total_spent = 0
    if active_cycle:
        proc_spent = tenant_filter(db.session.query(func.sum(ProcurementItem.actual_cost))).filter(
            ProcurementItem.status == 'completed',
            ProcurementItem.bill_id.isnot(None),
            ProcurementItem.expense_recorded_at >= datetime.combine(active_cycle.start_date, datetime.min.time()),
            ProcurementItem.expense_recorded_at <= datetime.combine(active_cycle.end_date, datetime.max.time()),
        ).scalar() or 0
        legacy_spent = tenant_filter(db.session.query(func.sum(Expense.amount))).filter(
            Expense.date >= active_cycle.start_date,
            Expense.date <= active_cycle.end_date,
        ).scalar() or 0
        cycle_total_spent = float(proc_spent) + float(legacy_spent)

    cumulative_proc_spent = tenant_filter(db.session.query(func.sum(ProcurementItem.actual_cost))).filter(
        ProcurementItem.status == 'completed',
        ProcurementItem.bill_id.isnot(None),
    ).scalar() or 0
    cumulative_legacy_spent = tenant_filter(db.session.query(func.sum(Expense.amount))).scalar() or 0
    cumulative_spending = float(cumulative_proc_spent) + float(cumulative_legacy_spent)

    avg_rating = tenant_filter(db.session.query(func.avg(Feedback.rating))).scalar() or 0
    first_of_month = date(today.year, today.month, 1)
    total_verified_bills = (
        tenant_filter(Bill.query)
        .join(FacultyReportSubmission, Bill.report_submission_id == FacultyReportSubmission.id)
        .filter(FacultyReportSubmission.status == 'verified')
        .count()
    )
    menus_this_month = tenant_filter(Menu.query).filter(Menu.created_at >= first_of_month).count()
    procurement_this_month = tenant_filter(ProcurementItem.query).filter(ProcurementItem.created_at >= first_of_month).count()
    pending_borrowings = tenant_filter(FloorLendBorrow.query).filter(FloorLendBorrow.status == 'pending').count()

    pending_submission_count = 0
    verified_submission_count = 0
    overdue_floors = 0
    floor_rows = []
    if active_cycle:
        for allocation in cycle_allocations:
            submission = submissions_by_floor.get(allocation.floor)
            if submission and submission.status == 'verified':
                verified_submission_count += 1
            else:
                pending_submission_count += 1
                if active_cycle.submission_deadline < today:
                    overdue_floors += 1
            floor_rows.append({
                'floor': allocation.floor,
                'allocation': allocation,
                'submission': submission,
            })

    cycles = (
        tenant_filter(FacultyBudgetCycle.query)
        .order_by(FacultyBudgetCycle.created_at.desc())
        .limit(8)
        .all()
    )

    return render_template(
        'faculty/dashboard.html',
        current_user=user,
        active_cycle=active_cycle,
        cycle_total_allocated=cycle_total_allocated,
        cycle_total_spent=cycle_total_spent,
        pending_submission_count=pending_submission_count,
        verified_submission_count=verified_submission_count,
        overdue_floors=overdue_floors,
        cumulative_spending=cumulative_spending,
        avg_rating=round(float(avg_rating), 1),
        total_verified_bills=total_verified_bills,
        menus_this_month=menus_this_month,
        procurement_this_month=procurement_this_month,
        pending_borrowings=pending_borrowings,
        floor_rows=floor_rows,
        cycles=cycles,
        today=today,
    )


@faculty_bp.route('/faculty/profile', methods=['GET', 'POST'])
def profile():
    user = _require_faculty()

    if request.method == 'POST':
        user.full_name = (request.form.get('full_name') or '').strip() or None
        user.phone_number = (request.form.get('phone_number') or '').strip() or None
        _ensure_username_from_full_name(user, db.session)

        new_password = (request.form.get('new_password') or '').strip()
        if new_password:
            user.password_hash = generate_password_hash(new_password)

        db.session.commit()
        flash('Faculty profile updated successfully.', 'success')
        return redirect(url_for('faculty.profile'))

    return render_template(
        'faculty/profile.html',
        current_user=user,
        user=user,
    )


@faculty_bp.route('/faculty/messages', methods=['GET', 'POST'])
def messages():
    user = _require_faculty()
    floor_options = _get_tenant_floor_options(user)

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        content = (request.form.get('content') or '').strip()
        target_scope = (request.form.get('target_scope') or 'all_pantry_heads').strip()

        if not title or not content:
            flash('Message title and content are required.', 'error')
            return redirect(url_for('faculty.messages'))

        if target_scope not in {'all_pantry_heads', 'selected_floors'}:
            flash('Invalid recipient scope selected.', 'error')
            return redirect(url_for('faculty.messages'))

        selected_floors = []
        if target_scope == 'selected_floors':
            for raw_floor in request.form.getlist('target_floors'):
                try:
                    floor = int(raw_floor)
                except (TypeError, ValueError):
                    continue
                if floor in floor_options and floor not in selected_floors:
                    selected_floors.append(floor)

            if not selected_floors:
                flash('Choose at least one floor for a targeted Faculty message.', 'error')
                return redirect(url_for('faculty.messages'))

        message = FacultyMessage(
            title=title,
            content=content,
            target_scope=target_scope,
            created_by_id=user.id,
            tenant_id=getattr(g, 'tenant_id', None),
        )
        db.session.add(message)
        db.session.flush()

        if target_scope == 'selected_floors':
            for floor in selected_floors:
                db.session.add(FacultyMessageFloor(
                    faculty_message_id=message.id,
                    floor=floor,
                    tenant_id=getattr(g, 'tenant_id', None),
                ))

        recipient_query = tenant_filter(User.query).filter(User.role == 'pantryHead')
        if target_scope == 'selected_floors':
            recipient_query = recipient_query.filter(User.floor.in_(selected_floors))
        recipients = recipient_query.all()

        db.session.commit()

        if request.headers.get('Accept') == 'application/json':
            from flask import jsonify
            recipient_list = [{"id": r.id, "name": r.full_name or r.username or r.email or 'Pantry Head'} for r in recipients]
            return jsonify({"message_id": message.id, "recipients": recipient_list})

        flash('Faculty message created.', 'success')
        return redirect(url_for('faculty.messages'))

    active_messages = (
        tenant_filter(FacultyMessage.query)
        .filter_by(is_archived=False)
        .order_by(FacultyMessage.created_at.desc())
        .all()
    )
    archived_messages = (
        tenant_filter(FacultyMessage.query)
        .filter_by(is_archived=True)
        .order_by(FacultyMessage.created_at.desc())
        .all()
    )

    return render_template(
        'faculty/messages.html',
        current_user=user,
        active_messages=active_messages,
        archived_messages=archived_messages,
        floor_options=floor_options,
        message_target_floors=_message_target_floors,
    )


@faculty_bp.route('/faculty/messages/<int:message_id>/send_single', methods=['POST'])
def send_single_message(message_id):
    from flask import jsonify
    user = _require_faculty()
    message = tenant_filter(FacultyMessage.query).filter_by(id=message_id).first_or_404()
    
    data = request.get_json() or {}
    recipient_id = data.get('user_id')
    
    if not recipient_id:
        return jsonify({"status": "error", "message": "user_id is required"}), 400
        
    recipient = User.query.get(recipient_id)
    if not recipient:
        return jsonify({"status": "error", "message": "user not found"}), 404
        
    send_push_notification(
        user_id=recipient.id,
        title=f"Faculty Message: {message.title}",
        body=message.content[:100] + ("..." if len(message.content) > 100 else ""),
        icon="/static/icons/icon-192.png",
        url="/dashboard",
    )
    
    if recipient.email:
        tenant_name = getattr(g, 'tenant_name', 'Maskan')
        email_subject = f"[{tenant_name}] Faculty Message: {message.title}"
        email_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2c3e50;">{message.title}</h2>
            <p style="white-space: pre-wrap; font-size: 16px; color: #333;">{message.content}</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #888;">Log in to your pantry dashboard to manage and reply if necessary.</p>
        </div>
        """
        send_email_notification(recipient.email, email_subject, email_html)
        
    return jsonify({"status": "success"})


@faculty_bp.route('/faculty/cycles', methods=['GET', 'POST'])
def cycles():
    user = _require_faculty()
    floor_options = _cycle_form_floor_options(user)

    if request.method == 'POST':
        action = (request.form.get('action') or 'save_draft').strip()
        cycle_data, error_message = _parse_cycle_form(floor_options)
        if error_message:
            flash(error_message, 'error')
            return redirect(url_for('faculty.cycles'))

        status = 'active' if action == 'activate_now' else 'draft'
        if status == 'active':
            existing_active = _current_active_cycle()
            if existing_active:
                flash('Close the current active cycle before activating a new one.', 'error')
                return redirect(url_for('faculty.cycles'))

        cycle = FacultyBudgetCycle(
            title=cycle_data['title'],
            start_date=cycle_data['start_date'],
            end_date=cycle_data['end_date'],
            submission_deadline=cycle_data['submission_deadline'],
            status=status,
            notes=cycle_data['notes'],
            created_by_id=user.id,
            activated_at=datetime.utcnow() if status == 'active' else None,
            tenant_id=getattr(g, 'tenant_id', None),
        )
        db.session.add(cycle)
        db.session.flush()

        _sync_cycle_budgets(cycle, user, cycle_data['allocations'])

        db.session.commit()
        flash(f'Faculty cycle "{cycle.title}" saved successfully.', 'success')
        return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))

    cycles = (
        tenant_filter(FacultyBudgetCycle.query)
        .order_by(FacultyBudgetCycle.created_at.desc())
        .all()
    )
    return render_template(
        'faculty/cycles.html',
        current_user=user,
        cycles=cycles,
        floor_options=floor_options,
        active_cycle=_current_active_cycle(),
        today=date.today(),
    )


@faculty_bp.route('/faculty/cycles/<int:cycle_id>')
def cycle_detail(cycle_id):
    user = _require_faculty()
    cycle = tenant_filter(FacultyBudgetCycle.query).filter_by(id=cycle_id).first_or_404()
    budgets = (
        tenant_filter(Budget.query)
        .filter_by(cycle_id=cycle.id)
        .order_by(Budget.floor.asc())
        .all()
    )
    submissions = (
        tenant_filter(FacultyReportSubmission.query)
        .filter_by(cycle_id=cycle.id)
        .all()
    )
    submissions_by_floor = {s.floor: s for s in submissions}
    floor_rows = []
    for budget in budgets:
        floor_rows.append({
            'floor': budget.floor,
            'budget': budget,
            'submission': submissions_by_floor.get(budget.floor),
        })

    editable_floors = _cycle_form_floor_options(user, cycle)
    budgets_by_floor = {budget.floor: budget for budget in budgets}

    active_cycle = _current_active_cycle()
    all_verified = _is_cycle_fully_verified(cycle)
    active_cycle_verified = _is_cycle_fully_verified(active_cycle) if active_cycle else True

    return render_template(
        'faculty/cycle_detail.html',
        current_user=user,
        cycle=cycle,
        floor_rows=floor_rows,
        editable_floors=editable_floors,
        budgets_by_floor=budgets_by_floor,
        today=date.today(),
        all_verified=all_verified,
        active_cycle=active_cycle,
        active_cycle_verified=active_cycle_verified,
    )


@faculty_bp.route('/faculty/cycles/<int:cycle_id>/edit', methods=['POST'])
def edit_cycle(cycle_id):
    user = _require_faculty()
    cycle = tenant_filter(FacultyBudgetCycle.query).filter_by(id=cycle_id).first_or_404()

    if cycle.status == 'closed':
        flash('Closed cycles cannot be edited.', 'error')
        return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))

    floor_options = _cycle_form_floor_options(user, cycle)
    cycle_data, error_message = _parse_cycle_form(floor_options)
    if error_message:
        flash(error_message, 'error')
        return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))

    cycle.title = cycle_data['title']
    cycle.start_date = cycle_data['start_date']
    cycle.end_date = cycle_data['end_date']
    cycle.submission_deadline = cycle_data['submission_deadline']
    cycle.notes = cycle_data['notes']
    _sync_cycle_budgets(cycle, user, cycle_data['allocations'])

    db.session.commit()
    flash('Cycle updated successfully.', 'success')
    return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))


@faculty_bp.route('/faculty/cycles/<int:cycle_id>/activate', methods=['POST'])
def activate_cycle(cycle_id):
    user = _require_faculty()
    cycle = tenant_filter(FacultyBudgetCycle.query).filter_by(id=cycle_id).first_or_404()
    existing_active = _current_active_cycle()
    if existing_active and existing_active.id != cycle.id:
        flash(f'Close the currently active cycle "{existing_active.title}" before activating another one.', 'error')
        return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))

    cycle.status = 'active'
    cycle.activated_at = datetime.utcnow()
    db.session.commit()
    flash('Cycle activated successfully.', 'success')
    return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))


@faculty_bp.route('/faculty/cycles/<int:cycle_id>/close', methods=['POST'])
def close_cycle(cycle_id):
    _require_faculty()
    cycle = tenant_filter(FacultyBudgetCycle.query).filter_by(id=cycle_id).first_or_404()
    if request.form.get('confirm_close') != '1':
        flash('Please confirm the close-cycle action before final closing.', 'error')
        return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))
    if cycle.status != 'active':
        flash('Only active cycles can be closed.', 'error')
        return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))
    if not _is_cycle_fully_verified(cycle):
        flash('Cannot close cycle until all floors have submitted reports and they are verified.', 'error')
        return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))
        
    cycle.status = 'closed'
    cycle.closed_at = datetime.utcnow()
    db.session.commit()
    flash('Cycle closed successfully.', 'success')
    return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))


@faculty_bp.route('/faculty/cycles/<int:cycle_id>/delete', methods=['POST'])
def delete_cycle(cycle_id):
    _require_faculty()
    cycle = tenant_filter(FacultyBudgetCycle.query).filter_by(id=cycle_id).first_or_404()
    cycle_title = cycle.title
    _delete_cycle_related_data(cycle)
    db.session.commit()
    flash(f'Cycle "{cycle_title}" and all linked budgets, submissions, saved print reports, and PDFs were deleted.', 'success')
    return redirect(url_for('faculty.cycles'))


@faculty_bp.route('/reports', methods=['GET', 'POST'])
def reports_page():
    user = _require_user()
    if not user:
        flash('Your staff session expired. Please sign in again.', 'error')
        return redirect(url_for('auth.staff_login'))
    if user.role not in {'admin', 'pantryHead'}:
        abort(403)

    floor = _get_active_floor(user)
    faculty_workflow_enabled = current_tenant_faculty_workflow_enabled()
    active_cycle = _current_active_cycle()
    allocation = _cycle_for_floor(active_cycle.id, floor) if active_cycle else None
    submission = None
    saved_print_reports = []

    if faculty_workflow_enabled and active_cycle:
        submission = tenant_filter(FacultyReportSubmission.query).filter_by(
            cycle_id=active_cycle.id,
            floor=floor,
        ).first()
        floor_budget_ledger = build_floor_budget_ledger(
            floor=floor,
            faculty_workflow_enabled=faculty_workflow_enabled,
        )
        current_available_budget = floor_budget_ledger['current_available_budget']

        if request.method == 'POST':
            if not allocation:
                flash('This floor does not have an allocation in the active Faculty cycle.', 'error')
                return redirect(url_for('faculty.reports_page'))

            if submission and submission.status == 'verified':
                flash('This cycle report has already been verified.', 'error')
                return redirect(url_for('faculty.reports_page'))

            if submission and submission.status == 'submitted':
                flash('This floor already has a submitted report awaiting Faculty review.', 'error')
                return redirect(url_for('faculty.reports_page'))

            upload = request.files.get('report_pdf')
            submission_notes = (request.form.get('submission_notes') or '').strip()
            try:
                print_report_id = int(request.form.get('print_report_id') or 0)
            except (TypeError, ValueError):
                print_report_id = 0

            if not upload or not upload.filename:
                flash('Please upload the combined PDF report generated from Expenses.', 'error')
                return redirect(url_for('faculty.reports_page'))

            if not upload.filename.lower().endswith('.pdf'):
                flash('Only PDF uploads are allowed for Faculty submissions.', 'error')
                return redirect(url_for('faculty.reports_page'))

            if not print_report_id:
                flash('Please choose a saved print report from Expenses first.', 'error')
                return redirect(url_for('faculty.reports_page'))

            selected_print_report = tenant_filter(ExpensePrintReport.query).filter_by(
                id=print_report_id,
                floor=floor,
            ).first()
            if not selected_print_report:
                flash('The selected print report was not found for this floor.', 'error')
                return redirect(url_for('faculty.reports_page'))
            if selected_print_report.cycle_id and selected_print_report.cycle_id != active_cycle.id:
                flash('Please choose a print report created for the current active cycle.', 'error')
                return redirect(url_for('faculty.reports_page'))

            selected_bills = []
            for link in selected_print_report.bill_links:
                if link.bill and link.bill.floor == floor:
                    selected_bills.append(link.bill)

            if not selected_bills:
                flash('The selected print report does not contain any bills.', 'error')
                return redirect(url_for('faculty.reports_page'))

            for bill in selected_bills:
                if bill.report_submission_id and (not submission or bill.report_submission_id != submission.id):
                    flash(f'Bill {bill.bill_no} is already linked to another report submission.', 'error')
                    return redirect(url_for('faculty.reports_page'))

            revision_no = (submission.revision_no + 1) if submission else 1
            stored_filename, storage_path, file_size = _save_submission_file(upload, active_cycle, floor, revision_no)

            if submission:
                old_path = submission.storage_path
                submission.report_title = selected_print_report.report_title
                submission.print_report_id = selected_print_report.id
                submission.status = 'submitted'
                submission.allocated_amount = current_available_budget
                submission.submission_notes = submission_notes
                submission.review_notes = None
                submission.stored_filename = stored_filename
                submission.original_filename = upload.filename
                submission.storage_path = storage_path
                submission.file_size_bytes = file_size
                submission.revision_no = revision_no
                submission.uploaded_by_id = user.id
                submission.submitted_at = datetime.utcnow()
                submission.verified_at = None
                submission.verified_by_id = None
                _sync_submission_links(submission, selected_bills, [])
                if old_path and old_path != storage_path and os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except OSError:
                        pass
            else:
                submission = FacultyReportSubmission(
                    cycle_id=active_cycle.id,
                    print_report_id=selected_print_report.id,
                    floor=floor,
                    uploaded_by_id=user.id,
                    report_title=selected_print_report.report_title,
                    status='submitted',
                    allocated_amount=current_available_budget,
                    submission_notes=submission_notes,
                    stored_filename=stored_filename,
                    original_filename=upload.filename,
                    storage_path=storage_path,
                    file_size_bytes=file_size,
                    revision_no=revision_no,
                    submitted_at=datetime.utcnow(),
                    tenant_id=getattr(g, 'tenant_id', None),
                )
                db.session.add(submission)
                db.session.flush()
                _sync_submission_links(submission, selected_bills, [])

            db.session.commit()
            flash('Report submitted to Faculty successfully.', 'success')
            return redirect(url_for('faculty.reports_page'))

        saved_print_reports = _saved_print_reports_for_floor(floor, active_cycle.id)

    # Fetch Ad-hoc / irregular saved reports for this floor
    adhoc_reports = tenant_filter(ExpensePrintReport.query).filter(
        ExpensePrintReport.floor == floor,
        ExpensePrintReport.cycle_id == None,
        ExpensePrintReport.storage_path != None
    ).order_by(ExpensePrintReport.created_at.desc()).all()

    return render_template(
        'reports.html',
        current_user=user,
        active_floor=floor,
        faculty_workflow_enabled=faculty_workflow_enabled,
        active_cycle=active_cycle,
        allocation=allocation,
        submission=submission,
        saved_print_reports=saved_print_reports,
        adhoc_reports=adhoc_reports,
        today=date.today(),
    )

from flask import send_from_directory

@faculty_bp.route('/reports/adhoc/<int:report_id>/download')
def download_adhoc_report(report_id):
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)
        
    floor = _get_active_floor(user)
    report = tenant_filter(ExpensePrintReport.query).filter_by(id=report_id).first_or_404()
    
    if user.role != 'admin' and report.floor != floor:
        abort(403)
        
    if not report.storage_path:
        flash("This report does not have a saved PDF file.", "error")
        return redirect(url_for('faculty.reports_page'))
        
    base_dir = current_app.config.get("REPORT_STORAGE_ROOT", os.path.join(current_app.root_path, "tmp", "reports"))
    
    file_dir = os.path.dirname(os.path.normpath(os.path.join(base_dir, report.storage_path)))
    filename = os.path.basename(report.storage_path)
    
    try:
        return send_from_directory(file_dir, filename, as_attachment=True, download_name=report.stored_filename)
    except FileNotFoundError:
        flash("File missing from server. It might have been deleted.", "error")
        return redirect(url_for('faculty.reports_page'))

@faculty_bp.route('/reports/adhoc/<int:report_id>/delete', methods=['POST'])
def delete_adhoc_report(report_id):
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)
        
    floor = _get_active_floor(user)
    report = tenant_filter(ExpensePrintReport.query).filter_by(id=report_id).first_or_404()
    
    if user.role != 'admin' and report.floor != floor:
        abort(403)

    if report.storage_path:
        base_dir = current_app.config.get("REPORT_STORAGE_ROOT", os.path.join(current_app.root_path, "tmp", "reports"))
        abs_path = os.path.normpath(os.path.join(base_dir, report.storage_path))
        if os.path.exists(abs_path):
            try:
                os.remove(abs_path)
            except OSError:
                pass
                
    db.session.delete(report)
    db.session.commit()
    
    flash("Ad-Hoc Report and its PDF have been permanently deleted.", "success")
    return redirect(url_for('faculty.reports_page'))

@faculty_bp.route('/faculty/reports/<int:submission_id>')
def report_detail(submission_id):
    user = _require_faculty()
    submission = tenant_filter(FacultyReportSubmission.query).filter_by(id=submission_id).first_or_404()
    linked_bills = (
        tenant_filter(Bill.query)
        .filter_by(report_submission_id=submission.id)
        .order_by(Bill.bill_date.desc(), Bill.created_at.desc())
        .all()
    )
    verification_summary = _build_submission_verification_data(submission, linked_bills)
    return render_template(
        'faculty/report_detail.html',
        current_user=user,
        submission=submission,
        cycle=submission.cycle,
        linked_bills=linked_bills,
        verification_summary=verification_summary,
    )


@faculty_bp.route('/faculty/reports/<int:submission_id>/verify', methods=['POST'])
def verify_report(submission_id):
    user = _require_faculty()
    submission = tenant_filter(FacultyReportSubmission.query).filter_by(id=submission_id).first_or_404()
    if request.form.get('verification_acknowledged') != '1':
        flash('Please review the verification modal before approving this report.', 'error')
        return redirect(url_for('faculty.report_detail', submission_id=submission.id))
    submission.status = 'verified'
    submission.review_notes = (request.form.get('review_notes') or '').strip()
    submission.verified_at = datetime.utcnow()
    submission.verified_by_id = user.id
    db.session.commit()
    flash('Report verified successfully.', 'success')
    return redirect(url_for('faculty.report_detail', submission_id=submission.id))


@faculty_bp.route('/faculty/reports/<int:submission_id>/reject', methods=['POST'])
def reject_report(submission_id):
    _require_faculty()
    submission = tenant_filter(FacultyReportSubmission.query).filter_by(id=submission_id).first_or_404()
    review_notes = (request.form.get('review_notes') or '').strip()
    if not review_notes:
        flash('Please add review notes before rejecting a report.', 'error')
        return redirect(url_for('faculty.report_detail', submission_id=submission.id))

    submission.status = 'rejected'
    submission.review_notes = review_notes
    submission.verified_at = None
    submission.verified_by_id = None
    db.session.commit()
    flash('Report rejected. The floor can now revise and re-submit.', 'success')
    return redirect(url_for('faculty.report_detail', submission_id=submission.id))


@faculty_bp.route('/faculty/messages/<int:message_id>/archive', methods=['POST'])
def archive_message(message_id):
    _require_faculty()
    message = tenant_filter(FacultyMessage.query).filter_by(id=message_id).first_or_404()
    message.is_archived = True
    db.session.commit()
    flash('Faculty message archived.', 'success')
    return redirect(url_for('faculty.messages'))


@faculty_bp.route('/faculty/messages/<int:message_id>/delete', methods=['POST'])
def delete_message(message_id):
    _require_faculty()
    message = tenant_filter(FacultyMessage.query).filter_by(id=message_id).first_or_404()
    db.session.delete(message)
    db.session.commit()
    flash('Faculty message deleted.', 'success')
    return redirect(url_for('faculty.messages'))


@faculty_bp.route('/faculty/reports/<int:submission_id>/download')
def download_report(submission_id):
    _require_faculty()
    if not current_tenant_faculty_workflow_enabled():
        flash('Faculty workflow is disabled for this tenant right now.', 'error')
        return redirect(url_for('faculty.login'))
    submission = tenant_filter(FacultyReportSubmission.query).filter_by(id=submission_id).first_or_404()
    
    if not submission.storage_path:
        flash('No storage path found for this report.', 'error')
        return redirect(url_for('faculty.report_detail', submission_id=submission.id))

    if os.path.isabs(submission.storage_path):
        abs_path = submission.storage_path
    else:
        abs_path = os.path.normpath(os.path.join(current_app.config["REPORT_STORAGE_ROOT"], submission.storage_path))

    if not os.path.exists(abs_path):
        flash('The stored PDF could not be found on the server.', 'error')
        return redirect(url_for('faculty.report_detail', submission_id=submission.id))

    return send_file(
        abs_path,
        as_attachment=True,
        download_name=submission.stored_filename,
        mimetype='application/pdf',
    )


@faculty_bp.route('/reports/<int:submission_id>/download')
def download_floor_submission(submission_id):
    user = _require_user()
    if not user:
        flash('Your staff session expired. Please sign in again.', 'error')
        return redirect(url_for('auth.staff_login'))
    if user.role not in {'admin', 'pantryHead'}:
        abort(403)
    if not current_tenant_faculty_workflow_enabled():
        flash('Faculty report submission is disabled for this tenant. Use Expenses for manual budgeting and printing.', 'error')
        return redirect(url_for('finance.expenses'))

    submission = tenant_filter(FacultyReportSubmission.query).filter_by(id=submission_id).first_or_404()
    floor = _get_active_floor(user)
    if submission.floor != floor:
        abort(403)

    if not submission.storage_path:
        flash('No storage path found for this report.', 'error')
        return redirect(url_for('faculty.reports_page'))

    if os.path.isabs(submission.storage_path):
        abs_path = submission.storage_path
    else:
        abs_path = os.path.normpath(os.path.join(current_app.config["REPORT_STORAGE_ROOT"], submission.storage_path))

    if not os.path.exists(abs_path):
        flash('The stored PDF could not be found on the server.', 'error')
        return redirect(url_for('faculty.reports_page'))

    return send_file(
        abs_path,
        as_attachment=True,
        download_name=submission.stored_filename,
        mimetype='application/pdf',
    )
