from fastapi import HTTPException, status, Depends
from typing import List
from ..models import User
from .auth import get_current_user


def require_roles(allowed_roles: List[str]):
    """
    Dependency to require specific roles for accessing endpoints
    
    Args:
        allowed_roles: List of roles that are allowed to access the endpoint
        
    Returns:
        Function that can be used as a FastAPI dependency
    """
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(allowed_roles)}"
            )
        return current_user
    
    return role_checker


def require_admin(current_user: User = Depends(get_current_user)):
    """Dependency to require admin role"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin role required."
        )
    return current_user


def require_admin_or_manager(current_user: User = Depends(get_current_user)):
    """Dependency to require admin or manager role"""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin or Manager role required."
        )
    return current_user


def require_manager_or_above(current_user: User = Depends(get_current_user)):
    """Dependency to require manager role or above (admin, manager)"""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Manager role or above required."
        )
    return current_user


def can_manage_users(current_user: User = Depends(get_current_user)):
    """Check if user can manage other users (admin or manager)"""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only administrators and managers can manage users."
        )
    return current_user


def can_create_users(current_user: User = Depends(get_current_user)):
    """Check if user can create new users (admin or manager)"""
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only administrators and managers can create users."
        )
    return current_user


def can_delete_users(current_user: User = Depends(get_current_user)):
    """Check if user can delete users (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only administrators can delete users."
        )
    return current_user


def can_modify_user_roles(current_user: User = Depends(get_current_user)):
    """Check if user can modify user roles (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only administrators can modify user roles."
        )
    return current_user


def is_admin(user: User) -> bool:
    """Check if user is admin"""
    return user.role == "admin"


def is_manager(user: User) -> bool:
    """Check if user is manager"""
    return user.role == "manager"


def is_admin_or_manager(user: User) -> bool:
    """Check if user is admin or manager"""
    return user.role in ["admin", "manager"]


def can_access_admin_features(user: User) -> bool:
    """Check if user can access admin features"""
    return user.role in ["admin", "manager"]


def get_user_permissions(user: User) -> dict:
    """Get user permissions based on role"""
    permissions = {
        "can_view_dashboard": True,
        "can_manage_inventory": False,
        "can_create_users": False,
        "can_edit_users": False,
        "can_delete_users": False,
        "can_modify_roles": False,
        "can_view_reports": False,
        "can_manage_suppliers": False,
        "can_manage_expenses": False,
        "can_access_pos": True,
        "can_view_orders": False,
        "can_manage_orders": False
    }
    
    if user.role == "admin":
        # Admin has all permissions
        permissions.update({
            "can_manage_inventory": True,
            "can_create_users": True,
            "can_edit_users": True,
            "can_delete_users": True,
            "can_modify_roles": True,
            "can_view_reports": True,
            "can_manage_suppliers": True,
            "can_manage_expenses": True,
            "can_view_orders": True,
            "can_manage_orders": True
        })
    elif user.role == "manager":
        # Manager has most permissions except user deletion and role modification
        permissions.update({
            "can_manage_inventory": True,
            "can_create_users": True,
            "can_edit_users": True,
            "can_view_reports": True,
            "can_manage_suppliers": True,
            "can_manage_expenses": True,
            "can_view_orders": True,
            "can_manage_orders": True
        })
    elif user.role == "cashier":
        # Cashier has limited permissions
        permissions.update({
            "can_view_reports": True,
            "can_view_orders": True
        })
    
    return permissions
