"""
Authentication API routes.
"""
from flask import Blueprint, request, jsonify, session
from services.auth_service import authenticate_user

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/login', methods=['POST'])
def login():
    """Login endpoint."""
    data = request.get_json(silent=True) or {}
    
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({
            'success': False,
            'message': 'กรุณากรอก username และ password'
        }), 400

    user = authenticate_user(username, password)
    if user is None:
        return jsonify({
            'success': False,
            'message': 'Username หรือ Password ไม่ถูกต้อง'
        }), 401

    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']

    redirect_url = '/admin/devices' if user['role'] == 'admin' else '/user/register'
    return jsonify({
        'success': True,
        'user': user,
        'redirect': redirect_url
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Logout endpoint."""
    session.clear()
    return jsonify({
        'success': True,
        'redirect': '/login'
    })


@auth_bp.route('/session', methods=['GET'])
def get_session():
    """Get current session info."""
    if 'user_id' in session:
        return jsonify({
            'logged_in': True,
            'user': {
                'id': session['user_id'],
                'username': session.get('username'),
                'role': session.get('role')
            }
        })
    return jsonify({'logged_in': False})
