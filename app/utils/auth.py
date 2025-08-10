from datetime import datetime, timedelta
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..config.settings import settings
from ..config.database import get_database
from ..models import User, UserRole
from .timezone import now_kampala, kampala_to_utc
from bson import ObjectId

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT token scheme
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    kampala_now = now_kampala()
    if expires_delta:
        expire_kampala = kampala_now + expires_delta
    else:
        expire_kampala = kampala_now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # Convert to UTC for JWT (JWT expects UTC timestamps)
    expire = kampala_to_utc(expire_kampala)
    to_encode.update({"exp": expire.timestamp()})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_user_by_username(username: str) -> Optional[User]:
    """Get user by username from database"""
    db = await get_database()
    user_data = await db.users.find_one({"username": username})
    if user_data:
        return User(**user_data)
    return None


async def get_user_by_email(email: str) -> Optional[User]:
    """Get user by email from database"""
    db = await get_database()
    user_data = await db.users.find_one({"email": email})
    if user_data:
        return User(**user_data)
    return None


async def get_user_by_id(user_id: str) -> Optional[User]:
    """Get user by ObjectId from database"""
    try:
        from bson import ObjectId
        db = await get_database()
        user_data = await db.users.find_one({"_id": ObjectId(user_id)})
        if user_data:
            return User(**user_data)
        return None
    except Exception:
        return None


async def check_email_exists(email: str) -> bool:
    """Fast check if email exists in database without returning user data"""
    db = await get_database()
    user_count = await db.users.count_documents({"email": email}, limit=1)
    return user_count > 0


async def authenticate_user(username: str, password: str) -> Optional[User]:
    """Authenticate user with username and password"""
    user = await get_user_by_username(username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Get current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception

    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception

    user = await get_user_by_username(username)
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    return user


def require_roles(allowed_roles: list[UserRole]):
    """Dependency to check if user has required role"""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return current_user
    return role_checker


# Common role dependencies
require_admin = require_roles([UserRole.ADMIN])
require_admin_or_inventory = require_roles([UserRole.ADMIN, UserRole.INVENTORY_MANAGER])
require_any_role = require_roles([UserRole.ADMIN, UserRole.CASHIER, UserRole.INVENTORY_MANAGER])