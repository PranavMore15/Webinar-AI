"""
Authentication and Authorization Utilities for WebinarAI.
Provides role-based access decorators, registration validators, and session helpers.
"""

from functools import wraps
import re
from flask import session, redirect, url_for, flash, request, jsonify

# Email validation regex conforming to standard RFC 5322 simplified pattern
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

def validate_registration_data(username: str, email: str, password: str, confirm_password: str):
    """
    Validates user registration input according to security specifications.
    Returns (is_valid: bool, error_message: str).
    """
    if not username or not username.strip():
        return False, "Username is required."
    
    clean_username = username.strip()
    if len(clean_username) < 3 or len(clean_username) > 50:
        return False, "Username must be between 3 and 50 characters."

    if not re.match(r'^[a-zA-Z0-9_]+$', clean_username):
        return False, "Username may only contain letters, numbers, and underscores."

    if not email or not email.strip():
        return False, "Email address is required."

    clean_email = email.strip()
    if not EMAIL_REGEX.match(clean_email):
        return False, "Please enter a valid email address (e.g., student@university.edu)."

    if not password:
        return False, "Password is required."

    if len(password) < 6:
        return False, "Password must be at least 6 characters long."

    if password != confirm_password:
        return False, "Passwords do not match."

    return True, ""

def login_required(f):
    """
    Ensures the user has an active session.
    Redirects to login page if unauthenticated, or returns 401 for API endpoints.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            if '/api/' in request.path or request.is_json:
                return jsonify({'success': False, 'message': 'Authentication required. Please log in.'}), 401
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def user_required(f):
    """
    Ensures the user has an active session and is a standard user.
    Administrators are strictly forbidden from accessing the processing workspace.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            if '/api/' in request.path or request.is_json:
                return jsonify({'success': False, 'message': 'Authentication required. Please log in.'}), 401
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.path))

        user_role = session.get('role')
        try:
            from app.models import db, User
            user = db.session.get(User, user_id)
            if user:
                if not user.is_active:
                    session.clear()
                    if '/api/' in request.path or request.is_json:
                        return jsonify({'success': False, 'message': 'Authentication required: User session is invalid or account was deactivated. Please log in again.'}), 401
                    flash('Your session has expired. Please log in again.', 'warning')
                    return redirect(url_for('auth.login', next=request.path))
                user_role = user.role
                session['role'] = user_role
                session['username'] = user.username
        except Exception:
            pass

        if user_role == 'admin':
            if '/api/' in request.path or request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Forbidden: Administrator accounts cannot access the processing workspace.'
                }), 403
            flash('Administrators cannot access the processing workspace. Please use the System Administration Console.', 'warning')
            return redirect(url_for('admin.dashboard'))

        if user_role and user_role != 'user':
            if '/api/' in request.path or request.is_json:
                return jsonify({'success': False, 'message': 'Forbidden: Access denied.'}), 403
            return redirect(url_for('auth.login'))

        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """
    Ensures the user has an active session and the 'admin' role.
    Rejects ordinary users with 403 for API or redirect for pages, preventing unauthorized access.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            if '/api/' in request.path or request.is_json:
                return jsonify({'success': False, 'message': 'Authentication required. Please log in.'}), 401
            flash('Administrator authentication required.', 'warning')
            return redirect(url_for('auth.admin_login', next=request.path))

        user_role = session.get('role')
        try:
            from app.models import db, User
            user = db.session.get(User, user_id)
            if user:
                if not user.is_active:
                    session.clear()
                    if '/api/' in request.path or request.is_json:
                        return jsonify({'success': False, 'message': 'Authentication required: Administrator session is invalid. Please log in again.'}), 401
                    flash('Your administrator session has expired. Please log in again.', 'warning')
                    return redirect(url_for('auth.admin_login', next=request.path))
                user_role = user.role
                session['role'] = user_role
                session['username'] = user.username
        except Exception:
            pass

        if user_role != 'admin':
            if '/api/' in request.path or request.is_json:
                return jsonify({'success': False, 'message': 'Forbidden: Administrator privileges required.'}), 403
            flash('Access denied: Administrator privileges required.', 'danger')
            return redirect(url_for('dashboard.index'))

        return f(*args, **kwargs)
    return decorated_function
