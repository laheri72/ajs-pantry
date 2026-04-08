from app import db
from datetime import datetime
from enum import Enum
import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import event
from sqlalchemy.orm import with_loader_criteria
from flask import g

class RoleEnum(Enum):
    SUPER_ADMIN = 'super_admin'
    ADMIN = 'admin'
    FACULTY = 'faculty'
    PANTRY_HEAD = 'pantryHead'
    TEA_MANAGER = 'teaManager'
    MEMBER = 'member'

class Tenant(db.Model):
    __tablename__ = 'tenants'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    floor_count = db.Column(db.Integer, default=11)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subscription_status = db.Column(db.String(50), default='active')

class PlatformAudit(db.Model):
    __tablename__ = 'platform_audits'
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(100), nullable=False) # e.g., 'provision_tenant', 'suspend_tenant'
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    performed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    
    performed_by = db.relationship('User', foreign_keys=[performed_by_id])

class TenantMixin:
    tenant_id = db.Column(UUID(as_uuid=True), db.ForeignKey('tenants.id'), nullable=True, index=True)

class User(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), nullable=False)
    floor = db.Column(db.Integer, nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    is_first_login = db.Column(db.Boolean, default=True)
    tr_number = db.Column(db.String(20), unique=True, nullable=True)
    full_name = db.Column(db.String(100), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    profile_pic = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Dish(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(20), default='main')  # main, side, both
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])

class Menu(db.Model, TenantMixin):
    __table_args__ = (
        db.Index('idx_menu_rotation', 'floor', 'date', 'is_buffer', 'assigned_team_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast, lunch, dinner
    dish_type = db.Column(db.String(20), nullable=False, default='main')  # main, side
    dish_id = db.Column(db.Integer, db.ForeignKey('dish.id'), index=True)
    side_dish_id = db.Column(db.Integer, db.ForeignKey('dish.id'))
    is_buffer = db.Column(db.Boolean, default=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    assigned_team_id = db.Column(db.Integer, db.ForeignKey('team.id'), index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    floor = db.Column(db.Integer, nullable=False)
    skip_notifications = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    dish = db.relationship('Dish', foreign_keys=[dish_id])
    side_dish = db.relationship('Dish', foreign_keys=[side_dish_id])
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id])
    assigned_team = db.relationship('Team', foreign_keys=[assigned_team_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])

class Expense(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    budget_id = db.Column(db.Integer, db.ForeignKey('budget.id'), index=True)
    report_submission_id = db.Column(db.Integer, db.ForeignKey('faculty_report_submission.id'), nullable=True, index=True)
    floor = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='expenses')
    budget = db.relationship('Budget', foreign_keys=[budget_id])

class TeaTask(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    floor = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])

class Suggestion(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    dish_id = db.Column(db.Integer, db.ForeignKey('dish.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    floor = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    dish = db.relationship('Dish', foreign_keys=[dish_id])
    user = db.relationship('User', backref='suggestions')

class SuggestionVote(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    suggestion_id = db.Column(db.Integer, db.ForeignKey('suggestion.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    suggestion = db.relationship('Suggestion', backref=db.backref('votes', cascade='all, delete-orphan'))
    user = db.relationship('User')

class Feedback(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer)  # 1-5 rating
    menu_id = db.Column(db.Integer, db.ForeignKey('menu.id'), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    floor = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    menu = db.relationship('Menu', foreign_keys=[menu_id])
    user = db.relationship('User', backref='feedbacks')

class Request(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    request_type = db.Column(db.String(50), nullable=False)  # absence, maintenance, etc.
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    floor = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')
    approved_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])

class Bill(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    bill_no = db.Column(db.String(100), nullable=False)
    bill_date = db.Column(db.Date, nullable=False)
    shop_name = db.Column(db.String(100), nullable=True)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    floor = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(50), default='manual')
    original_filename = db.Column(db.String(255), nullable=True)
    report_submission_id = db.Column(db.Integer, db.ForeignKey('faculty_report_submission.id'), nullable=True, index=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to items
    items = db.relationship('ProcurementItem', backref='bill', lazy=True)

class ProcurementItem(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    priority = db.Column(db.String(20), default='medium')
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    floor = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # New financial fields
    actual_cost = db.Column(db.Numeric(12, 2), nullable=True)
    expense_recorded_at = db.Column(db.DateTime, nullable=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=True, index=True)
    
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])


class Team(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), nullable=True)  # emoji or short label
    floor = db.Column(db.Integer, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])


class TeamMember(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    team = db.relationship('Team', foreign_keys=[team_id])
    user = db.relationship('User', foreign_keys=[user_id])


class Budget(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    floor = db.Column(db.Integer, nullable=False, index=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey('faculty_budget_cycle.id'), nullable=True, index=True)
    allocated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    amount_allocated = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    allocation_type = db.Column(db.String(20), nullable=False)  # weekly, monthly, 15days, manual
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    faculty_note = db.Column(db.Text, nullable=True)
    is_faculty_allocation = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    allocated_by = db.relationship('User', foreign_keys=[allocated_by_id])


class FacultyBudgetCycle(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    start_date = db.Column(db.Date, nullable=False, index=True)
    end_date = db.Column(db.Date, nullable=False, index=True)
    submission_deadline = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='draft', index=True)
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    activated_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])
    budgets = db.relationship('Budget', backref='cycle', lazy=True)
    submissions = db.relationship('FacultyReportSubmission', backref='cycle', lazy=True)


class FacultyReportSubmission(db.Model, TenantMixin):
    __table_args__ = (
        db.UniqueConstraint('cycle_id', 'floor', name='uq_cycle_floor_submission'),
    )
    id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey('faculty_budget_cycle.id'), nullable=False, index=True)
    print_report_id = db.Column(db.Integer, db.ForeignKey('expense_print_report.id'), nullable=True, index=True)
    floor = db.Column(db.Integer, nullable=False, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    report_title = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='submitted', index=True)
    allocated_amount = db.Column(db.Numeric(12, 2), nullable=True)
    submission_notes = db.Column(db.Text, nullable=True)
    review_notes = db.Column(db.Text, nullable=True)
    stored_filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.Text, nullable=False)
    file_size_bytes = db.Column(db.BigInteger, nullable=False, default=0)
    revision_no = db.Column(db.Integer, nullable=False, default=1)
    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime, nullable=True)
    verified_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])
    verified_by = db.relationship('User', foreign_keys=[verified_by_id])
    print_report = db.relationship('ExpensePrintReport', foreign_keys=[print_report_id])
    bills = db.relationship('Bill', backref='report_submission', lazy=True)
    expenses = db.relationship('Expense', backref='report_submission', lazy=True)


class ExpensePrintReport(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey('faculty_budget_cycle.id'), nullable=True, index=True)
    floor = db.Column(db.Integer, nullable=False, index=True)
    report_title = db.Column(db.String(150), nullable=False)
    report_budget = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_spent = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    remaining_balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])
    cycle = db.relationship('FacultyBudgetCycle', foreign_keys=[cycle_id])
    bill_links = db.relationship(
        'ExpensePrintReportBill',
        backref=db.backref('print_report', lazy=True),
        cascade='all, delete-orphan',
        lazy=True,
    )


class ExpensePrintReportBill(db.Model, TenantMixin):
    __table_args__ = (
        db.UniqueConstraint('print_report_id', 'bill_id', name='uq_expense_print_report_bill'),
    )
    id = db.Column(db.Integer, primary_key=True)
    print_report_id = db.Column(db.Integer, db.ForeignKey('expense_print_report.id'), nullable=False, index=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False, index=True)
    include_in_summary = db.Column(db.Boolean, nullable=False, default=False)
    include_as_voucher = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bill = db.relationship('Bill', foreign_keys=[bill_id])


class FloorLendBorrow(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    lender_floor = db.Column(db.Integer, nullable=False, index=True)
    borrower_floor = db.Column(db.Integer, nullable=False, index=True)
    item_name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.String(50), nullable=False)
    item_type = db.Column(db.String(20), nullable=False, default='grocery')
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    borrower_marked_at = db.Column(db.DateTime)
    lender_verified_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])


class SpecialEvent(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False)
    floor = db.Column(db.Integer, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])


class Announcement(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    floor = db.Column(db.Integer, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_archived = db.Column(db.Boolean, default=False)

    created_by = db.relationship('User', foreign_keys=[created_by_id])


class FacultyMessage(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    target_scope = db.Column(db.String(30), nullable=False, default='all_pantry_heads', index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)

    created_by = db.relationship('User', foreign_keys=[created_by_id])
    target_floors = db.relationship(
        'FacultyMessageFloor',
        backref=db.backref('faculty_message', lazy=True),
        cascade='all, delete-orphan',
        lazy=True,
    )


class FacultyMessageFloor(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    faculty_message_id = db.Column(db.Integer, db.ForeignKey('faculty_message.id'), nullable=False, index=True)
    floor = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Garamat(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    floor = db.Column(db.Integer, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    team = db.relationship('Team', foreign_keys=[team_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])


class PushSubscription(db.Model, TenantMixin):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False)
    p256dh = db.Column(db.String(255), nullable=False)
    auth = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('push_subscriptions', cascade='all, delete-orphan'))


@event.listens_for(db.session, "do_orm_execute")
def _add_tenant_filter(execute_state):
    """
    Automatically adds a tenant_id filter to all ORM queries if a tenant_id
    is present in Flask's global 'g' object.
    """
    if (
        execute_state.is_select
        and not execute_state.is_column_load
        and not execute_state.is_relationship_load
        and hasattr(g, 'tenant_id')
        and g.tenant_id is not None
        and not getattr(g, 'is_super_admin', False)
    ):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                TenantMixin,
                lambda cls: cls.tenant_id == g.tenant_id,
                include_aliases=True
            )
        )
