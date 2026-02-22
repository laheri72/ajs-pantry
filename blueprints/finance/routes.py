from flask import render_template, request, redirect, url_for, flash, jsonify, abort
from app import db
from models import User, Expense, ProcurementItem, Budget, FloorLendBorrow, Bill
from pdf_service import PDFParserService
from datetime import datetime, date
from sqlalchemy import or_, func
import logging
from . import finance_bp
from ..utils import (
    _require_user,
    _get_active_floor,
    _get_floor_options_for_admin
)

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

            item = ProcurementItem.query.get(item_id)
            if item and (user.role == 'admin' or item.floor == user.floor):
                if item.status != 'completed':
                    flash('Costs can only be recorded for completed items.', 'error')
                else:
                    item.actual_cost = cost
                    item.expense_recorded_at = datetime.utcnow()
                    
                    # If item belongs to a bill, update bill total
                    if item.bill_id:
                        bill = Bill.query.get(item.bill_id)
                        if bill:
                            # Recalculate total amount from all items in this bill
                            bill_total = db.session.query(func.sum(ProcurementItem.actual_cost)).filter(ProcurementItem.bill_id == bill.id).scalar() or 0
                            bill.total_amount = bill_total

                    db.session.commit()
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
                    total_amount=0
                )
                db.session.add(bill)
                db.session.flush() # Get bill.id
                
                total_amount = 0
                for i in range(len(item_ids)):
                    item_id = int(item_ids[i])
                    cost = float(costs[i] or 0)
                    
                    item = ProcurementItem.query.get(item_id)
                    if item and (user.role == 'admin' or item.floor == floor):
                        item.actual_cost = cost
                        item.bill_id = bill.id
                        item.expense_recorded_at = datetime.utcnow()
                        total_amount += cost
                
                bill.total_amount = total_amount
                db.session.commit()
                flash(f'Bill {bill_no} recorded successfully with {len(item_ids)} items.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error recording bill: {str(e)}', 'error')
            return redirect(url_for('finance.expenses'))

    # 2. Financial Calculations
    # Total Budget Allocated
    total_budget = db.session.query(func.sum(Budget.amount_allocated)).filter(Budget.floor == floor).scalar() or 0
    
    # Total Spent (Current System: Completed Procurements with Costs)
    total_spent_procurement = db.session.query(func.sum(ProcurementItem.actual_cost)).filter(
        ProcurementItem.floor == floor, 
        ProcurementItem.status == 'completed'
    ).scalar() or 0
    
    # Legacy Expenses (Optional: include in total spent if desired)
    total_spent_legacy = db.session.query(func.sum(Expense.amount)).filter(Expense.floor == floor).scalar() or 0
    
    total_spent = float(total_spent_procurement) + float(total_spent_legacy)
    remaining_balance = float(total_budget) - total_spent

    # 3. Data for Ledger
    # Get completed procurements for this floor that are NOT yet in a bill
    pending_procurements = ProcurementItem.query.filter_by(
        floor=floor, status='completed', bill_id=None
    ).order_by(ProcurementItem.created_at.desc()).all()
    
    # Get all bills for this floor
    bills = Bill.query.filter_by(floor=floor).order_by(Bill.bill_date.desc()).all()
    
    # Get budget history
    budgets = Budget.query.filter_by(floor=floor).order_by(Budget.start_date.desc()).all()
    
    # Legacy expenses for reference
    legacy_expenses = Expense.query.filter_by(floor=floor).order_by(Expense.date.desc()).all()

    # Get unique shop names for suggestions
    unique_shops = db.session.query(Bill.shop_name).filter(
        Bill.floor == floor, Bill.shop_name.isnot(None), Bill.shop_name != ''
    ).distinct().order_by(Bill.shop_name).all()
    unique_shops = [s[0] for s in unique_shops]

    return render_template(
        'expenses.html',
        total_budget=total_budget,
        total_spent=total_spent,
        remaining_balance=remaining_balance,
        pending_procurements=pending_procurements,
        bills=bills,
        budgets=budgets,
        legacy_expenses=legacy_expenses,
        unique_shops=unique_shops,
        is_manager=is_manager,
        today=date.today(),
        current_user=user
    )

@finance_bp.route('/bills/<int:bill_id>/delete', methods=['POST'])
def delete_bill(bill_id):
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)

    bill = Bill.query.get_or_404(bill_id)
    if user.role != 'admin' and bill.floor != user.floor:
        abort(403)

    for item in bill.items:
        item.bill_id = None
    
    db.session.delete(bill)
    db.session.commit()
    flash('Bill deleted and items moved back to pending costs.', 'success')
    return redirect(url_for('finance.expenses'))

@finance_bp.route('/budgets/add', methods=['POST'])
def add_budget():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        abort(403)

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
        allocation_type=request.form.get('allocation_type'),
        start_date=start_date,
        end_date=end_date,
        notes=request.form.get('notes')
    )
    db.session.add(budget)
    db.session.commit()
    flash('Budget allocation added.', 'success')
    return redirect(url_for('finance.expenses'))

@finance_bp.route('/expenses/<int:expense_id>/delete', methods=['POST'])
def delete_expense(expense_id):
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))

    if user.role not in ['admin', 'pantryHead']:
        abort(403)

    expense = Expense.query.get(expense_id)
    if not expense:
        abort(404)
    if user.role == 'pantryHead' and expense.floor != user.floor:
        abort(404)

    db.session.delete(expense)
    db.session.commit()
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
        pending = FloorLendBorrow.query.filter_by(status='pending').order_by(FloorLendBorrow.created_at.desc()).all()
        returned = FloorLendBorrow.query.filter_by(status='returned').order_by(FloorLendBorrow.borrower_marked_at.desc()).all()
        completed = FloorLendBorrow.query.filter_by(status='completed').order_by(FloorLendBorrow.lender_verified_at.desc()).limit(100).all()
    else:
        query = FloorLendBorrow.query.filter(or_(FloorLendBorrow.lender_floor == floor, FloorLendBorrow.borrower_floor == floor))
        
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
        status='pending'
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

    record = FloorLendBorrow.query.get_or_404(record_id)
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

    record = FloorLendBorrow.query.get_or_404(record_id)
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

@finance_bp.route('/expenses/import-pdf', methods=['POST'])
def import_pdf():
    user = _require_user()
    if not user or user.role not in ['admin', 'pantryHead']:
        return jsonify({'error': 'Unauthorized'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        data = PDFParserService.parse_dmart_invoice(file.stream)
        data['filename'] = file.filename
        return jsonify(data)
    except Exception as e:
        logging.error(f"PDF Import Error: {str(e)}")
        return jsonify({'error': f"Failed to parse PDF: {str(e)}"}), 500

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
            bill_no=data.get('bill_no') or f"DM-{int(datetime.utcnow().timestamp())}",
            bill_date=bill_date,
            shop_name=data.get('shop_name') or 'D-Mart',
            total_amount=data.get('total_amount', 0),
            floor=floor,
            source='pdf_import',
            original_filename=data.get('filename')
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
                bill_id=bill.id
            )
            db.session.add(item)

        db.session.commit()
        return jsonify({'success': True, 'bill_id': bill.id})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Save Imported Bill Error: {str(e)}")
        return jsonify({'error': f"Failed to save bill: {str(e)}"}), 500
