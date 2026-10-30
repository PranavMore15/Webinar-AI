"""
Authentication Routes for WebinarAI.
Handles user registration, login, logout, and strict role separation.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models import db, User
from app.utils.auth import validate_registration_data

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Public user registration route.
    Validates form data server-side and strictly provisions 'user' accounts.
    Never trusts client-submitted role fields.
    """
    if session.get('user_id'):
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Server-side format & syntax validation
        is_valid, error_msg = validate_registration_data(username, email, password, confirm_password)
        if not is_valid:
            flash(error_msg, 'danger')
            return render_template('register.html', username=username, email=email)

        # Check for existing username (case-insensitive)
        existing_username = User.query.filter(db.func.lower(User.username) == username.lower()).first()
        if existing_username:
            flash('This username is already registered. Please choose another username or sign in.', 'danger')
            return render_template('register.html', username=username, email=email)

        # Check for existing email (case-insensitive)
        existing_email = User.query.filter(db.func.lower(User.email) == email.lower()).first()
        if existing_email:
            flash('This email address is already registered. Please sign in.', 'danger')
            return render_template('register.html', username=username, email=email)

        try:
            # Provision new standard user account - strictly set role='user' on server
            new_user = User(
                username=username,
                email=email.lower(),
                role='user',
                is_active=True
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()

            # Establish authenticated session
            session['user_id'] = new_user.id
            session['username'] = new_user.username
            session['role'] = new_user.role

            flash(f'Account created successfully! Welcome to WebinarAI, {new_user.username}.', 'success')
            return redirect(url_for('dashboard.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Registration could not be completed: {str(e)}', 'danger')
            return render_template('register.html', username=username, email=email)

    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    User & Administrator sign-in endpoint.
    Strictly enforces role separation:
    - User Login accepts ONLY active accounts with role 'user'. Admin credentials are rejected.
    - Admin Login accepts ONLY active accounts with role 'admin'. User credentials are rejected.
    """
    if session.get('user_id'):
        if session.get('role') == 'admin':
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('dashboard.index'))

    # Determine login mode: check request path, query param, or form field
    login_type = 'admin' if request.path.startswith('/admin') else request.args.get('type', request.form.get('login_type', 'user')).lower().strip()
    if login_type not in ('user', 'admin'):
        login_type = 'user'

    if request.method == 'POST':
        identifier = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        form_login_type = request.form.get('login_type', '').lower().strip()
        if form_login_type in ('user', 'admin'):
            login_type = form_login_type
        elif request.path.startswith('/admin'):
            login_type = 'admin'

        # Basic presence validation
        if not identifier or not password:
            flash('Please enter both username and password.', 'danger')
            return render_template('login.html', username=identifier, login_type=login_type)

        # Query user by username or email
        db_user = None
        try:
            db_user = User.query.filter(
                (db.func.lower(User.username) == identifier.lower()) |
                (db.func.lower(User.email) == identifier.lower())
            ).first()
        except Exception:
            db_user = None

        if db_user and db_user.check_password(password):
            # 1. Check account active status
            if not db_user.is_active:
                flash('Your account has been deactivated. Please contact a system administrator.', 'danger')
                return render_template('login.html', username=identifier, login_type=login_type)

            # 2. Strict role separation check
            if login_type == 'admin':
                if db_user.role != 'admin':
                    flash('Access restricted: This account does not have administrator privileges.', 'danger')
                    return render_template('login.html', username=identifier, login_type='admin')
            else:  # login_type == 'user'
                if db_user.role != 'user':
                    flash('Access restricted: Administrator accounts must sign in via Admin Login.', 'danger')
                    return render_template('login.html', username=identifier, login_type='user')

            # 3. Successful role-verified authentication -> establish session
            session['user_id'] = db_user.id
            session['username'] = db_user.username
            session['role'] = db_user.role

            next_target = request.args.get('next')
            if db_user.role == 'admin':
                flash(f'Welcome back, Administrator {db_user.username}!', 'success')
                return redirect(next_target or url_for('admin.dashboard'))
            else:
                flash(f'Welcome back, {db_user.username}!', 'success')
                return redirect(next_target or url_for('dashboard.index'))

        flash('Invalid credentials. Please verify your username and password.', 'danger')
        return render_template('login.html', username=identifier, login_type=login_type)

    return render_template('login.html', login_type=login_type)

@auth_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """
    Dedicated admin login shortcut route.
    """
    if session.get('user_id'):
        if session.get('role') == 'admin':
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('dashboard.index'))
    return login()

@auth_bp.route('/logout')
def logout():
    """
    Clears all active session state and redirects to login.
    """
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))
