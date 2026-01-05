"""
Authentication API routes
"""
from flask import Blueprint, request, jsonify, session
from services.auth_service import authenticate_user

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login endpoint
    
    Request:
        {
            "username": "admin",
            "password": "password123"
        }
    
    Response:
        {
            "success": true,
            "user": {
                "id": 1,
                "username": "admin",
                "role": "admin"
            },
            "redirect": "/admin/devices"
        }
    """
    data = request.get_json()
    
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({
            'success': False,
            'message': 'กรุณากรอก username และ password'
        }), 400
    
    username = data['username']
    password = data['password']
    
    # Authenticate
    user = authenticate_user(username, password)
    
    if user is None:
        return jsonify({
            'success': False,
            'message': 'Username หรือ Password ไม่ถูกต้อง'
        }), 401
    
    # Set session
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    
    # Determine redirect based on role
    redirect = '/admin/devices' if user['role'] == 'admin' else '/user/register'
    
    return jsonify({
        'success': True,
        'user': user,
        'redirect': redirect
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """
    Logout endpoint
    
    Response:
        {
            "success": true,
            "redirect": "/login"
        }
    """
    session.clear()
    
    return jsonify({
        'success': True,
        'redirect': '/login'
    })


@auth_bp.route('/session', methods=['GET'])
def get_session():
    """
    Get current session info
    
    Response:
        {
            "logged_in": true,
            "user": {
                "id": 1,
                "username": "admin",
                "role": "admin"
            }
        }
    """
    if 'user_id' in session:
        return jsonify({
            'logged_in': True,
            'user': {
                'id': session['user_id'],
                'username': session['username'],
                'role': session['role']
            }
        })
    
    return jsonify({
        'logged_in': False
    })
