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

class Menu(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast, lunch, dinner
    dish_type = db.Column(db.String(20), nullable=False, default='main')  # main, side
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    assigned_team_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    floor = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
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

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer)  # 1-5 rating
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    floor = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
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
