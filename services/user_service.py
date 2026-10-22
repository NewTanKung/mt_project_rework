"""
User service - Forwarder to auth_service.
"""
from services.auth_service import (
    create_user,
    update_user,
    delete_user,
    get_all_users,
    get_user_by_id
)

__all__ = ['create_user', 'update_user', 'delete_user', 'get_all_users', 'get_user_by_id']
