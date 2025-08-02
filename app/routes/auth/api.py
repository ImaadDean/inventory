from fastapi import APIRouter, HTTPException, status, Depends, Request
from datetime import datetime, timedelta
from ...utils.timezone import now_kampala, kampala_to_utc
from ...config.database import get_database
from ...config.settings import settings
from ...schemas.auth import UserLogin, UserRegister, UserResponse, Token, PasswordChange, ForgotPasswordRequest, ResetPasswordRequest
from ...models import User
from ...utils.auth import (
    authenticate_user,
    get_password_hash,
    create_access_token,
    get_current_user,
    verify_password,
    get_user_by_id
)
from ...utils.email import (
    generate_reset_token,
    store_reset_token,
    verify_reset_token,
    mark_token_as_used,
    send_password_reset_email,
    send_password_changed_notification
)

router = APIRouter(prefix="/api/auth", tags=["Authentication API"])


@router.get("/ping")
async def ping(request: Request):
    """Test endpoint to check request base URL detection"""
    base_url = str(request.base_url).rstrip('/')
    return {
        "base_url": base_url,
        "host": request.headers.get("host"),
        "scheme": request.url.scheme,
        "email_reset_url_example": f"{base_url}/auth/reset-password?token=example123"
    }


# Public registration removed - Only admin/manager can create users


@router.post("/login", response_model=Token)
async def login_user(user_credentials: UserLogin):
    """Authenticate user and return access token"""
    user = await authenticate_user(user_credentials.username, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # Update last login and activity
    db = await get_database()
    current_time = kampala_to_utc(now_kampala())
    await db.users.update_one(
        {"_id": user.id},
        {"$set": {
            "last_login": current_time,
            "last_activity": current_time
        }}
    )

    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active
        )
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active
    )


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user)
):
    """Change user password"""
    # Verify current password
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )

    # Hash new password
    new_hashed_password = get_password_hash(password_data.new_password)

    # Update password in database
    db = await get_database()
    await db.users.update_one(
        {"_id": current_user.id},
        {"$set": {
            "hashed_password": new_hashed_password,
            "updated_at": datetime.utcnow()
        }}
    )

    return {"message": "Password changed successfully"}


@router.post("/forgot-password")
async def forgot_password(request_data: ForgotPasswordRequest, request: Request):
    """Send password reset email"""
    try:
        db = await get_database()

        # Find user by email
        user_data = await db.users.find_one({"email": request_data.email})
        if not user_data:
            # Don't reveal if email exists or not for security
            return {"message": "If the email exists in our system, you will receive a password reset link."}

        user = User(**user_data)

        # Check if user is active
        if not user.is_active:
            return {"message": "If the email exists in our system, you will receive a password reset link."}

        # Generate reset token
        reset_token = generate_reset_token()

        # Store token in database
        token_stored = await store_reset_token(str(user.id), reset_token)
        if not token_stored:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate reset token"
            )

        # Get base URL from request and send reset email
        base_url = str(request.base_url).rstrip('/')
        email_sent = await send_password_reset_email(user.email, reset_token, user.full_name, base_url)
        if not email_sent:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send reset email"
            )

        return {"message": "If the email exists in our system, you will receive a password reset link."}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in forgot password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """Reset password using token"""
    try:
        # Validate passwords match
        if request.new_password != request.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )

        # Verify reset token
        user_id = await verify_reset_token(request.token)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )

        # Get user
        user = await get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User not found"
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account is inactive"
            )

        # Hash new password
        new_hashed_password = get_password_hash(request.new_password)

        # Update password in database
        db = await get_database()
        await db.users.update_one(
            {"_id": user.id},
            {"$set": {
                "hashed_password": new_hashed_password,
                "updated_at": datetime.utcnow()
            }}
        )

        # Mark token as used
        await mark_token_as_used(request.token)

        # Send confirmation email
        await send_password_changed_notification(user.email, user.full_name)

        return {"message": "Password reset successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in reset password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )