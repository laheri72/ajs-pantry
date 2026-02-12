from flask import render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, db
from models import User, Menu, Expense, TeaTask, Suggestion, Feedback, Request, ProcurementItem
from datetime import datetime, date
import logging

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role')
        email = request.form.get('email', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        user = None
        if role == 'admin':
            user = User.query.filter_by(username=username, role='admin').first()
        else:
            user = User.query.filter_by(email=email, role=role).first()
            
        if user and check_password_hash(user.password_hash, password):
            if user.is_first_login:
                session['temp_user_id'] = user.id
                return redirect(url_for('change_password'))
            
            session['user_id'] = user.id
            session['role'] = user.role
            session['floor'] = user.floor
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('login.html')

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'temp_user_id' not in session:
        return redirect(url_for('login'))
        
    user = User.query.get(session['temp_user_id'])
    if not user:
        return redirect(url_for('login'))
        
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
        
        flash('Password updated successfully', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('change_password.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    stats = {
        'user_count': User.query.filter_by(floor=user.floor).count(),
        'pending_requests': Request.query.filter_by(floor=user.floor, status='pending').count(),
        'weekly_expenses': sum([e.amount for e in Expense.query.filter_by(floor=user.floor).all()])
    }
    
    return render_template('dashboard.html', user=user, stats=stats)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_user':
            role = request.form.get('role')
            floor = int(request.form.get('floor', user.floor))
            
            new_user = User()
            new_user.role = role
            new_user.floor = floor
            new_user.password_hash = generate_password_hash('maskan1447')
            new_user.is_first_login = True
            
            if role == 'member':
                tr_number = request.form.get('tr_number')
                new_user.tr_number = tr_number
                new_user.email = f"{tr_number}@jameasaifiyah.edu"
            else:
                new_user.email = request.form.get('email')
                
            db.session.add(new_user)
            db.session.commit()
            flash(f'User added successfully', 'success')
            
    all_users = User.query.all()
    return render_template('admin.html', user=user, all_users=all_users)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        user.full_name = request.form.get('full_name')
        user.phone_number = request.form.get('phone_number')
        
        new_password = request.form.get('new_password')
        if new_password:
            user.password_hash = generate_password_hash(new_password)
            
        db.session.commit()
        flash('Profile updated successfully', 'success')
        
    return render_template('profile.html', user=user)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

# Remaining routes for menus, tea, expenses, etc. (kept for functionality)
@app.route('/menus', methods=['GET', 'POST'])
def menus():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST' and user.role in ['admin', 'pantryHead']:
        menu = Menu(title=request.form.get('title'), description=request.form.get('description'), 
                    date=datetime.strptime(request.form.get('date'), '%Y-%m-%d').date(),
                    meal_type=request.form.get('meal_type'), floor=user.floor, created_by_id=user.id)
        db.session.add(menu); db.session.commit()
    return render_template('menus.html', user=user, menus=Menu.query.filter_by(floor=user.floor).all())

@app.route('/tea', methods=['GET', 'POST'])
def tea():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST' and user.role in ['admin', 'teaManager']:
        task = TeaTask(title=request.form.get('title'), description=request.form.get('description'),
                       date=datetime.strptime(request.form.get('date'), '%Y-%m-%d').date(),
                       time=request.form.get('time'), floor=user.floor, created_by_id=user.id)
        db.session.add(task); db.session.commit()
    return render_template('tea.html', user=user, tea_tasks=TeaTask.query.filter_by(floor=user.floor).all())

@app.route('/expenses', methods=['GET', 'POST'])
def expenses():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST' and user.role in ['admin', 'pantryHead']:
        exp = Expense(description=request.form.get('description'), amount=float(request.form.get('amount')),
                      category=request.form.get('category'), date=datetime.strptime(request.form.get('date'), '%Y-%m-%d').date(),
                      user_id=user.id, floor=user.floor)
        db.session.add(exp); db.session.commit()
    return render_template('expenses.html', user=user, expenses=Expense.query.filter_by(floor=user.floor).all())
