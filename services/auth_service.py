"""
Authentication and user management service.
"""
import bcrypt
import sqlite3
import logging
from database import query_one, query_all, execute

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception as e:
        logger.error("Password verification error: %s", e)
        return False


def authenticate_user(username: str, password: str) -> dict | None:
    """
    Authenticate user by username and password.
    Returns user dict without password if valid, None otherwise.
    """
    user = query_one("SELECT * FROM users WHERE username = ?", (username,))
    if user is None:
        return None
        
    if verify_password(password, user['password']):
        user_copy = dict(user)
        del user_copy['password']
        return user_copy
        
    return None


def get_user_by_id(user_id: int) -> dict | None:
    """Get user by ID without password."""
    return query_one("SELECT id, username, role FROM users WHERE id = ?", (user_id,))


def create_user(username: str, password: str, role: str = 'user') -> int | None:
    """
    Create a new user.
    Returns new user ID, or None if username already exists.
    """
    hashed = hash_password(password)
    try:
        return execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, hashed, role)
        )
    except sqlite3.IntegrityError:
        logger.warning("Username '%s' already exists", username)
        return None


def update_user(user_id: int, username: str | None = None, password: str | None = None, role: str | None = None) -> bool:
    """Update user information."""
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
    sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
    try:
        execute(sql, tuple(params))
        return True
    except sqlite3.IntegrityError:
        logger.warning("Failed to update user %s: username collision", user_id)
        return False


def delete_user(user_id: int) -> bool:
    """Delete a user."""
    execute("DELETE FROM users WHERE id = ?", (user_id,))
    return True


def get_all_users() -> list[dict]:
    """Get all users without passwords."""
    return query_all("SELECT id, username, role FROM users ORDER BY username")
