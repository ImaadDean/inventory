from fastapi import APIRouter, Request, Form, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from ...config.database import get_database
from ...config.settings import settings
from ...models import User
from ...utils.auth import (
    authenticate_user,
    get_password_hash,
    create_access_token,
    get_current_user,
    verify_password
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

        # Update last login
        db = await get_database()
        await db.users.update_one(
            {"_id": user.id},
            {"$set": {"last_login": datetime.utcnow()}}
        )

        # Create access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )

        # Redirect to dashboard with token in cookie
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
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


@auth_routes.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Display registration page"""
    return templates.TemplateResponse("auth/register.html", {"request": request})


@auth_routes.post("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    """Handle registration form submission"""
    print("=== REGISTRATION FORM ROUTE CALLED ===")
    try:
        # Get form data
        form_data = await request.form()
        full_name = form_data.get("full_name")
        username = form_data.get("username")
        email = form_data.get("email")
        password = form_data.get("password")
        confirm_password = form_data.get("confirm_password")

        print(f"Registration attempt - Username: {username}, Email: {email}, Full Name: {full_name}")

        # Validate required fields
        if not all([full_name, username, email, password, confirm_password]):
            return templates.TemplateResponse(
                "auth/register.html",
                {"request": request, "error": "All fields are required"}
            )
        # Validate passwords match
        if password != confirm_password:
            return templates.TemplateResponse(
                "auth/register.html",
                {"request": request, "error": "Passwords do not match"}
            )

        db = await get_database()

        # Check if username already exists
        existing_user = await db.users.find_one({"username": username})
        if existing_user:
            return templates.TemplateResponse(
                "auth/register.html",
                {"request": request, "error": "Username already exists"}
            )

        # Check if email already exists
        existing_email = await db.users.find_one({"email": email})
        if existing_email:
            return templates.TemplateResponse(
                "auth/register.html",
                {"request": request, "error": "Email already registered"}
            )

        # Create new user
        hashed_password = get_password_hash(password)
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            role="cashier"  # Default role for web registration
        )

        # Insert user into database
        result = await db.users.insert_one(user.model_dump(by_alias=True, exclude={"id"}))

        # Redirect to login page with success message
        return RedirectResponse(url="/auth/login?registered=true", status_code=status.HTTP_302_FOUND)

    except Exception as e:
        print(f"Registration error: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": f"Registration failed: {str(e)}"}
        )


@auth_routes.get("/logout")
async def logout():
    """Handle logout"""
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response


@auth_routes.get("/test")
async def test_route():
    """Test route to verify auth routes are working"""
    return {"message": "Auth routes are working!", "timestamp": datetime.utcnow()}