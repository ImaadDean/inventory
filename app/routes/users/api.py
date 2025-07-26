from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional
from datetime import datetime
from bson import ObjectId
from ...config.database import get_database
from ...schemas.user import UserCreate, UserUpdate, UserResponse, UserList
from ...models import User
from ...utils.auth import (
    get_password_hash,
    require_admin,
    get_current_user
)

router = APIRouter(prefix="/api/users", tags=["User Management API"])


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(require_admin)
):
    """Create a new user (Admin only)"""
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
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(require_admin)
):
    """Get all users with pagination and filtering (Admin only)"""
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

    users = [
        UserResponse(
            id=str(user["_id"]),
            username=user["username"],
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"],
            is_active=user["is_active"],
            created_at=user["created_at"],
            updated_at=user.get("updated_at"),
            last_login=user.get("last_login")
        )
        for user in users_data
    ]

    return UserList(
        users=users,
        total=total,
        page=page,
        size=size
    )