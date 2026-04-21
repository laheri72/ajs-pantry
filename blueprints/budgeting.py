from datetime import date, timedelta

from flask import g
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app import db
from models import Bill, Budget, Expense, FacultyBudgetCycle
from .utils import visible_budget_condition


def _coerce_float(value):
    return float(value or 0)


def _tenant_scoped_query(query, tenant_id=None):
    tenant_id = tenant_id if tenant_id is not None else getattr(g, 'tenant_id', None)
    if tenant_id is not None:
        return query.filter_by(tenant_id=tenant_id)
    return query


def _sum_period_bills(floor, start_date, end_date=None, tenant_id=None):
    query = _tenant_scoped_query(db.session.query(func.sum(Bill.total_amount)), tenant_id).filter(
        Bill.floor == floor,
        Bill.bill_date >= start_date,
    )
    if end_date is not None:
        query = query.filter(Bill.bill_date <= end_date)
    return _coerce_float(query.scalar())


def _sum_period_legacy_expenses(floor, start_date, end_date=None, tenant_id=None):
    query = _tenant_scoped_query(db.session.query(func.sum(Expense.amount)), tenant_id).filter(
        Expense.floor == floor,
        Expense.date >= start_date,
    )
    if end_date is not None:
        query = query.filter(Expense.date <= end_date)
    return _coerce_float(query.scalar())


def _make_period_from_budget(budget):
    cycle = budget.cycle
    source_type = 'faculty_cycle' if cycle else 'manual'
    end_date = cycle.end_date if cycle else budget.end_date
    return {
        'source_type': source_type,
        'source_id': cycle.id if cycle else budget.id,
        'budget_id': budget.id,
        'cycle_id': cycle.id if cycle else None,
        'title': cycle.title if cycle else f"{(budget.allocation_type or 'manual').title()} Budget",
        'start_date': budget.start_date,
        'end_date': end_date,
        'created_at': cycle.created_at if cycle else budget.created_at,
        'allocated_amount': _coerce_float(budget.amount_allocated),
        'faculty_note': budget.faculty_note,
        'notes': budget.notes,
        'status': cycle.status if cycle else 'manual',
        'is_synthetic': False,
    }


def _make_synthetic_active_cycle_period(active_cycle):
    return {
        'source_type': 'faculty_cycle',
        'source_id': active_cycle.id,
        'budget_id': None,
        'cycle_id': active_cycle.id,
        'title': active_cycle.title,
        'start_date': active_cycle.start_date,
        'end_date': active_cycle.end_date,
        'created_at': active_cycle.created_at,
        'allocated_amount': 0.0,
        'faculty_note': None,
        'notes': active_cycle.notes,
        'status': active_cycle.status,
        'is_synthetic': True,
    }


def build_floor_budget_ledger(floor, tenant_id=None, faculty_workflow_enabled=True):
    budgets = (
        _tenant_scoped_query(Budget.query.options(joinedload(Budget.cycle)), tenant_id)
        .filter(Budget.floor == floor, visible_budget_condition(True))
        .order_by(Budget.start_date.asc(), Budget.created_at.asc(), Budget.id.asc())
        .all()
    )
    periods = [_make_period_from_budget(budget) for budget in budgets]

    active_cycle = None
    active_cycle_allocation = None
    if faculty_workflow_enabled:
        active_cycle = (
            _tenant_scoped_query(FacultyBudgetCycle.query, tenant_id)
            .filter_by(status='active')
            .order_by(FacultyBudgetCycle.start_date.desc(), FacultyBudgetCycle.created_at.desc())
            .first()
        )
        if active_cycle:
            active_cycle_allocation = next(
                (period for period in periods if period['cycle_id'] == active_cycle.id),
                None,
            )
            if not active_cycle_allocation:
                periods.append(_make_synthetic_active_cycle_period(active_cycle))

    periods.sort(key=lambda row: (row['start_date'], row['created_at'], row['source_type'], row['source_id'] or 0))

    running_balance = 0.0
    for idx, period in enumerate(periods):
        next_start = periods[idx + 1]['start_date'] if idx + 1 < len(periods) else None
        effective_end = period['end_date']
        if effective_end is None and next_start and next_start > period['start_date']:
            effective_end = next_start - timedelta(days=1)
        if effective_end and effective_end < period['start_date']:
            effective_end = period['start_date']

        spent_amount = _sum_period_bills(floor, period['start_date'], effective_end, tenant_id=tenant_id)
        spent_amount += _sum_period_legacy_expenses(floor, period['start_date'], effective_end, tenant_id=tenant_id)

        opening_balance = running_balance
        available_budget = opening_balance + period['allocated_amount']
        closing_balance = available_budget - spent_amount

        period['effective_end_date'] = effective_end
        period['opening_balance'] = opening_balance
        period['available_budget'] = available_budget
        period['spent_amount'] = spent_amount
        period['closing_balance'] = closing_balance
        period['is_current'] = False

        running_balance = closing_balance

    current_period = None
    if active_cycle:
        current_period = next((period for period in periods if period['cycle_id'] == active_cycle.id), None)
    elif periods:
        latest_period = periods[-1]
        has_faculty_history = any(period['source_type'] == 'faculty_cycle' for period in periods)
        if not faculty_workflow_enabled:
            current_period = latest_period if latest_period['source_type'] == 'manual' else None
        elif latest_period['source_type'] == 'manual' or not has_faculty_history:
            current_period = latest_period

    if current_period:
        current_period['is_current'] = True

    latest_closing_balance = periods[-1]['closing_balance'] if periods else 0.0
    carryforward_balance = current_period['closing_balance'] if current_period else latest_closing_balance

    return {
        'active_cycle': active_cycle,
        'active_cycle_allocation': active_cycle_allocation,
        'current_period': current_period,
        'periods': list(reversed(periods)),
        'current_allocated_amount': current_period['allocated_amount'] if current_period else 0.0,
        'current_available_budget': current_period['available_budget'] if current_period else carryforward_balance,
        'current_spent_amount': current_period['spent_amount'] if current_period else 0.0,
        'current_remaining_balance': current_period['closing_balance'] if current_period else carryforward_balance,
        'carryforward_balance': carryforward_balance,
        'has_period_history': bool(periods),
        'today': date.today(),
    }
