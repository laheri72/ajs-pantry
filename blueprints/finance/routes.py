from flask import render_template, request, redirect, url_for, flash, jsonify, abort, g
from app import db
from models import User, Expense, ProcurementItem, Budget, FloorLendBorrow, Bill, ExpensePrintReport, ExpensePrintReportBill
from .services.parser_factory import ParserFactory
from datetime import datetime, date
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload
import logging
from . import finance_bp
from ..budgeting import build_floor_budget_ledger
from ..utils import (
    _require_user,
    _get_active_floor,
    _get_floor_options_for_admin,
    current_tenant_faculty_workflow_enabled,
    tenant_filter,
    visible_budget_condition,
)
from ..pantry.routes import _clear_dashboard_cache

@finance_bp.route('/expenses', methods=['GET', 'POST'])
def expenses():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    floor = _get_active_floor(user)
    
    # Permission check: Read-only for members, manage for PH/Admin
    is_manager = user.role in ['admin', 'pantryHead']

    # 1. Handle actual_cost updates and Bills
    if request.method == 'POST' and is_manager:
        action = request.form.get('action')
        if action == 'record_cost':
            try:
                item_id = int(request.form.get('item_id') or 0)
                cost = float(request.form.get('actual_cost') or 0)
            except ValueError:
                flash('Invalid cost value', 'error')
                return redirect(url_for('finance.expenses'))

            item = tenant_filter(ProcurementItem.query).filter_by(id=item_id).first()
            if item and (user.role == 'admin' or item.floor == user.floor):
                if item.status != 'completed':
                    flash('Costs can only be recorded for completed items.', 'error')
                else:
                    item.actual_cost = cost
                    item.expense_recorded_at = datetime.utcnow()
                    
                    # If item belongs to a bill, update bill total
                    if item.bill_id:
                        bill = tenant_filter(Bill.query).filter_by(id=item.bill_id).first()
                        if bill:
                            # Recalculate total amount from all items in this bill
                            bill_total = tenant_filter(db.session.query(func.sum(ProcurementItem.actual_cost))).filter(ProcurementItem.bill_id == bill.id).scalar() or 0
                            bill.total_amount = bill_total

                    db.session.commit()
                    _clear_dashboard_cache(getattr(g, 'tenant_id', None), floor)
                    flash(f'Cost for {item.item_name} recorded.', 'success')
            return redirect(url_for('finance.expenses'))

        if action == 'record_bill':
            try:
                item_ids = request.form.getlist('item_ids[]')
                costs = request.form.getlist('costs[]')
                bill_no = (request.form.get('bill_no') or '').strip()
                bill_date_str = request.form.get('bill_date')
                shop_name = (request.form.get('shop_name') or '').strip()
                
                if not bill_no or not bill_date_str:
                    flash('Bill number and date are required', 'error')
                    return redirect(url_for('finance.expenses'))
                
                if not item_ids:
                    flash('Please select at least one item to include in the bill.', 'error')
                    return redirect(url_for('finance.expenses'))

                bill_date = datetime.strptime(bill_date_str, '%Y-%m-%d').date()
                
                # Create the bill
                bill = Bill(
                    bill_no=bill_no,
                    bill_date=bill_date,
                    shop_name=shop_name,
                    floor=floor,
                    total_amount=0,
                    tenant_id=getattr(g, 'tenant_id', None)
                )
                db.session.add(bill)
                db.session.flush() # Get bill.id
                
                total_amount = 0
                for i in range(len(item_ids)):
                    item_id = int(item_ids[i])
                    cost = float(costs[i] or 0)
                    
                    item = tenant_filter(ProcurementItem.query).filter_by(id=item_id).first()
                    if item and (user.role == 'admin' or item.floor == floor):
                        item.actual_cost = cost
                        item.bill_id = bill.id
                        item.expense_recorded_at = datetime.utcnow()
                        total_amount += cost
                
                bill.total_amount = total_amount
                db.session.commit()
                _clear_dashboard_cache(getattr(g, 'tenant_id', None), floor)
                flash(f'Bill {bill_no} recorded successfully with {len(item_ids)} items.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error recording bill: {str(e)}', 'error')
            return redirect(url_for('finance.expenses'))

    faculty_workflow_enabled = current_tenant_faculty_workflow_enabled()
    budget_ledger = build_floor_budget_ledger(
        floor=floor,
        faculty_workflow_enabled=faculty_workflow_enabled,
    )
    current_budget_period = budget_ledger['current_period']
    total_budget = budget_ledger['current_allocated_amount']
    total_spent = budget_ledger['current_spent_amount']
    remaining_balance = budget_ledger['current_remaining_balance']
    current_available_budget = budget_ledger['current_available_budget']
    carryforward_balance = budget_ledger['carryforward_balance']

    # Tiny insight metrics: floor-level all-time totals (across periods).
    floor_total_budget = float(
        tenant_filter(db.session.query(func.sum(Budget.amount_allocated))).filter(
            Budget.floor == floor,
            visible_budget_condition(faculty_workflow_enabled),
        ).scalar() or 0
    )
    floor_total_spent_proc = float(
        tenant_filter(db.session.query(func.sum(ProcurementItem.actual_cost))).filter(
            ProcurementItem.floor == floor,
            ProcurementItem.status == 'completed',
        ).scalar() or 0
    )
    floor_total_spent_legacy = float(
        tenant_filter(db.session.query(func.sum(Expense.amount))).filter(
            Expense.floor == floor,
        ).scalar() or 0
    )
    floor_total_spent = floor_total_spent_proc + floor_total_spent_legacy

    # 3. Data for Ledger
    # Get completed procurements for this floor that are NOT yet in a bill
    # This list is usually small (pending to be recorded), so we keep it as .all()
    pending_procurements = tenant_filter(ProcurementItem.query).filter_by(
        floor=floor, status='completed', bill_id=None
    ).order_by(ProcurementItem.created_at.desc()).all()
    
    # Get all bills for this floor (PAGINATED - ACTIVE ONLY)
    bills_page = request.args.get('bills_page', 1, type=int)
    bills_pagination = tenant_filter(Bill.query).options(joinedload(Bill.items)).filter_by(
        floor=floor, is_archived=False
    ).order_by(Bill.bill_date.desc()).paginate(page=bills_page, per_page=15, error_out=False)
    bills = bills_pagination.items
    
    # Get ALL active bills for this floor (UNPAGINATED) - for Print Module
    all_active_bills = tenant_filter(Bill.query).filter_by(
        floor=floor, is_archived=False
    ).order_by(Bill.bill_date.desc()).all()
    
    # Get all archived bills for this floor (PAGINATED)
    archived_page = request.args.get('archived_page', 1, type=int)
    archived_pagination = tenant_filter(Bill.query).options(joinedload(Bill.items)).filter_by(
        floor=floor, is_archived=True
    ).order_by(Bill.bill_date.desc()).paginate(page=archived_page, per_page=15, error_out=False)
    archived_bills = archived_pagination.items
    
    # Get budget history
    budget_periods = budget_ledger['periods']
    active_cycle = budget_ledger['active_cycle'] if faculty_workflow_enabled else None
    active_cycle_allocation = budget_ledger['active_cycle_allocation']
    editable_budget_ids = []
    if is_manager and not faculty_workflow_enabled:
        manual_budget_query = tenant_filter(Budget.query).filter(
            Budget.floor == floor,
            Budget.cycle_id.is_(None),
            Budget.is_faculty_allocation.is_(False),
        )
        latest_manual_budget = manual_budget_query.order_by(Budget.created_at.desc(), Budget.id.desc()).first()
        if latest_manual_budget:
            editable_budget_ids.append(latest_manual_budget.id)

        today_value = date.today()
        current_manual_budget = manual_budget_query.filter(
            Budget.start_date <= today_value,
            or_(Budget.end_date.is_(None), Budget.end_date >= today_value),
        ).order_by(Budget.start_date.desc(), Budget.created_at.desc(), Budget.id.desc()).first()
        if current_manual_budget and current_manual_budget.id not in editable_budget_ids:
            editable_budget_ids.append(current_manual_budget.id)
    
    # Legacy expenses for reference (PAGINATED)
    legacy_page = request.args.get('legacy_page', 1, type=int)
    legacy_pagination = tenant_filter(Expense.query).filter_by(floor=floor).order_by(Expense.date.desc()).paginate(page=legacy_page, per_page=15, error_out=False)
    legacy_expenses = legacy_pagination.items

    # Get unique shop names for suggestions
    unique_shops = tenant_filter(db.session.query(Bill.shop_name)).filter(
        Bill.floor == floor, Bill.shop_name.isnot(None), Bill.shop_name != ''
    ).distinct().order_by(Bill.shop_name).all()
    unique_shops = [s[0] for s in unique_shops]

    # Calculate suggested next bill number
    last_bill = tenant_filter(Bill.query).filter_by(floor=floor).order_by(Bill.created_at.desc()).first()
    suggested_bill_no = "1001"
    if last_bill and last_bill.bill_no:
        try:
            # Try to increment if it's purely numeric
            if last_bill.bill_no.isdigit():
                suggested_bill_no = str(int(last_bill.bill_no) + 1)
            else:
                # Handle cases like INV-1001 by finding the numeric part at the end
                import re
                match = re.search(r'(\d+)$', last_bill.bill_no)
                if match:
                    number_part = match.group(1)
                    prefix = last_bill.bill_no[:-len(number_part)]
                    new_number = str(int(number_part) + 1).zfill(len(number_part))
                    suggested_bill_no = prefix + new_number
        except (ValueError, TypeError):
            pass

    return render_template(
        'expenses.html',
        total_budget=total_budget,
        total_spent=total_spent,
        remaining_balance=remaining_balance,
        pending_procurements=pending_procurements,
        bills=bills,
        all_active_bills=all_active_bills,
        bills_pagination=bills_pagination,
        archived_bills=archived_bills,
        archived_pagination=archived_pagination,
        budget_periods=budget_periods,
        legacy_expenses=legacy_expenses,
        legacy_pagination=legacy_pagination,
        unique_shops=unique_shops,
        suggested_bill_no=suggested_bill_no,
        is_manager=is_manager,
        faculty_workflow_enabled=faculty_workflow_enabled,
        current_budget_period=current_budget_period,
        current_available_budget=current_available_budget,
        carryforward_balance=carryforward_balance,
        floor_total_budget=floor_total_budget,
        floor_total_spent=floor_total_spent,
        active_cycle=active_cycle,
        active_cycle_allocation=active_cycle_allocation,
        editable_budget_ids=editable_budget_ids,
        today=date.today(),
        current_user=user,
        active_floor=floor
    )

import os
from werkzeug.utils import secure_filename
import re

def _tenant_slug_gen():
    tenant_name = getattr(g, 'tenant_name', None) or 'tenant'
    slug = re.sub(r'[^a-z0-9]+', '-', tenant_name.lower()).strip('-')
    return slug or 'tenant'

def _finance_report_storage_dir():
    from flask import current_app
    base_dir = current_app.config.get("REPORT_STORAGE_ROOT", os.path.join(current_app.root_path, "tmp", "reports"))
    path = os.path.join(base_dir, _tenant_slug_gen())
    os.makedirs(path, exist_ok=True)
    return path


@finance_bp.route('/expenses/print-reports/save', methods=['POST'])
def save_print_report():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json or {}
    floor = _get_active_floor(user)
    report_title = (data.get('report_title') or '').strip() or 'Expense Report'
    try:
        requested_report_budget = float(data.get('report_budget') or 0)
        total_spent = float(data.get('total_spent') or 0)
        remaining_balance = float(data.get('remaining_balance') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid report totals'}), 400
    summary_bill_ids = data.get('summary_bill_ids') or []
    voucher_bill_ids = data.get('voucher_bill_ids') or []

    try:
        summary_bill_ids = [int(x) for x in summary_bill_ids]
        voucher_bill_ids = [int(x) for x in voucher_bill_ids]
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid bill selection'}), 400

    all_bill_ids = sorted(set(summary_bill_ids + voucher_bill_ids))
    if not all_bill_ids:
        return jsonify({'error': 'Please select at least one bill to save this report.'}), 400

    bills = tenant_filter(Bill.query).filter(Bill.id.in_(all_bill_ids), Bill.floor == floor).all()
    if len(bills) != len(all_bill_ids):
        return jsonify({'error': 'One or more bills were invalid for this floor.'}), 400

    faculty_workflow_enabled = current_tenant_faculty_workflow_enabled()
    budget_ledger = build_floor_budget_ledger(
        floor=floor,
        faculty_workflow_enabled=faculty_workflow_enabled,
    )
    active_cycle = budget_ledger['active_cycle'] if faculty_workflow_enabled else None
    # Use user-selected print-modal budget in manual/inactive-cycle mode.
    # Keep budget locked to ledger only when an active Faculty cycle is present.
    report_budget = budget_ledger['current_available_budget'] if active_cycle else requested_report_budget
    remaining_balance = report_budget - total_spent

    print_report = ExpensePrintReport(
        cycle_id=active_cycle.id if active_cycle else None,
        floor=floor,
        report_title=report_title,
        report_budget=report_budget,
        total_spent=total_spent,
        remaining_balance=remaining_balance,
        created_by_id=user.id,
        tenant_id=getattr(g, 'tenant_id', None)
    )
    db.session.add(print_report)
    db.session.flush()

    summary_set = set(summary_bill_ids)
    voucher_set = set(voucher_bill_ids)
    for bill in bills:
        db.session.add(ExpensePrintReportBill(
            print_report_id=print_report.id,
            bill_id=bill.id,
            include_in_summary=bill.id in summary_set,
            include_as_voucher=bill.id in voucher_set,
            tenant_id=getattr(g, 'tenant_id', None)
        ))

    db.session.commit()
    return jsonify({
        'success': True,
        'print_report_id': print_report.id,
        'report_title': print_report.report_title,
    })

@finance_bp.route('/expenses/print-reports/<int:report_id>/upload-pdf', methods=['POST'])
def upload_print_report_pdf(report_id):
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        return jsonify({'error': 'Unauthorized'}), 403

    floor = _get_active_floor(user)
    report = tenant_filter(ExpensePrintReport.query).filter_by(id=report_id).first()
    
    if not report or (user.role != 'admin' and report.floor != floor):
        return jsonify({'error': 'Report not found or access denied.'}), 404

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Size Guard: Max 5MB
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size > 5 * 1024 * 1024:
        return jsonify({'error': 'File size exceeds 5MB limit.'}), 400

    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Only PDF files are supported.'}), 400

    try:
        from flask import current_app
        storage_dir = _finance_report_storage_dir()
        
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        new_filename = f"{_tenant_slug_gen()}_Irregular_Floor-{report.floor}_{report.id}_{timestamp}.pdf"
        
        path = os.path.join(storage_dir, new_filename)
        file.save(path)
        
        relative_path = f"{_tenant_slug_gen()}/{new_filename}"
        
        # Remove old file if it existed
        if report.storage_path:
            base_d = current_app.config.get("REPORT_STORAGE_ROOT", os.path.join(current_app.root_path, "tmp", "reports"))
            old_abs_path = os.path.normpath(os.path.join(base_d, report.storage_path))
            if os.path.exists(old_abs_path):
                try:
                    os.remove(old_abs_path)
                except OSError:
                    pass
            
        report.original_filename = file.filename
        report.stored_filename = new_filename
        report.storage_path = relative_path
        report.file_size_bytes = file_size
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'File securely uploaded and saved.'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Ad-hoc PDF Upload Error: {str(e)}")
        return jsonify({'error': f"Failed to process upload: {str(e)}"}), 500

@finance_bp.route('/bills/<int:bill_id>/archive', methods=['POST'])
def archive_bill(bill_id):
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)

    bill = tenant_filter(Bill.query).filter_by(id=bill_id).first_or_404()
    if user.role != 'admin' and bill.floor != user.floor:
        abort(403)

    bill.is_archived = not bill.is_archived
    db.session.commit()
    status = "archived" if bill.is_archived else "restored"
    flash(f'Bill {bill.bill_no} has been {status}.', 'success')
    return redirect(url_for('finance.expenses'))

@finance_bp.route('/bills/bulk-archive', methods=['POST'])
def bulk_archive_bills():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    bill_ids = data.get('bill_ids', [])
    
    if not bill_ids:
        return jsonify({'error': 'No bill IDs provided'}), 400

    try:
        bills = tenant_filter(Bill.query).filter(Bill.id.in_(bill_ids)).all()
        archived_count = 0
        for bill in bills:
            # Floor check for PH
            if user.role == 'admin' or bill.floor == user.floor:
                bill.is_archived = True
                archived_count += 1
        
        db.session.commit()
        return jsonify({'success': True, 'count': archived_count})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@finance_bp.route('/bills/<int:bill_id>/delete', methods=['POST'])
def delete_bill(bill_id):
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)

    bill = tenant_filter(Bill.query).filter_by(id=bill_id).first_or_404()
    if user.role != 'admin' and bill.floor != user.floor:
        abort(403)

    for item in bill.items:
        item.bill_id = None
        # Also clear costs so they are truly "pending" and not counting in Total Spent
        item.actual_cost = None
        item.expense_recorded_at = None
    
    db.session.delete(bill)
    db.session.commit()
    _clear_dashboard_cache(getattr(g, 'tenant_id', None), bill.floor)
    flash('Bill record removed. Items returned to pending list (costs reset).', 'success')
    return redirect(url_for('finance.expenses'))

@finance_bp.route('/bills/<int:bill_id>/delete-permanent', methods=['POST'])
def delete_bill_permanent(bill_id):
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)

    bill = tenant_filter(Bill.query).filter_by(id=bill_id).first_or_404()
    if user.role != 'admin' and bill.floor != user.floor:
        abort(403)

    # Delete all items associated with this bill permanently
    for item in bill.items:
        db.session.delete(item)
    
    db.session.delete(bill)
    db.session.commit()
    flash('Bill and all its associated items have been permanently deleted.', 'success')
    return redirect(url_for('finance.expenses'))

@finance_bp.route('/reconcile/atomic', methods=['POST'])
def atomic_reconcile():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    bill_id = data.get('bill_id')
    reconciliations = data.get('reconciliations', []) # List of {procurement_id: X, cost: Y}

    if not bill_id:
        return jsonify({'error': 'Bill ID is required'}), 400

    bill = tenant_filter(Bill.query).filter_by(id=bill_id).first()
    if not bill:
        return jsonify({'error': 'Bill not found'}), 404

    try:
        total_reconciled_cost = 0
        for rec in reconciliations:
            proc_id = rec.get('procurement_id')
            cost = float(rec.get('cost') or 0)
            
            item = tenant_filter(ProcurementItem.query).filter_by(id=proc_id).first()
            if item and (user.role == 'admin' or item.floor == bill.floor):
                item.actual_cost = cost
                item.bill_id = bill.id
                item.status = 'completed'
                item.expense_recorded_at = datetime.utcnow()
                total_reconciled_cost += cost
        
        # Update bill total if it was a manual reconciliation adding to an existing bill
        # Or if we want the bill to reflect the sum of its items
        current_total = tenant_filter(db.session.query(func.sum(ProcurementItem.actual_cost))).filter(ProcurementItem.bill_id == bill.id).scalar() or 0
        bill.total_amount = current_total
        
        db.session.commit()
        _clear_dashboard_cache(getattr(g, 'tenant_id', None), bill.floor)
        return jsonify({'success': True, 'reconciled_count': len(reconciliations), 'new_total': float(bill.total_amount)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@finance_bp.route('/procurement/unbilled', methods=['GET'])
def get_unbilled_procurement():
    user = _require_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    floor = _get_active_floor(user)
    # Get items that are EITHER completed and unbilled, OR still pending
    # This allows matching a bill to something that was just bought but not yet marked done
    items = tenant_filter(ProcurementItem.query).filter(
        ProcurementItem.floor == floor,
        ProcurementItem.bill_id == None
    ).order_by(ProcurementItem.status.desc(), ProcurementItem.created_at.desc()).all()

    return jsonify({
        'items': [{
            'id': i.id,
            'name': i.item_name,
            'quantity': i.quantity,
            'status': i.status,
            'category': i.category,
            'created_at': i.created_at.strftime('%Y-%m-%d')
        } for i in items]
    })

@finance_bp.route('/reconcile/atomic/full', methods=['POST'])
def atomic_reconcile_full():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    floor = _get_active_floor(user)
    try:
        bill_date_str = data.get('bill_date')
        bill_date = datetime.strptime(bill_date_str, '%Y-%m-%d').date() if bill_date_str else date.today()

        # 1. Create the Bill
        bill = Bill(
            bill_no=data.get('bill_no') or f"REC-{int(datetime.utcnow().timestamp())}",
            bill_date=bill_date,
            shop_name=data.get('shop_name') or 'Generic Vendor',
            total_amount=data.get('total_amount', 0),
            floor=floor,
            source='receipt_scan',
            original_filename=data.get('filename'),
            tenant_id=getattr(g, 'tenant_id', None)
        )
        db.session.add(bill)
        db.session.flush()

        # 2. Create NEW ProcurementItems
        for item_data in data.get('new_items', []):
            item = ProcurementItem(
                item_name=item_data.get('name'),
                quantity=item_data.get('quantity'),
                category='other',
                priority='medium',
                status='completed',
                floor=floor,
                created_by_id=user.id,
                actual_cost=item_data.get('cost'),
                expense_recorded_at=datetime.utcnow(),
                bill_id=bill.id,
                tenant_id=getattr(g, 'tenant_id', None)
            )
            db.session.add(item)

        # 3. Reconcile EXISTING ProcurementItems
        for rec in data.get('reconciliations', []):
            proc_id = rec.get('procurement_id')
            cost = float(rec.get('cost') or 0)
            
            item = tenant_filter(ProcurementItem.query).filter_by(id=proc_id).first()
            if item and (user.role == 'admin' or item.floor == floor):
                item.actual_cost = cost
                item.bill_id = bill.id
                item.status = 'completed'
                item.expense_recorded_at = datetime.utcnow()

        # 4. Final Total Sync
        db.session.flush() # Ensure all items have costs applied
        
        # Priority: 1. Manually edited total from payload, 2. Sum of items
        payload_total = float(data.get('total_amount') or 0)
        if payload_total > 0:
            bill.total_amount = payload_total
        else:
            final_total = tenant_filter(db.session.query(func.sum(ProcurementItem.actual_cost))).filter(ProcurementItem.bill_id == bill.id).scalar() or 0
            bill.total_amount = final_total

        db.session.commit()
        _clear_dashboard_cache(getattr(g, 'tenant_id', None), floor)
        return jsonify({'success': True, 'bill_id': bill.id})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Atomic Full Reconcile Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@finance_bp.route('/budgets/add', methods=['POST'])
def add_budget():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)
    if current_tenant_faculty_workflow_enabled():
        flash('Manual budget allocation is disabled while Faculty workflow is enabled for this tenant.', 'error')
        return redirect(url_for('finance.expenses'))

    floor = _get_active_floor(user)
    try:
        amount = float(request.form.get('amount') or 0)
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date_raw = request.form.get('end_date')
        end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date() if end_date_raw else None
    except Exception:
        flash('Invalid budget data', 'error')
        return redirect(url_for('finance.expenses'))

    budget = Budget(
        floor=floor,
        amount_allocated=amount,
        allocation_type=(request.form.get('allocation_type') or 'manual').strip() or 'manual',
        start_date=start_date,
        end_date=end_date,
        notes=request.form.get('notes'),
        allocated_by_id=user.id,
        is_faculty_allocation=False,
        tenant_id=getattr(g, 'tenant_id', None)
    )
    db.session.add(budget)
    db.session.commit()
    _clear_dashboard_cache(getattr(g, 'tenant_id', None), floor)
    flash('Manual budget allocation added.', 'success')
    return redirect(url_for('finance.expenses'))

@finance_bp.route('/budgets/<int:budget_id>/delete', methods=['POST'])
def delete_budget(budget_id):
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)
    if current_tenant_faculty_workflow_enabled():
        flash('Manual budget deletion is disabled while Faculty workflow is enabled for this tenant.', 'error')
        return redirect(url_for('finance.expenses'))

    budget = tenant_filter(Budget.query).filter_by(id=budget_id).first_or_404()
    if budget.cycle_id is not None:
        flash('Faculty cycle budgets can only be managed from the Faculty portal.', 'error')
        return redirect(url_for('finance.expenses'))
    if user.role != 'admin' and budget.floor != user.floor:
        abort(403)

    db.session.delete(budget)
    db.session.commit()
    _clear_dashboard_cache(getattr(g, 'tenant_id', None), budget.floor)
    flash('Manual budget allocation deleted successfully.', 'success')
    return redirect(url_for('finance.expenses'))

@finance_bp.route('/budgets/<int:budget_id>/update', methods=['POST'])
def update_budget(budget_id):
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)
    if current_tenant_faculty_workflow_enabled():
        flash('Manual budget edits are disabled while Faculty workflow is enabled for this tenant.', 'error')
        return redirect(url_for('finance.expenses'))

    budget = tenant_filter(Budget.query).filter_by(id=budget_id).first_or_404()
    if budget.cycle_id is not None or budget.is_faculty_allocation:
        flash('Faculty cycle budgets can only be managed from the Faculty portal.', 'error')
        return redirect(url_for('finance.expenses'))
    if user.role != 'admin' and budget.floor != user.floor:
        abort(403)

    manual_budget_query = tenant_filter(Budget.query).filter(
        Budget.floor == budget.floor,
        Budget.cycle_id.is_(None),
        Budget.is_faculty_allocation.is_(False),
    )
    latest_manual_budget = manual_budget_query.order_by(Budget.created_at.desc(), Budget.id.desc()).first()
    today_value = date.today()
    current_manual_budget = manual_budget_query.filter(
        Budget.start_date <= today_value,
        or_(Budget.end_date.is_(None), Budget.end_date >= today_value),
    ).order_by(Budget.start_date.desc(), Budget.created_at.desc(), Budget.id.desc()).first()
    editable_budget_ids = {
        row_id for row_id in [
            latest_manual_budget.id if latest_manual_budget else None,
            current_manual_budget.id if current_manual_budget else None,
        ] if row_id is not None
    }
    if budget.id not in editable_budget_ids:
        flash('Only the latest or current manual budget can be edited.', 'error')
        return redirect(url_for('finance.expenses'))

    try:
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date_raw = request.form.get('end_date')
        end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date() if end_date_raw else None
    except Exception:
        flash('Invalid budget dates.', 'error')
        return redirect(url_for('finance.expenses'))

    if end_date and end_date <= start_date:
        flash('End date must be after the start date.', 'error')
        return redirect(url_for('finance.expenses'))

    budget.start_date = start_date
    budget.end_date = end_date
    budget.notes = (request.form.get('notes') or '').strip() or None

    db.session.commit()
    _clear_dashboard_cache(getattr(g, 'tenant_id', None), budget.floor)
    flash('Budget period updated successfully.', 'success')
    return redirect(url_for('finance.expenses'))

@finance_bp.route('/expenses/<int:expense_id>/delete', methods=['POST'])
def delete_expense(expense_id):
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    if user.role not in ['admin', 'pantryHead']:
        abort(403)

    expense = tenant_filter(Expense.query).filter_by(id=expense_id).first()
    if not expense:
        abort(404)
    if user.role == 'pantryHead' and expense.floor != user.floor:
        abort(404)

    db.session.delete(expense)
    db.session.commit()
    _clear_dashboard_cache(getattr(g, 'tenant_id', None), expense.floor)
    flash('Expense deleted successfully', 'success')
    return redirect(url_for('finance.expenses'))

@finance_bp.route('/lend-borrow')
def lend_borrow():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    if user.role not in ['admin', 'pantryHead']:
        abort(403)

    floor = _get_active_floor(user)
    
    if user.role == 'admin':
        pending = tenant_filter(FloorLendBorrow.query).filter_by(status='pending').order_by(FloorLendBorrow.created_at.desc()).all()
        returned = tenant_filter(FloorLendBorrow.query).filter_by(status='returned').order_by(FloorLendBorrow.borrower_marked_at.desc()).all()
        completed = tenant_filter(FloorLendBorrow.query).filter_by(status='completed').order_by(FloorLendBorrow.lender_verified_at.desc()).limit(100).all()
    else:
        query = tenant_filter(FloorLendBorrow.query).filter(or_(FloorLendBorrow.lender_floor == floor, FloorLendBorrow.borrower_floor == floor))
        
        pending = query.filter(FloorLendBorrow.status == 'pending').order_by(FloorLendBorrow.created_at.desc()).all()
        returned = query.filter(FloorLendBorrow.status == 'returned').order_by(FloorLendBorrow.borrower_marked_at.desc()).all()
        completed = query.filter(FloorLendBorrow.status == 'completed').order_by(FloorLendBorrow.lender_verified_at.desc()).limit(50).all()

    return render_template(
        'lend_borrow.html',
        pending=pending,
        returned=returned,
        completed=completed,
        floor_options=_get_floor_options_for_admin(),
        current_user=user,
        active_floor=floor
    )

@finance_bp.route('/lend-borrow/create', methods=['POST'])
def create_lend_borrow():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)

    floor = _get_active_floor(user)
    borrower_floor = int(request.form.get('borrower_floor'))
    
    if borrower_floor == floor:
        flash('You cannot lend to your own floor.', 'error')
        return redirect(url_for('finance.lend_borrow'))

    new_record = FloorLendBorrow(
        lender_floor=floor,
        borrower_floor=borrower_floor,
        item_name=request.form.get('item_name'),
        quantity=request.form.get('quantity'),
        item_type=request.form.get('item_type'),
        notes=request.form.get('notes'),
        created_by_id=user.id,
        status='pending',
        tenant_id=getattr(g, 'tenant_id', None)
    )
    db.session.add(new_record)
    db.session.commit()
    flash('Lend request created.', 'success')
    return redirect(url_for('finance.lend_borrow'))

@finance_bp.route('/lend-borrow/<int:record_id>/mark-returned', methods=['POST'])
def mark_returned(record_id):
    user = _require_user()
    if not user:
        abort(401)

    if user.role not in ['admin', 'pantryHead']:
        abort(403)

    record = tenant_filter(FloorLendBorrow.query).filter_by(id=record_id).first_or_404()
    floor = _get_active_floor(user)

    if user.role != 'admin' and record.borrower_floor != floor:
        abort(403)

    if record.status != 'pending':
        flash('Only pending items can be marked as returned.', 'error')
        return redirect(url_for('finance.lend_borrow'))

    record.status = 'returned'
    record.borrower_marked_at = datetime.utcnow()
    db.session.commit()
    flash('Item marked as returned. Lender must now verify.', 'success')
    return redirect(url_for('finance.lend_borrow'))

@finance_bp.route('/lend-borrow/<int:record_id>/verify', methods=['POST'])
def verify_return(record_id):
    user = _require_user()
    if not user:
        abort(401)

    if user.role not in ['admin', 'pantryHead']:
        abort(403)

    record = tenant_filter(FloorLendBorrow.query).filter_by(id=record_id).first_or_404()
    floor = _get_active_floor(user)
    action = request.form.get('action')

    if user.role != 'admin' and record.lender_floor != floor:
        abort(403)

    if record.status != 'returned':
        flash('Only returned items can be verified.', 'error')
        return redirect(url_for('finance.lend_borrow'))

    if action == 'confirm':
        record.status = 'completed'
        record.lender_verified_at = datetime.utcnow()
        flash('Return verified and completed.', 'success')
    elif action == 'reject':
        record.status = 'pending'
        record.borrower_marked_at = None
        flash('Return rejected. Transaction reverted to pending.', 'warning')
    
    db.session.commit()
    return redirect(url_for('finance.lend_borrow'))

import uuid
from flask import current_app

@finance_bp.route('/expenses/import-receipt', methods=['POST'])
def import_receipt():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        return jsonify({'error': 'Unauthorized'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # 1. Size Guard: Max 5MB
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size > 5 * 1024 * 1024:
        return jsonify({'error': 'File size exceeds 5MB limit.'}), 400

    # 2. MIME Validation
    mime_type = file.content_type
    allowed_mimes = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']
    if mime_type not in allowed_mimes:
        return jsonify({'error': f"Unsupported file type: {mime_type}"}), 400

    try:
        # Check if RQ is available
        if hasattr(current_app, 'task_queue') and current_app.task_queue:
            # Async Path: Save to temp and enqueue
            temp_dir = os.path.join(current_app.root_path, 'tmp', 'receipts')
            os.makedirs(temp_dir, exist_ok=True)
            
            # Generate a unique task ID
            task_id = str(uuid.uuid4())
            temp_path = os.path.join(temp_dir, f"{task_id}_{file.filename}")
            file.save(temp_path)
            
            # Enqueue the job
            current_app.task_queue.enqueue(
                'blueprints.finance.routes._process_receipt_worker',
                temp_path,
                mime_type,
                file.filename,
                job_id=task_id
            )
            
            return jsonify({'status': 'processing', 'task_id': task_id})
        
        # Sync Fallback
        text = ParserFactory.get_text(file.stream, mime_type)
        if text == "ERROR_TESSERACT_NOT_FOUND":
            return jsonify({'error': 'OCR Engine (Tesseract) is not installed on the server.'}), 500
            
        if not text:
            return jsonify({'error': 'Failed to extract text from receipt.'}), 500
        
        parser = ParserFactory.get_parser(text)
        receipt_data = parser.parse(text)
        
        if not receipt_data:
            return jsonify({'error': 'Failed to parse extracted text.'}), 500
            
        data = receipt_data.to_dict()
        data['filename'] = file.filename
        return jsonify(data)
    except Exception as e:
        logging.error(f"Receipt Import Error: {str(e)}")
        return jsonify({'error': f"Failed to parse receipt: {str(e)}"}), 500

def _process_receipt_worker(file_path, mime_type, original_filename):
    """RQ Worker: Processes the receipt from a temporary file."""
    from app import app
    with app.app_context():
        try:
            with open(file_path, 'rb') as f:
                text = ParserFactory.get_text(f, mime_type)
                
            if not text or text == "ERROR_TESSERACT_NOT_FOUND":
                return {'error': 'OCR_FAILED'}
            
            parser = ParserFactory.get_parser(text)
            receipt_data = parser.parse(text)
            
            if not receipt_data:
                return {'error': 'PARSE_FAILED'}
            
            data = receipt_data.to_dict()
            data['filename'] = original_filename
            return data
        except Exception as e:
            logging.error(f"Worker Error: {e}")
            return {'error': str(e)}
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

@finance_bp.route('/expenses/import-status/<task_id>', methods=['GET'])
def check_import_status(task_id):
    """Checks the status of an async receipt processing task."""
    if not hasattr(current_app, 'task_queue') or not current_app.task_queue:
        return jsonify({'error': 'Background processing not configured'}), 400
        
    job = current_app.task_queue.fetch_job(task_id)
    if not job:
        return jsonify({'status': 'not_found'}), 404
        
    if job.is_finished:
        result = job.result
        if isinstance(result, dict) and 'error' in result:
            return jsonify({'status': 'failed', 'error': result['error']})
        return jsonify({'status': 'completed', 'data': result})
    elif job.is_failed:
        return jsonify({'status': 'failed'})
    else:
        return jsonify({'status': 'processing'})

@finance_bp.route('/expenses/save-imported-bill', methods=['POST'])
def save_imported_bill():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    floor = _get_active_floor(user)

    try:
        date_str = data.get('bill_date')
        if date_str:
            bill_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            bill_date = date.today()

        bill = Bill(
            bill_no=data.get('bill_no') or f"REC-{int(datetime.utcnow().timestamp())}",
            bill_date=bill_date,
            shop_name=data.get('shop_name') or 'Generic Vendor',
            total_amount=data.get('total_amount', 0),
            floor=floor,
            source='receipt_scan',
            original_filename=data.get('filename'),
            tenant_id=getattr(g, 'tenant_id', None)
        )
        db.session.add(bill)
        db.session.flush()

        for item_data in data.get('items', []):
            item = ProcurementItem(
                item_name=item_data.get('name'),
                quantity=item_data.get('quantity'),
                category='other',
                priority='medium',
                status='completed',
                floor=floor,
                created_by_id=user.id,
                actual_cost=item_data.get('cost'),
                expense_recorded_at=datetime.utcnow(),
                bill_id=bill.id,
                tenant_id=getattr(g, 'tenant_id', None)
            )
            db.session.add(item)

        db.session.commit()
        _clear_dashboard_cache(getattr(g, 'tenant_id', None), floor)
        return jsonify({'success': True, 'bill_id': bill.id})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Save Imported Bill Error: {str(e)}")
        return jsonify({'error': f"Failed to save bill: {str(e)}"}), 500

@finance_bp.route('/bills/<int:bill_id>/items', methods=['GET'])
def get_bill_items(bill_id):
    user = _require_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    bill = tenant_filter(Bill.query).filter_by(id=bill_id).first_or_404()
    # Basic floor check for non-admins
    if user.role != 'admin' and bill.floor != user.floor:
        abort(403)

    items = []
    for item in bill.items:
        items.append({
            'id': item.id,
            'item_name': item.item_name,
            'quantity': item.quantity,
            'actual_cost': float(item.actual_cost or 0)
        })
    
    return jsonify({
        'bill_no': bill.bill_no,
        'bill_date': bill.bill_date.strftime('%Y-%m-%d'),
        'items': items
    })
