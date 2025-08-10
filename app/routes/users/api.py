from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from typing import Optional
from datetime import datetime
from bson import ObjectId
from ...config.database import get_database
from ...schemas.user import UserCreate, UserUpdate, UserResponse, UserList, UserWithActivity
from ...models import User
from ...utils.auth import (
    get_password_hash,
    get_current_user,
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


async def get_current_user_hybrid(request: Request) -> User:
    """Get current user from either JWT token or cookie"""

    # Try cookie authentication first (for web interface)
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            # Handle Bearer prefix in cookie value
            token = access_token
            if access_token.startswith("Bearer "):
                token = access_token[7:]  # Remove "Bearer " prefix

            payload = verify_token(token)
            if payload:
                username = payload.get("sub")
                if username:
                    user = await get_user_by_username(username)
                    if user and user.is_active:
                        return user
        except Exception as e:
            print(f"Cookie auth failed: {e}")

    # Try JWT token authentication (for API clients)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            payload = verify_token(token)
            if payload:
                username = payload.get("sub")
                if username:
                    user = await get_user_by_username(username)
                    if user and user.is_active:
                        return user
        except Exception as e:
            print(f"JWT auth failed: {e}")

    # If both methods fail, raise authentication error
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_roles_hybrid(allowed_roles: list[str]):
    """Dependency to check if user has required role using hybrid auth"""
    async def role_checker(request: Request) -> User:
        current_user = await get_current_user_hybrid(request)
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return current_user
    return role_checker


# Create hybrid role dependencies
require_admin_or_inventory_hybrid = require_roles_hybrid(["admin", "inventory_manager"])


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    user_data: UserCreate,
    current_user: User = Depends(require_admin_or_inventory_hybrid)
):
    """Create a new user (Admin or Manager only)"""
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
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(require_admin_or_inventory_hybrid)
):
    """Get all users with pagination and filtering (Admin or Manager only)"""
    db = await get_database()

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


@router.get("/auth-test", response_model=dict)
async def test_authentication(request: Request, current_user: User = Depends(require_admin_or_inventory_hybrid)):
    """Test endpoint to verify authentication is working"""
    return {
        "authenticated": True,
        "user": {
            "username": current_user.username,
            "email": current_user.email,
            "role": current_user.role,
            "is_active": current_user.is_active
        },
        "message": "Users API authentication successful!"
    }


@router.get("/{user_id}", response_model=UserWithActivity)
async def get_user(user_id: str, request: Request, current_user: User = Depends(require_admin_or_inventory_hybrid)):
    """Get a single user by ID"""
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
    user_update: UserUpdate,
    request: Request,
    current_user: User = Depends(require_admin_or_inventory_hybrid)
):
    """Update a user"""
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
    user_id: str,
    request: Request,
    current_user: User = Depends(require_admin_or_inventory_hybrid)
):
    """Delete a user"""
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
        if str(user["_id"]) == str(current_user.id):
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