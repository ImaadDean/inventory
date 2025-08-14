from fastapi import APIRouter, HTTPException, status, Depends, Query, Request, Header
from typing import Optional
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
    require_admin_or_inventory,
    require_admin
)
from ...utils.user_activity import get_detailed_user_status

router = APIRouter(prefix="/api/users", tags=["User Management API"])


# Hybrid authentication dependencies (cookies + JWT tokens)
async def require_admin_or_inventory_hybrid(request: Request) -> User:
    """Require admin or inventory_manager role via hybrid authentication (cookies or JWT)"""
    current_user = await get_current_user_hybrid(request)
    if current_user.role not in ["admin", "inventory_manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin or Inventory Manager role required."
        )
    return current_user


async def require_admin_hybrid(request: Request) -> User:
    """Require admin role via hybrid authentication (cookies or JWT)"""
    current_user = await get_current_user_hybrid(request)
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin role required."
        )
    return current_user


@router.get("/debug/whoami", response_model=dict)
async def debug_whoami(request: Request):
    """Debug endpoint to check current user's role and permissions"""
    try:
        current_user = await get_current_user_hybrid(request)
        return {
            "user_id": str(current_user.id),
            "username": current_user.username,
            "role": current_user.role,
            "is_active": current_user.is_active,
            "permissions": {
                "can_access_user_management": current_user.role in ["admin", "inventory_manager"],
                "required_roles_for_user_management": ["admin", "inventory_manager"],
                "can_delete_users": current_user.role == "admin"
            },
            "message": "Use this endpoint to check if you have the right permissions for user management",
            "auth_method": "hybrid (cookies or JWT tokens)"
        }
    except HTTPException as e:
        return {
            "authenticated": False,
            "error": e.detail,
            "message": "Authentication failed",
            "cookies_present": "access_token" in request.cookies,
            "auth_header_present": bool(request.headers.get("Authorization"))
        }



@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    user_data: UserCreate
):
    """Create a new user (Admin or Inventory Manager required)"""
    current_user = await require_admin_or_inventory_hybrid(request)
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
    """Get all users with pagination and filtering (Admin or Inventory Manager required)"""
    try:
        current_user = await require_admin_or_inventory_hybrid(request)
        db = await get_database()
        
        # Admin or Inventory Manager authentication required

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




@router.get("/{user_id}", response_model=UserWithActivity)
async def get_user(
    request: Request,
    user_id: str
):
    """Get a single user by ID (Admin or Inventory Manager required)"""
    try:
        current_user = await require_admin_or_inventory_hybrid(request)
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
    request: Request,
    user_id: str,
    user_update: UserUpdate
):
    """Update a user (Admin or Inventory Manager required)"""
    try:
        current_user = await require_admin_or_inventory_hybrid(request)
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
    request: Request,
    user_id: str
):
    """Delete a user (Admin role required)"""
    try:
        current_user = await require_admin_hybrid(request)
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
        if user_id == str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot delete your own account"
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