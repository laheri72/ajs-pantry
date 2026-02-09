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
        
        if role == 'admin':
            # Admin login with username
            user = User.query.filter_by(username=username, role='admin').first()
            if user and check_password_hash(user.password_hash, password):
                session['user_id'] = user.id
                session['role'] = user.role
                session['floor'] = user.floor
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid admin credentials', 'error')
        else:
            # Other roles login with email
            user = User.query.filter_by(email=email, role=role).first()
            if user:
                if not user.is_verified:
                    flash('Please verify your email first', 'error')
                elif user.username and check_password_hash(user.password_hash, password):
                    session['user_id'] = user.id
                    session['role'] = user.role
                    session['floor'] = user.floor
                    return redirect(url_for('dashboard'))
                else:
                    flash('Invalid credentials', 'error')
            else:
                flash('User not found', 'error')
    
    return render_template('login.html')

@app.route('/verify-email', methods=['POST'])
def verify_email():
    email = request.form.get('email', '').strip()
    role = request.form.get('role')
    
    user = User.query.filter_by(email=email, role=role).first()
    if user:
        # In a real application, you would send an email verification
        # For this demo, we'll just mark as verified and redirect
        user.is_verified = True
        db.session.commit()
        session['temp_user_id'] = user.id
        return redirect(url_for('create_account'))
    else:
        flash('Email not found for this role', 'error')
        return redirect(url_for('login'))

@app.route('/create-account', methods=['GET', 'POST'])
def create_account():
    if 'temp_user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['temp_user_id'])
    if not user:
        session.pop('temp_user_id', None)
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('create_account.html')
        
        # Check if username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists', 'error')
            return render_template('create_account.html')
        
        user.username = username
        user.password_hash = generate_password_hash(password)
        db.session.commit()
        
        session.pop('temp_user_id', None)
        session['user_id'] = user.id
        session['role'] = user.role
        session['floor'] = user.floor
        
        flash('Account created successfully', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('create_account.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    # Get quick stats for home page
    stats = {
        'user_count': User.query.filter_by(floor=user.floor).count(),
        'pending_requests': Request.query.filter_by(floor=user.floor, status='pending').count(),
        'weekly_expenses': sum([e.amount for e in Expense.query.filter_by(floor=user.floor).all()])
    }
    
    return render_template('dashboard.html', user=user, stats=stats)

@app.route('/home')
def home():
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
    
    return render_template('home.html', user=user, stats=stats)

@app.route('/people')
def people():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
        
    users = User.query.filter_by(floor=user.floor).all()
    
    return render_template('people.html', user=user, users=users)

@app.route('/calendar')
def calendar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
        
    menus = Menu.query.filter_by(floor=user.floor).all()
    tea_tasks = TeaTask.query.filter_by(floor=user.floor).all()
    
    return render_template('calendar.html', user=user, menus=menus, tea_tasks=tea_tasks)

@app.route('/menus', methods=['GET', 'POST'])
def menus():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if request.method == 'POST' and user.role in ['admin', 'pantryHead']:
        title = request.form.get('title')
        description = request.form.get('description')
        date_str = request.form.get('date')
        meal_type = request.form.get('meal_type')
        dish_type = request.form.get('dish_type', 'main')
        assigned_to_id = request.form.get('assigned_to_id')
        
        if date_str:
            menu_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            menu = Menu()
            menu.title=title
            menu.description=description
            menu.date=menu_date
            menu.meal_type=meal_type
            menu.dish_type=dish_type
            menu.assigned_to_id=assigned_to_id
            menu.created_by_id=user.id
            menu.floor=user.floor
            
            db.session.add(menu)
            db.session.commit()
            flash('Menu added successfully', 'success')
    
    menus = Menu.query.filter_by(floor=user.floor).order_by(Menu.date.desc()).all()
    floor_users = User.query.filter_by(floor=user.floor).all()
    
    return render_template('menus.html', user=user, menus=menus, floor_users=floor_users)

@app.route('/tea', methods=['GET', 'POST'])
def tea():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if request.method == 'POST' and user.role in ['admin', 'teaManager']:
        title = request.form.get('title')
        description = request.form.get('description')
        date_str = request.form.get('date')
        time = request.form.get('time')
        assigned_to_id = request.form.get('assigned_to_id')
        
        if date_str:
            task_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            tea_task = TeaTask()
            tea_task.title=title
            tea_task.description=description
            tea_task.date=task_date
            tea_task.time=time
            tea_task.assigned_to_id=assigned_to_id
            tea_task.created_by_id=user.id
            tea_task.floor=user.floor
            
            db.session.add(tea_task)
            db.session.commit()
            flash('Tea task added successfully', 'success')
    
    tea_tasks = TeaTask.query.filter_by(floor=user.floor).order_by(TeaTask.date.desc()).all()
    floor_users = User.query.filter_by(floor=user.floor).all()
    
    return render_template('tea.html', user=user, tea_tasks=tea_tasks, floor_users=floor_users)

@app.route('/expenses', methods=['GET', 'POST'])
def expenses():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if request.method == 'POST' and user.role in ['admin', 'pantryHead']:
        description = request.form.get('description')
        amount_str = request.form.get('amount')
        category = request.form.get('category')
        date_str = request.form.get('date')
        
        if amount_str and date_str:
            amount = float(amount_str)
            expense_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            expense = Expense()
            expense.description=description
            expense.amount=amount
            expense.category=category
            expense.date=expense_date
            expense.user_id=user.id
            expense.floor=user.floor
            
            db.session.add(expense)
            db.session.commit()
            flash('Expense added successfully', 'success')
    
    # Filter expenses based on query parameters
    filter_category = request.args.get('category', '')
    filter_date_str = request.args.get('date', '')
    
    query = Expense.query.filter_by(floor=user.floor)
    
    if filter_category:
        query = query.filter(Expense.category == filter_category)
    if filter_date_str:
        filter_date = datetime.strptime(filter_date_str, '%Y-%m-%d').date()
        query = query.filter(Expense.date == filter_date)
    
    expenses = query.order_by(Expense.date.desc()).all()
    total_amount = sum([e.amount for e in expenses])
    categories = db.session.query(Expense.category).filter_by(floor=user.floor).distinct().all()
    
    return render_template('expenses.html', user=user, expenses=expenses, 
                         total_amount=total_amount, categories=categories,
                         filter_category=filter_category, filter_date=filter_date_str)

@app.route('/suggestions', methods=['GET', 'POST'])
def suggestions():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        
        suggestion = Suggestion()
        suggestion.title=title
        suggestion.description=description
        suggestion.user_id=user.id
        suggestion.floor=user.floor
        
        db.session.add(suggestion)
        db.session.commit()
        flash('Suggestion submitted successfully', 'success')
    
    suggestions = Suggestion.query.filter_by(floor=user.floor).order_by(Suggestion.created_at.desc()).all()
    
    return render_template('suggestions.html', user=user, suggestions=suggestions)

@app.route('/feedbacks', methods=['GET', 'POST'])
def feedbacks():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        rating_str = request.form.get('rating', '0')
        rating = int(rating_str) if rating_str else 0
        
        feedback = Feedback()
        feedback.title=title
        feedback.description=description
        feedback.rating=rating
        feedback.user_id=user.id
        feedback.floor=user.floor
        feedback.is_approved=(user.role == 'admin')
        
        db.session.add(feedback)
        db.session.commit()
        flash('Feedback submitted successfully', 'success')
    
    if user.role == 'admin':
        feedbacks = Feedback.query.filter_by(floor=user.floor).order_by(Feedback.created_at.desc()).all()
    else:
        feedbacks = Feedback.query.filter_by(floor=user.floor, is_approved=True).order_by(Feedback.created_at.desc()).all()
    
    return render_template('feedbacks.html', user=user, feedbacks=feedbacks)

@app.route('/requests', methods=['GET', 'POST'])
def requests():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        if request.form.get('action') == 'approve' and user.role == 'admin':
            request_id = request.form.get('request_id')
            req = Request.query.get(request_id)
            if req:
                req.status = 'approved'
                req.approved_by_id = user.id
                db.session.commit()
                flash('Request approved', 'success')
        else:
            title = request.form.get('title')
            description = request.form.get('description')
            request_type = request.form.get('request_type')
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')
            
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
            
            req = Request()
            req.title=title
            req.description=description
            req.request_type=request_type
            req.start_date=start_date
            req.end_date=end_date
            req.user_id=user.id
            req.floor=user.floor
            
            db.session.add(req)
            db.session.commit()
            flash('Request submitted successfully', 'success')
    
    requests = Request.query.filter_by(floor=user.floor).order_by(Request.created_at.desc()).all()
    
    return render_template('requests.html', user=user, requests=requests)

@app.route('/procurement', methods=['GET', 'POST'])
def procurement():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if request.method == 'POST' and user.role in ['admin', 'pantryHead']:
        item_name = request.form.get('item_name')
        quantity = request.form.get('quantity')
        category = request.form.get('category')
        priority = request.form.get('priority')
        assigned_to_id = request.form.get('assigned_to_id')
        
        procurement_item = ProcurementItem()
        procurement_item.item_name=item_name
        procurement_item.quantity=quantity
        procurement_item.category=category
        procurement_item.priority=priority
        procurement_item.assigned_to_id=assigned_to_id
        procurement_item.created_by_id=user.id
        procurement_item.floor=user.floor
        
        db.session.add(procurement_item)
        db.session.commit()
        flash('Procurement item added successfully', 'success')
    
    procurement_items = ProcurementItem.query.filter_by(floor=user.floor).order_by(ProcurementItem.created_at.desc()).all()
    floor_users = User.query.filter_by(floor=user.floor).all()
    
    return render_template('procurement.html', user=user, procurement_items=procurement_items, floor_users=floor_users)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        
        if current_password and new_password:
            if check_password_hash(user.password_hash, current_password):
                user.password_hash = generate_password_hash(new_password)
                flash('Password updated successfully', 'success')
            else:
                flash('Current password is incorrect', 'error')
                return render_template('profile.html', user=user)
        
        user.username = username
        user.email = email
        db.session.commit()
        flash('Profile updated successfully', 'success')
    
    return render_template('profile.html', user=user)

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
            email = request.form.get('email')
            role = request.form.get('role')
            floor_str = request.form.get('floor')
            floor = int(floor_str) if floor_str else user.floor
            
            # Check if user already exists
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash('User with this email already exists', 'error')
            else:
                new_user = User()
                new_user.email=email
                new_user.role=role
                new_user.floor=floor
                new_user.password_hash=generate_password_hash('maskanmarol')
                new_user.is_verified=False
                
                db.session.add(new_user)
                db.session.commit()
                flash(f'{role.title() if role else "User"} added successfully', 'success')
        
        elif action == 'update_floor':
            user_id = request.form.get('user_id')
            new_floor_str = request.form.get('floor')
            if user_id and new_floor_str:
                new_floor = int(new_floor_str)
                target_user = User.query.get(user_id)
                if target_user:
                    target_user.floor = new_floor
                    db.session.commit()
                    flash('User floor updated successfully', 'success')
    
    all_users = User.query.all()
    
    return render_template('admin.html', user=user, all_users=all_users)

@app.route('/add-user', methods=['POST'])
def add_user():
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    email = request.form.get('email')
    role = request.form.get('role')
    floor_str = request.form.get('floor')
    floor = int(floor_str) if floor_str else session.get('floor', 1)
    
    # Check if user already exists
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({'error': 'User with this email already exists'}), 400
    
    new_user = User()
    new_user.email=email
    new_user.role=role
    new_user.floor=floor
    new_user.password_hash=generate_password_hash('maskanmarol')
    new_user.is_verified=False
    
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'{role.title() if role else "User"} added successfully'})

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user_admin(user_id):
    if 'user_id' not in session:
        flash('Please log in first', 'error')
        return redirect(url_for('login'))
    
    current_user = User.query.get(session['user_id'])
    if not current_user or current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    if current_user.id == user_id:
        flash('You cannot delete yourself', 'error')
        return redirect(url_for('admin'))
    
    user_to_delete = User.query.get_or_404(user_id)
    db.session.delete(user_to_delete)
    db.session.commit()
    flash('User deleted successfully', 'success')
    
    return redirect(url_for('admin'))

@app.route('/procurement/complete/<int:item_id>', methods=['POST'])
def complete_procurement(item_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = User.query.get(session['user_id'])
    if not user or user.role not in ['admin', 'pantryHead']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    item = ProcurementItem.query.get_or_404(item_id)
    item.status = 'completed'
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/tea/complete/<int:task_id>', methods=['POST'])
def complete_tea_task(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = User.query.get(session['user_id'])
    if not user or user.role not in ['admin', 'teaManager']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    task = TeaTask.query.get_or_404(task_id)
    task.status = 'completed'
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/expenses/delete/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    if 'user_id' not in session:
        flash('Please log in first', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user or user.role not in ['admin', 'pantryHead']:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    expense = Expense.query.get_or_404(expense_id)
    db.session.delete(expense)
    db.session.commit()
    flash('Expense deleted successfully', 'success')
    
    return redirect(url_for('expenses'))

@app.route('/menus/delete/<int:menu_id>', methods=['POST'])
def delete_menu(menu_id):
    if 'user_id' not in session:
        flash('Please log in first', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user or user.role not in ['admin', 'pantryHead']:
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    menu = Menu.query.get_or_404(menu_id)
    db.session.delete(menu)
    db.session.commit()
    flash('Menu deleted successfully', 'success')
    
    return redirect(url_for('menus'))

@app.context_processor
def inject_user():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        return dict(current_user=user)
    return dict(current_user=None)
