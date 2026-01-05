"""
Authentication service
"""
import bcrypt
from database.db_manager import execute_query, dict_from_row


def hash_password(password):
    """
    Hash password using bcrypt
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password, hashed):
    """
    Verify password against hash
    """
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def authenticate_user(username, password):
    """
    Authenticate user by username and password
    
    Returns:
        dict: User data if successful, None otherwise
    """
    query = "SELECT * FROM users WHERE username = ?"
    user = execute_query(query, (username,), fetch_one=True)
    
    if user is None:
        return None
    
    user_dict = dict_from_row(user)
    
    # Verify password
    if verify_password(password, user_dict['password']):
        # Remove password from returned data
        del user_dict['password']
        return user_dict
    
    return None


def get_user_by_id(user_id):
    """
    Get user by ID
    
    Returns:
        dict: User data without password
    """
    query = "SELECT id, username, role FROM users WHERE id = ?"
    user = execute_query(query, (user_id,), fetch_one=True)
    return dict_from_row(user)


def create_user(username, password, role='user'):
    """
    Create new user
    
    Returns:
        int: New user ID if successful, None if username exists
    """
    # Check if username exists
    existing = execute_query(
        "SELECT id FROM users WHERE username = ?",
        (username,),
        fetch_one=True
    )
    
    if existing:
        return None
    
    # Hash password
    hashed = hash_password(password)
    
    # Insert user
    query = "INSERT INTO users (username, password, role) VALUES (?, ?, ?)"
    return execute_query(query, (username, hashed, role), commit=True)


def update_user(user_id, username=None, password=None, role=None):
    """
    Update user information
    
    Returns:
        bool: True if successful
    """
    updates = []
    params = []
    
    if username:
        updates.append("username = ?")
        params.append(username)
    
    if password:
        updates.append("password = ?")
        params.append(hash_password(password))
    
    if role:
        updates.append("role = ?")
        params.append(role)
    
    if not updates:
        return False
    
    params.append(user_id)
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
    execute_query(query, tuple(params), commit=True)
    return True


def delete_user(user_id):
    """
    Delete user
    
    Returns:
        bool: True if successful
    """
    query = "DELETE FROM users WHERE id = ?"
    execute_query(query, (user_id,), commit=True)
    return True


def get_all_users():
    """
    Get all users (without passwords)
    
    Returns:
        list: List of user dictionaries
    """
    query = "SELECT id, username, role FROM users ORDER BY username"
    users = execute_query(query, fetch_all=True)
    return [dict(user) for user in users]
