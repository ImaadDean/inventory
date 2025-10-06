from fastapi import APIRouter, Request, Form, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from ...config.database import get_database
from ...utils.timezone import now_kampala, kampala_to_utc
from ...config.settings import settings
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

templates = Jinja2Templates(directory="app/templates")
auth_routes = APIRouter(prefix="/auth", tags=["Authentication Web"])


@auth_routes.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Display login page"""
    return templates.TemplateResponse("auth/login.html", {"request": request})


@auth_routes.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """Handle login form submission"""
    try:
        user = await authenticate_user(username, password)
        if not user:
            return templates.TemplateResponse(
                "auth/login.html",
                {"request": request, "error": "Invalid username or password"}
            )

        if not user.is_active:
            return templates.TemplateResponse(
                "auth/login.html",
                {"request": request, "error": "Account is inactive"}
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

        # Redirect based on user role
        if user.role == "cashier":
            redirect_url = "/pos"
        else:
            redirect_url = "/dashboard"

        response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="access_token",
            value=f"Bearer {access_token}",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            httponly=True
        )
        return response

    except Exception as e:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Login failed. Please try again."}
        )


# Registration routes removed - Only admin/manager can create users





@auth_routes.get("/logout")
async def logout():
    """Handle logout"""
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response


@auth_routes.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Display forgot password page"""
    return templates.TemplateResponse("auth/forgot_password.html", {"request": request})


@auth_routes.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_form(request: Request):
    """Handle forgot password form submission"""
    try:
        # Get form data
        form_data = await request.form()
        email = form_data.get("email")

        if not email:
            return templates.TemplateResponse(
                "auth/forgot_password.html",
                {"request": request, "error": "Email is required"}
            )

        db = await get_database()

        # Find user by email
        user_data = await db.users.find_one({"email": email})
        if user_data:
            user = User(**user_data)

            # Only send email if user is active
            if user.is_active:
                # Generate reset token
                reset_token = generate_reset_token()

                # Store token in database
                token_stored = await store_reset_token(str(user.id), reset_token)
                if token_stored:
                    # Get base URL from request
                    base_url = str(request.base_url).rstrip('/')
                    # Send reset email
                    await send_password_reset_email(user.email, reset_token, user.full_name, base_url)

        # Always show success message for security (don't reveal if email exists)
        return templates.TemplateResponse(
            "auth/forgot_password.html",
            {"request": request, "success": "If the email exists in our system, you will receive a password reset link."}
        )

    except Exception as e:
        print(f"Forgot password error: {e}")
        return templates.TemplateResponse(
            "auth/forgot_password.html",
            {"request": request, "error": "An error occurred. Please try again."}
        )


@auth_routes.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request):
    """Display reset password page"""
    token = request.query_params.get("token")
    if not token:
        return RedirectResponse(url="/auth/login?error=invalid_token", status_code=status.HTTP_302_FOUND)

    # Verify token is valid
    user_id = await verify_reset_token(token)
    if not user_id:
        return RedirectResponse(url="/auth/login?error=invalid_token", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse("auth/reset_password.html", {"request": request, "token": token})


@auth_routes.post("/reset-password", response_class=HTMLResponse)
async def reset_password_form(request: Request):
    """Handle reset password form submission"""
    try:
        # Get form data
        form_data = await request.form()
        token = form_data.get("token")
        new_password = form_data.get("new_password")
        confirm_password = form_data.get("confirm_password")

        if not all([token, new_password, confirm_password]):
            return templates.TemplateResponse(
                "auth/reset_password.html",
                {"request": request, "token": token, "error": "All fields are required"}
            )

        # Validate passwords match
        if new_password != confirm_password:
            return templates.TemplateResponse(
                "auth/reset_password.html",
                {"request": request, "token": token, "error": "Passwords do not match"}
            )
        
        # Validate password length (bcrypt limitation)
        if len(new_password.encode('utf-8')) > 72:
            return templates.TemplateResponse(
                "auth/reset_password.html",
                {"request": request, "token": token, "error": "Password is too long. Please use a password with fewer than 72 characters."}
            )

        # Verify reset token
        user_id = await verify_reset_token(token)
        if not user_id:
            return RedirectResponse(url="/auth/login?error=invalid_token", status_code=status.HTTP_302_FOUND)

        # Get user
        user = await get_user_by_id(user_id)
        if not user or not user.is_active:
            return RedirectResponse(url="/auth/login?error=invalid_token", status_code=status.HTTP_302_FOUND)

        # Hash new password
        new_hashed_password = get_password_hash(new_password)

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
        await mark_token_as_used(token)

        # Send confirmation email
        await send_password_changed_notification(user.email, user.full_name)

        # Redirect to login with success message
        return RedirectResponse(url="/auth/login?reset=success", status_code=status.HTTP_302_FOUND)

    except Exception as e:
        print(f"Reset password error: {e}")
        return templates.TemplateResponse(
            "auth/reset_password.html",
            {"request": request, "token": token, "error": "An error occurred. Please try again."}
        )


@auth_routes.get("/test")
async def test_route():
    """Test route to verify auth routes are working"""
    return {"message": "Auth routes are working!", "timestamp": now_kampala()}


