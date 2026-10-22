"""
Authentication and authorization decorators and guards.
"""
from functools import wraps
from flask import session, jsonify, redirect, url_for, request

def login_required_api():
    """Blueprint before_request hook for user APIs."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401


def admin_required_api():
    """Blueprint before_request hook for admin APIs."""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401


def page_login_required(role: str | None = None):
    """View decorator for HTML page endpoints."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect('/login')
            if role and session.get('role') != role:
                return redirect('/login')
            return f(*args, **kwargs)
        return decorated_function
    return decorator
