from flask import render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from models import User
from . import auth_bp
from ..utils import (
    _ensure_username_from_full_name, 
    _require_user, 
    _get_current_user,
    _get_active_floor,
    FLOOR_MIN,
    FLOOR_MAX
)

@auth_bp.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('pantry.dashboard'))
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = 'member'
        email = request.form.get('email', '').strip()
        
        # Auto-append domain if only TR number is provided
        if email and '@' not in email:
            email = f"{email}@jameasaifiyah.edu"
            
        password = request.form.get('password', '').strip()
        
        user = User.query.filter_by(email=email, role=role).first()
            
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            if _ensure_username_from_full_name(user, db.session):
                db.session.commit()
            if user.is_first_login:
                session['temp_user_id'] = user.id
                return redirect(url_for('auth.change_password'))
            
            session['user_id'] = user.id
            session['role'] = user.role
            session['floor'] = user.floor
            session.permanent = True
            return redirect(url_for('pantry.dashboard'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('login.html')

@auth_bp.route('/staff-login', methods=['GET', 'POST'])
def staff_login():
    if request.method == 'POST':
        role = (request.form.get('role') or '').strip()
        email = request.form.get('email', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if role not in {'admin', 'pantryHead', 'teaManager'}:
            flash('Invalid role selected', 'error')
            return render_template('staff_login.html')

        if role == 'admin' and not username:
            flash('Admin login requires a username (not email).', 'error')
            return render_template('staff_login.html')
        if role != 'admin' and not email:
            flash('Please enter your TR Number.', 'error')
            return render_template('staff_login.html')

        # Auto-append domain for staff if only TR number is provided
        if email and '@' not in email:
            email = f"{email}@jameasaifiyah.edu"

        user = None
        if role == 'admin':
            user = User.query.filter_by(username=username, role='admin').first()
        else:
            user = User.query.filter_by(email=email, role=role).first()

        if not user or not user.password_hash:
            flash('Invalid credentials', 'error')
            if role == 'admin' and user and not user.password_hash:
                flash('Admin password is not set. Reset it and try again.', 'error')
            return render_template('staff_login.html')

        if check_password_hash(user.password_hash, password):
            if _ensure_username_from_full_name(user, db.session):
                db.session.commit()

            if user.role != 'admin' and user.is_first_login:
                session['temp_user_id'] = user.id
                return redirect(url_for('auth.change_password'))

            session['user_id'] = user.id
            session['role'] = user.role
            session['floor'] = user.floor
            session.permanent = True
            if user.role == 'admin':
                session['active_floor'] = user.floor
            return redirect(url_for('pantry.dashboard'))

        flash('Invalid credentials', 'error')

    return render_template('staff_login.html')

@auth_bp.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'temp_user_id' not in session:
        return redirect(url_for('auth.login'))
        
    user = User.query.get(session['temp_user_id'])
    if not user:
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('change_password.html')
            
        user.password_hash = generate_password_hash(new_password)
        user.is_first_login = False
        db.session.commit()
        
        session.pop('temp_user_id', None)
        session['user_id'] = user.id
        session['role'] = user.role
        session['floor'] = user.floor
        if user.role == 'admin':
            session['active_floor'] = user.floor
        
        flash('Password updated successfully', 'success')
        return redirect(url_for('pantry.dashboard'))
        
    return render_template('change_password.html')

@auth_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    user = _require_user()
    if not user:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        user.full_name = request.form.get('full_name')
        user.phone_number = request.form.get('phone_number')

        _ensure_username_from_full_name(user, db.session)
        
        new_password = request.form.get('new_password')
        if new_password:
            user.password_hash = generate_password_hash(new_password)
            
        db.session.commit()
        flash('Profile updated successfully', 'success')
        
    return render_template('profile.html', user=user, current_user=user)

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('auth.login'))
