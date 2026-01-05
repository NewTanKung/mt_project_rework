"""
User service - Already implemented in auth_service
This file is kept for consistency with the project structure
"""
from .auth_service import (
    create_user,
    update_user,
    delete_user,
    get_all_users,
    get_user_by_id
)

__all__ = ['create_user', 'update_user', 'delete_user', 'get_all_users', 'get_user_by_id']
