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
from werkzeug.security import check_password_hash

from app import db
from models import (
    Bill,
    Budget,
    Expense,
    FacultyBudgetCycle,
    FacultyReportSubmission,
    Feedback,
    FloorLendBorrow,
    Menu,
    ProcurementItem,
    User,
)
from . import faculty_bp
from ..utils import (
    _ensure_username_from_full_name,
    _get_active_floor,
    _get_tenant_floor_options,
    _require_faculty,
    _require_user,
    tenant_filter,
    visible_budget_condition,
)


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


def _parse_selected_ids(values):
    parsed = []
    for raw in values:
        try:
            parsed.append(int(raw))
        except (TypeError, ValueError):
            continue
    return parsed


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


def _submission_selectable_expenses(floor, existing_submission=None):
    query = tenant_filter(Expense.query).filter(Expense.floor == floor)
    if existing_submission:
        query = query.filter(
            (Expense.report_submission_id.is_(None))
            | (Expense.report_submission_id == existing_submission.id)
        )
    else:
        query = query.filter(Expense.report_submission_id.is_(None))
    return query.order_by(Expense.date.desc(), Expense.created_at.desc()).all()


def _save_submission_file(file_storage, cycle, floor, revision_no):
    filename = _build_report_filename(cycle, floor, revision_no)
    path = os.path.join(_report_storage_dir(), filename)
    file_storage.save(path)
    return filename, path, os.path.getsize(path)


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
    floor_options = _get_tenant_floor_options(user)
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
        for floor in floor_options:
            allocation = next((b for b in cycle_allocations if b.floor == floor), None)
            submission = submissions_by_floor.get(floor)
            if submission and submission.status == 'verified':
                verified_submission_count += 1
            else:
                pending_submission_count += 1
                if active_cycle.submission_deadline < today:
                    overdue_floors += 1
            floor_rows.append({
                'floor': floor,
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


@faculty_bp.route('/faculty/cycles', methods=['GET', 'POST'])
def cycles():
    user = _require_faculty()
    floor_options = _get_tenant_floor_options(user)

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        start_date_raw = request.form.get('start_date')
        end_date_raw = request.form.get('end_date')
        deadline_raw = request.form.get('submission_deadline')
        cycle_notes = (request.form.get('notes') or '').strip()
        action = (request.form.get('action') or 'save_draft').strip()

        if not title or not start_date_raw or not end_date_raw or not deadline_raw:
            flash('Cycle title, term dates, and deadline are required.', 'error')
            return redirect(url_for('faculty.cycles'))

        try:
            start_date = datetime.strptime(start_date_raw, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date()
            submission_deadline = datetime.strptime(deadline_raw, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid cycle date provided.', 'error')
            return redirect(url_for('faculty.cycles'))

        if end_date < start_date:
            flash('Cycle end date must be after the start date.', 'error')
            return redirect(url_for('faculty.cycles'))

        if submission_deadline < start_date:
            flash('Submission deadline cannot be before the cycle starts.', 'error')
            return redirect(url_for('faculty.cycles'))

        status = 'active' if action == 'activate_now' else 'draft'
        if status == 'active':
            existing_active = _current_active_cycle()
            if existing_active:
                flash('Close the current active cycle before activating a new one.', 'error')
                return redirect(url_for('faculty.cycles'))

        cycle = FacultyBudgetCycle(
            title=title,
            start_date=start_date,
            end_date=end_date,
            submission_deadline=submission_deadline,
            status=status,
            notes=cycle_notes,
            created_by_id=user.id,
            activated_at=datetime.utcnow() if status == 'active' else None,
            tenant_id=getattr(g, 'tenant_id', None),
        )
        db.session.add(cycle)
        db.session.flush()

        for floor in floor_options:
            amount_raw = request.form.get(f'amount_{floor}', '0')
            note = (request.form.get(f'faculty_note_{floor}') or '').strip()
            try:
                amount = float(amount_raw or 0)
            except ValueError:
                amount = 0

            db.session.add(Budget(
                floor=floor,
                cycle_id=cycle.id,
                allocated_by_id=user.id,
                amount_allocated=amount,
                allocation_type='faculty_cycle',
                start_date=start_date,
                end_date=end_date,
                notes=cycle_notes or f'Faculty cycle {title}',
                faculty_note=note,
                is_faculty_allocation=True,
                tenant_id=getattr(g, 'tenant_id', None),
            ))

        db.session.commit()
        flash(f'Faculty cycle "{title}" saved successfully.', 'success')
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

    return render_template(
        'faculty/cycle_detail.html',
        current_user=user,
        cycle=cycle,
        floor_rows=floor_rows,
        today=date.today(),
    )


@faculty_bp.route('/faculty/cycles/<int:cycle_id>/activate', methods=['POST'])
def activate_cycle(cycle_id):
    user = _require_faculty()
    cycle = tenant_filter(FacultyBudgetCycle.query).filter_by(id=cycle_id).first_or_404()
    existing_active = _current_active_cycle()
    if existing_active and existing_active.id != cycle.id:
        flash('Close the currently active cycle before activating another one.', 'error')
        return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))

    cycle.status = 'active'
    cycle.activated_at = datetime.utcnow()
    db.session.commit()
    flash('Cycle activated successfully.', 'success')
    return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))


@faculty_bp.route('/faculty/cycles/<int:cycle_id>/close', methods=['POST'])
def close_cycle(cycle_id):
    user = _require_faculty()
    cycle = tenant_filter(FacultyBudgetCycle.query).filter_by(id=cycle_id).first_or_404()
    cycle.status = 'closed'
    cycle.closed_at = datetime.utcnow()
    db.session.commit()
    flash('Cycle closed successfully.', 'success')
    return redirect(url_for('faculty.cycle_detail', cycle_id=cycle.id))


@faculty_bp.route('/reports', methods=['GET', 'POST'])
def reports_page():
    user = _require_user()
    if not user or user.role not in {'admin', 'pantryHead'}:
        abort(403)

    floor = _get_active_floor(user)
    active_cycle = _current_active_cycle()
    allocation = _cycle_for_floor(active_cycle.id, floor) if active_cycle else None
    submission = None
    selectable_bills = []
    selectable_expenses = []

    if active_cycle:
        submission = tenant_filter(FacultyReportSubmission.query).filter_by(
            cycle_id=active_cycle.id,
            floor=floor,
        ).first()

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
            report_title = (request.form.get('report_title') or '').strip() or f"Floor {floor} Report"
            submission_notes = (request.form.get('submission_notes') or '').strip()
            bill_ids = _parse_selected_ids(request.form.getlist('bill_ids'))
            expense_ids = _parse_selected_ids(request.form.getlist('expense_ids'))

            if not upload or not upload.filename:
                flash('Please upload the combined PDF report generated from Expenses.', 'error')
                return redirect(url_for('faculty.reports_page'))

            if not upload.filename.lower().endswith('.pdf'):
                flash('Only PDF uploads are allowed for Faculty submissions.', 'error')
                return redirect(url_for('faculty.reports_page'))

            selected_bills = tenant_filter(Bill.query).filter(Bill.id.in_(bill_ids), Bill.floor == floor).all() if bill_ids else []
            selected_expenses = tenant_filter(Expense.query).filter(Expense.id.in_(expense_ids), Expense.floor == floor).all() if expense_ids else []

            if len(selected_bills) != len(bill_ids) or len(selected_expenses) != len(expense_ids):
                flash('One or more selected finance records were invalid for this floor.', 'error')
                return redirect(url_for('faculty.reports_page'))

            for bill in selected_bills:
                if bill.report_submission_id and (not submission or bill.report_submission_id != submission.id):
                    flash(f'Bill {bill.bill_no} is already linked to another report submission.', 'error')
                    return redirect(url_for('faculty.reports_page'))

            for expense in selected_expenses:
                if expense.report_submission_id and (not submission or expense.report_submission_id != submission.id):
                    flash(f'Legacy expense "{expense.description}" is already linked to another report submission.', 'error')
                    return redirect(url_for('faculty.reports_page'))

            revision_no = (submission.revision_no + 1) if submission else 1
            stored_filename, storage_path, file_size = _save_submission_file(upload, active_cycle, floor, revision_no)

            if submission:
                old_path = submission.storage_path
                submission.report_title = report_title
                submission.status = 'submitted'
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
                _sync_submission_links(submission, selected_bills, selected_expenses)
                if old_path and old_path != storage_path and os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except OSError:
                        pass
            else:
                submission = FacultyReportSubmission(
                    cycle_id=active_cycle.id,
                    floor=floor,
                    uploaded_by_id=user.id,
                    report_title=report_title,
                    status='submitted',
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
                _sync_submission_links(submission, selected_bills, selected_expenses)

            db.session.commit()
            flash('Report submitted to Faculty successfully.', 'success')
            return redirect(url_for('faculty.reports_page'))

        selectable_bills = _submission_selectable_bills(floor, submission if submission and submission.status == 'rejected' else None)
        selectable_expenses = _submission_selectable_expenses(floor, submission if submission and submission.status == 'rejected' else None)

    return render_template(
        'reports.html',
        current_user=user,
        active_floor=floor,
        active_cycle=active_cycle,
        allocation=allocation,
        submission=submission,
        selectable_bills=selectable_bills,
        selectable_expenses=selectable_expenses,
        today=date.today(),
    )


@faculty_bp.route('/faculty/reports/<int:submission_id>')
def report_detail(submission_id):
    user = _require_faculty()
    submission = tenant_filter(FacultyReportSubmission.query).filter_by(id=submission_id).first_or_404()
    return render_template(
        'faculty/report_detail.html',
        current_user=user,
        submission=submission,
        cycle=submission.cycle,
        linked_bills=tenant_filter(Bill.query).filter_by(report_submission_id=submission.id).order_by(Bill.bill_date.desc()).all(),
        linked_expenses=tenant_filter(Expense.query).filter_by(report_submission_id=submission.id).order_by(Expense.date.desc()).all(),
    )


@faculty_bp.route('/faculty/reports/<int:submission_id>/verify', methods=['POST'])
def verify_report(submission_id):
    user = _require_faculty()
    submission = tenant_filter(FacultyReportSubmission.query).filter_by(id=submission_id).first_or_404()
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


@faculty_bp.route('/faculty/reports/<int:submission_id>/download')
def download_report(submission_id):
    _require_faculty()
    submission = tenant_filter(FacultyReportSubmission.query).filter_by(id=submission_id).first_or_404()
    if not submission.storage_path or not os.path.exists(submission.storage_path):
        flash('The stored PDF could not be found on the server.', 'error')
        return redirect(url_for('faculty.report_detail', submission_id=submission.id))

    return send_file(
        submission.storage_path,
        as_attachment=True,
        download_name=submission.stored_filename,
        mimetype='application/pdf',
    )


@faculty_bp.route('/reports/<int:submission_id>/download')
def download_floor_submission(submission_id):
    user = _require_user()
    if not user or user.role not in {'admin', 'pantryHead'}:
        abort(403)

    submission = tenant_filter(FacultyReportSubmission.query).filter_by(id=submission_id).first_or_404()
    floor = _get_active_floor(user)
    if submission.floor != floor:
        abort(403)
    if not submission.storage_path or not os.path.exists(submission.storage_path):
        flash('The stored PDF could not be found on the server.', 'error')
        return redirect(url_for('faculty.reports_page'))

    return send_file(
        submission.storage_path,
        as_attachment=True,
        download_name=submission.stored_filename,
        mimetype='application/pdf',
    )
