from datetime import datetime, timedelta
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..config.settings import settings
from ..config.database import get_database
from ..models import User, UserRole
from .timezone import now_kampala, kampala_to_utc
from bson import ObjectId

# Password hashing with bcrypt backend configuration
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
    bcrypt__ident="2b"
)

# JWT token scheme
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    # Truncate password to 72 bytes to avoid bcrypt limitation
    if isinstance(plain_password, str):
        plain_password = plain_password.encode('utf-8')
    if len(plain_password) > 72:
        plain_password = plain_password[:72]
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    # Truncate password to 72 bytes to avoid bcrypt limitation
    if isinstance(password, str):
        password = password.encode('utf-8')
    if len(password) > 72:
        password = password[:72]
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
    """Get current authenticated user and update last activity"""
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

    # Update user's last activity (last seen) every time we verify authentication
    try:
        from .user_activity import update_user_activity
        await update_user_activity(str(user.id))
    except Exception as e:
        # Don't fail authentication if activity update fails, just log it
        print(f"Warning: Failed to update user activity for {username}: {e}")

    return user


async def get_current_user_no_activity_update(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Get current authenticated user without updating last activity (for health checks, etc.)"""
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


async def get_current_user_hybrid(request: Request) -> User:
    """Get current user from either JWT token or cookie and update last activity"""

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
                        # Update user's last activity
                        try:
                            from .user_activity import update_user_activity
                            await update_user_activity(str(user.id))
                        except Exception as e:
                            print(f"Warning: Failed to update user activity for {username}: {e}")
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
                        # Update user's last activity
                        try:
                            from .user_activity import update_user_activity
                            await update_user_activity(str(user.id))
                        except Exception as e:
                            print(f"Warning: Failed to update user activity for {username}: {e}")
                        return user
        except Exception as e:
            print(f"JWT auth failed: {e}")

    # If both methods fail, raise authentication error
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_hybrid_dependency():
    """FastAPI dependency wrapper for hybrid authentication"""
    async def dependency(request: Request) -> User:
        return await get_current_user_hybrid(request)
    return dependency


def require_roles(allowed_roles: list[UserRole]):
    """Dependency to check if user has required role"""
    async def role_checker(current_user: User = Depends(get_current_user_hybrid_dependency())) -> User:
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
require_admin_or_manager = require_roles([UserRole.ADMIN, UserRole.INVENTORY_MANAGER])  # Alias for installments
require_any_role = require_roles([UserRole.ADMIN, UserRole.CASHIER, UserRole.INVENTORY_MANAGER])