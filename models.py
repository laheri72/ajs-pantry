from app import db
from datetime import datetime
from enum import Enum

class RoleEnum(Enum):
    ADMIN = 'admin'
    PANTRY_HEAD = 'pantryHead'
    TEA_MANAGER = 'teaManager'
    MEMBER = 'member'

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=True)
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

class Dish(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])

class Menu(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast, lunch, dinner
    dish_type = db.Column(db.String(20), nullable=False, default='main')  # main, side
    dish_id = db.Column(db.Integer, db.ForeignKey('dish.id'))
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    assigned_team_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    floor = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    dish = db.relationship('Dish', foreign_keys=[dish_id])
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id])
    assigned_team = db.relationship('Team', foreign_keys=[assigned_team_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    floor = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='expenses')

class TeaTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    floor = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])

class Suggestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    floor = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='suggestions')

class SuggestionVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    suggestion_id = db.Column(db.Integer, db.ForeignKey('suggestion.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    suggestion = db.relationship('Suggestion', backref=db.backref('votes', cascade='all, delete-orphan'))
    user = db.relationship('User')

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer)  # 1-5 rating
    menu_id = db.Column(db.Integer, db.ForeignKey('menu.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    floor = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    menu = db.relationship('Menu', foreign_keys=[menu_id])
    user = db.relationship('User', backref='feedbacks')

class Request(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    request_type = db.Column(db.String(50), nullable=False)  # absence, maintenance, etc.
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    floor = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')
    approved_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_no = db.Column(db.String(100), nullable=False)
    bill_date = db.Column(db.Date, nullable=False)
    shop_name = db.Column(db.String(100), nullable=True)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    floor = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(50), default='manual')
    original_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to items
    items = db.relationship('ProcurementItem', backref='bill', lazy=True)

class ProcurementItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    priority = db.Column(db.String(20), default='medium')
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    floor = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # New financial fields
    actual_cost = db.Column(db.Numeric(12, 2), nullable=True)
    expense_recorded_at = db.Column(db.DateTime, nullable=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=True)
    
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])


class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), nullable=True)  # emoji or short label
    floor = db.Column(db.Integer, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])


class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    team = db.relationship('Team', foreign_keys=[team_id])
    user = db.relationship('User', foreign_keys=[user_id])


class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    floor = db.Column(db.Integer, nullable=False, index=True)
    amount_allocated = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    allocation_type = db.Column(db.String(20), nullable=False)  # weekly, monthly, 15days, manual
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class FloorLendBorrow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lender_floor = db.Column(db.Integer, nullable=False, index=True)
    borrower_floor = db.Column(db.Integer, nullable=False, index=True)
    item_name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.String(50), nullable=False)
    item_type = db.Column(db.String(20), nullable=False, default='grocery')
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    borrower_marked_at = db.Column(db.DateTime)
    lender_verified_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])


class SpecialEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False)
    floor = db.Column(db.Integer, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])


class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    floor = db.Column(db.Integer, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_archived = db.Column(db.Boolean, default=False)

    created_by = db.relationship('User', foreign_keys=[created_by_id])


class Garamat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    floor = db.Column(db.Integer, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    team = db.relationship('Team', foreign_keys=[team_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])
