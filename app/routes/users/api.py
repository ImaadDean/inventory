from fastapi import APIRouter, HTTPException, status, Depends, Query, Request, Header
from typing import Optional, Union
from datetime import datetime
from bson import ObjectId
from ...config.database import get_database
from ...schemas.user import UserCreate, UserUpdate, UserResponse, UserList, UserWithActivity
from ...models import User
from ...utils.auth import (
    get_password_hash,
    get_current_user,
    get_current_user_hybrid,
    get_current_user_hybrid_dependency,
    verify_token,
    get_user_by_username
)
from ...utils.authorization import (
    require_admin,
    require_admin_or_manager,
    can_create_users,
    can_delete_users,
    can_modify_user_roles
)
from ...utils.user_activity import get_detailed_user_status, update_user_activity

router = APIRouter(prefix="/api/users", tags=["User Management API"])





# Use centralized role dependencies that update Last Seen
from ...utils.auth import require_admin_or_inventory

# Simple header-based role checking functions
async def check_admin_or_manager(
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None)
) -> dict:
    """Check if user is admin or manager using headers"""
    if not x_user_id or not x_user_role:
        return {
            "is_admin_or_manager": False,
            "reason": "Missing headers: X-User-Id and X-User-Role required",
            "user_id": None,
            "user_role": None
        }
    
    # Validate role
    if x_user_role.lower() not in ["admin", "inventory_manager"]:
        return {
            "is_admin_or_manager": False,
            "reason": f"Invalid role '{x_user_role}'. Must be 'admin' or 'inventory_manager'",
            "user_id": x_user_id,
            "user_role": x_user_role
        }
    
    # Verify user exists in database
    try:
        db = await get_database()
        if ObjectId.is_valid(x_user_id):
            user = await db.users.find_one({"_id": ObjectId(x_user_id)})
        else:
            user = None
            
        if not user:
            return {
                "is_admin_or_manager": False,
                "reason": f"User with ID '{x_user_id}' not found in database",
                "user_id": x_user_id,
                "user_role": x_user_role
            }
        
        # Verify role matches database
        if user["role"] != x_user_role:
            return {
                "is_admin_or_manager": False,
                "reason": f"Role mismatch. Header says '{x_user_role}' but database has '{user['role']}'",
                "user_id": x_user_id,
                "user_role": x_user_role
            }
        
        return {
            "is_admin_or_manager": True,
            "reason": "Role verified successfully",
            "user_id": x_user_id,
            "user_role": x_user_role,
            "username": user["username"],
            "email": user["email"]
        }
        
    except Exception as e:
        return {
            "is_admin_or_manager": False,
            "reason": f"Database error: {str(e)}",
            "user_id": x_user_id,
            "user_role": x_user_role
        }

async def require_admin_or_manager_header(
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None)
) -> dict:
    """Require admin or manager role via headers, raise exception if not valid"""
    check_result = await check_admin_or_manager(x_user_id, x_user_role)
    
    if not check_result["is_admin_or_manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Access denied",
                "reason": check_result["reason"],
                "required_headers": {
                    "X-User-Id": "Your user ID from database",
                    "X-User-Role": "admin or inventory_manager"
                },
                "example": {
                    "X-User-Id": "689c64d771dc9a7cb074625a", 
                    "X-User-Role": "admin"
                }
            }
        )
    
    return check_result


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    user_data: UserCreate
):
    """Create a new user (No authentication required)"""
    db = await get_database()

    # Check if username already exists
    existing_user = await db.users.find_one({"username": user_data.username})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    # Check if email already exists
    existing_email = await db.users.find_one({"email": user_data.email})
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hashed_password,
        role=user_data.role
    )

    # Insert user into database
    result = await db.users.insert_one(user.model_dump(by_alias=True, exclude={"id"}))
    user.id = result.inserted_id

    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login=user.last_login
    )


@router.get("/", response_model=UserList)
async def get_users(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None)
):
    """Get all users with pagination and filtering (No authentication required)"""
    try:
        db = await get_database()
        
        # No authentication required - endpoint is now public

        # Build filter query
        filter_query = {}
        if search:
            filter_query["$or"] = [
                {"username": {"$regex": search, "$options": "i"}},
                {"full_name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}}
            ]
        if role:
            filter_query["role"] = role
        if is_active is not None:
            filter_query["is_active"] = is_active

        # Get total count
        total = await db.users.count_documents(filter_query)

        # Get users with pagination
        skip = (page - 1) * size
        cursor = db.users.find(filter_query).skip(skip).limit(size).sort("created_at", -1)
        users_data = await cursor.to_list(length=size)

        users = []
        for user in users_data:
            # Get activity status for each user
            status_info = get_detailed_user_status(
                user.get("last_login"),
                user.get("last_activity")
            )

            user_with_activity = UserWithActivity(
                id=str(user["_id"]),
                username=user["username"],
                email=user["email"],
                full_name=user["full_name"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                updated_at=user.get("updated_at"),
                last_login=user.get("last_login"),
                last_activity=user.get("last_activity"),
                activity_status=status_info
            )

            users.append(user_with_activity)

        return UserList(
            users=users,
            total=total,
            page=page,
            size=size
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve users: {str(e)}"
        )


@router.get("/auth-test", response_model=dict)
async def test_authentication():
    """Test endpoint - no authentication required"""
    return {
        "authenticated": False,
        "message": "Users API endpoints are now public - no authentication required!",
        "endpoint_access": "Public access granted",
        "note": "Authentication has been removed from users endpoints",
        "new_endpoints": {
            "header_auth_test": "/api/users/admin/auth-test",
            "admin_users_list": "/api/users/admin/",
            "admin_user_delete": "/api/users/admin/{user_id}/delete"
        }
    }


@router.get("/admin/auth-test", response_model=dict)
async def test_admin_authentication(
    auth_info: dict = Depends(require_admin_or_manager_header)
):
    """Test endpoint to verify header-based admin/manager authentication"""
    return {
        "authenticated": True,
        "auth_method": "header-based",
        "user": {
            "id": auth_info["user_id"],
            "role": auth_info["user_role"],
            "username": auth_info.get("username"),
            "email": auth_info.get("email")
        },
        "permissions": {
            "can_view_users": True,
            "can_create_users": True,
            "can_edit_users": True,
            "can_delete_users": auth_info["user_role"] == "admin"
        },
        "message": "Header-based authentication successful!",
        "endpoint_access": "Granted - Admin or Inventory Manager role confirmed via headers"
    }


@router.get("/admin/", response_model=UserList)
async def get_users_admin(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    auth_info: dict = Depends(require_admin_or_manager_header)
):
    """Get all users with pagination and filtering (Admin/Manager authentication via headers required)"""
    try:
        db = await get_database()
        
        print(f"Admin access: User {auth_info['username']} ({auth_info['user_role']}) accessing users list")

        # Build filter query
        filter_query = {}
        if search:
            filter_query["$or"] = [
                {"username": {"$regex": search, "$options": "i"}},
                {"full_name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}}
            ]
        if role:
            filter_query["role"] = role
        if is_active is not None:
            filter_query["is_active"] = is_active

        # Get total count
        total = await db.users.count_documents(filter_query)

        # Get users with pagination
        skip = (page - 1) * size
        cursor = db.users.find(filter_query).skip(skip).limit(size).sort("created_at", -1)
        users_data = await cursor.to_list(length=size)

        users = []
        for user in users_data:
            # Get activity status for each user
            status_info = get_detailed_user_status(
                user.get("last_login"),
                user.get("last_activity")
            )

            user_with_activity = UserWithActivity(
                id=str(user["_id"]),
                username=user["username"],
                email=user["email"],
                full_name=user["full_name"],
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
                updated_at=user.get("updated_at"),
                last_login=user.get("last_login"),
                last_activity=user.get("last_activity"),
                activity_status=status_info
            )

            users.append(user_with_activity)

        return UserList(
            users=users,
            total=total,
            page=page,
            size=size
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_users_admin: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve users: {str(e)}"
        )


@router.delete("/admin/{user_id}/delete", response_model=dict)
async def delete_user_admin(
    user_id: str,
    auth_info: dict = Depends(require_admin_or_manager_header)
):
    """Delete a user with admin/manager authentication via headers"""
    try:
        db = await get_database()

        # Validate user ID
        if not ObjectId.is_valid(user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID"
            )

        # Check if user exists
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Prevent self-deletion
        if user_id == auth_info["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot delete your own account"
            )

        # Only admins can delete other admins
        if user["role"] == "admin" and auth_info["user_role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can delete admin accounts"
            )

        # Prevent deletion of the last admin
        if user["role"] == "admin":
            admin_count = await db.users.count_documents({"role": "admin"})
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete the last administrator account"
                )

        # Delete the user
        result = await db.users.delete_one({"_id": ObjectId(user_id)})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete user"
            )

        print(f"User {auth_info['username']} ({auth_info['user_role']}) deleted user {user['username']}")

        return {
            "success": True,
            "message": f"User '{user['username']}' deleted successfully",
            "deleted_user": {
                "id": user_id,
                "username": user["username"],
                "full_name": user["full_name"]
            },
            "deleted_by": {
                "id": auth_info["user_id"],
                "username": auth_info["username"],
                "role": auth_info["user_role"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user: {str(e)}"
        )


@router.get("/{user_id}", response_model=UserWithActivity)
async def get_user(user_id: str):
    """Get a single user by ID (No authentication required)"""
    try:
        db = await get_database()

        # Validate user ID
        if not ObjectId.is_valid(user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID"
            )

        # Get user
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Get activity status
        status_info = get_detailed_user_status(
            user.get("last_login"),
            user.get("last_activity")
        )

        return UserWithActivity(
            id=str(user["_id"]),
            username=user["username"],
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"],
            is_active=user["is_active"],
            created_at=user["created_at"],
            updated_at=user.get("updated_at"),
            last_login=user.get("last_login"),
            last_activity=user.get("last_activity"),
            activity_status=status_info
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve user: {str(e)}"
        )


@router.put("/{user_id}", response_model=dict)
async def update_user(
    user_id: str,
    user_update: UserUpdate
):
    """Update a user (No authentication required)"""
    try:
        db = await get_database()

        # Validate user ID
        if not ObjectId.is_valid(user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID"
            )

        # Check if user exists
        existing_user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Prepare update data
        update_data = {}
        if user_update.full_name is not None:
            update_data["full_name"] = user_update.full_name

        if user_update.email is not None:
            # Check if email already exists (excluding current user)
            existing_email = await db.users.find_one({
                "email": user_update.email,
                "_id": {"$ne": ObjectId(user_id)}
            })
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already exists"
                )
            update_data["email"] = user_update.email

        if user_update.username is not None:
            # Check if username already exists (excluding current user)
            existing_username = await db.users.find_one({
                "username": user_update.username,
                "_id": {"$ne": ObjectId(user_id)}
            })
            if existing_username:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already exists"
                )
            update_data["username"] = user_update.username

        if user_update.role is not None:
            # Validate role
            valid_roles = ["admin", "inventory_manager", "cashier"]
            if user_update.role not in valid_roles:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid role. Valid roles: {valid_roles}"
                )
            update_data["role"] = user_update.role

        if user_update.is_active is not None:
            update_data["is_active"] = user_update.is_active

        if user_update.password is not None:
            # Hash the new password
            update_data["hashed_password"] = get_password_hash(user_update.password)

        # Add updated timestamp
        update_data["updated_at"] = datetime.utcnow()

        # Update the user
        result = await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user"
            )

        # Get updated user
        updated_user = await db.users.find_one({"_id": ObjectId(user_id)})

        return {
            "success": True,
            "message": "User updated successfully",
            "user": {
                "id": str(updated_user["_id"]),
                "username": updated_user["username"],
                "email": updated_user["email"],
                "full_name": updated_user["full_name"],
                "role": updated_user["role"],
                "is_active": updated_user["is_active"],
                "updated_at": updated_user["updated_at"].isoformat()
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user: {str(e)}"
        )


@router.delete("/{user_id}", response_model=dict)
async def delete_user(
    user_id: str
):
    """Delete a user (No authentication required)"""
    try:
        db = await get_database()

        # Validate user ID
        if not ObjectId.is_valid(user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID"
            )

        # Check if user exists
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Note: Self-deletion prevention removed since authentication is disabled

        # Prevent deletion of the last admin
        if user["role"] == "admin":
            admin_count = await db.users.count_documents({"role": "admin"})
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete the last administrator account"
                )

        # Delete the user
        result = await db.users.delete_one({"_id": ObjectId(user_id)})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete user"
            )

        return {
            "success": True,
            "message": f"User '{user['username']}' deleted successfully",
            "deleted_user": {
                "id": user_id,
                "username": user["username"],
                "full_name": user["full_name"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user: {str(e)}"
        )