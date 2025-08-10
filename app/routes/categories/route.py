from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from bson import ObjectId
from ...models import User
from ...utils.auth import get_current_user, verify_token, get_user_by_username
from ...config.database import get_database

templates = Jinja2Templates(directory="app/templates")
categories_routes = APIRouter(prefix="/categories", tags=["Category Management Web"])


async def get_current_user_from_cookie(request: Request):
    """Get current user from cookie for HTML routes"""
    access_token = request.cookies.get("access_token")
    if not access_token:
        return None
    
    if access_token.startswith("Bearer "):
        token = access_token[7:]
    else:
        token = access_token
    
    payload = verify_token(token)
    if not payload:
        return None
    
    username = payload.get("sub")
    if not username:
        return None
    
    user = await get_user_by_username(username)
    return user


@categories_routes.get("/", response_class=HTMLResponse)
async def categories_page(request: Request):
    """Display categories management page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Block cashiers from accessing categories
    if current_user.role == "cashier":
        return RedirectResponse(url="/pos", status_code=302)

    return templates.TemplateResponse(
        "categories/index.html",
        {"request": request, "user": current_user}
    )


@categories_routes.post("/", response_class=HTMLResponse)
async def create_category(
    request: Request,
    name: str = Form(...),
    description: str = Form(None),
    is_active: str = Form(None)
):
    """Handle category creation from form submission"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Block cashiers from creating categories
    if current_user.role == "cashier":
        return RedirectResponse(url="/pos", status_code=302)

    db = await get_database()

    try:
        # Check if category with same name already exists
        existing_category = await db.categories.find_one({"name": name.strip()})
        if existing_category:
            return RedirectResponse(
                url="/categories/?error=Category with this name already exists",
                status_code=302
            )



        # Create category document
        category_doc = {
            "name": name.strip(),
            "description": description.strip() if description else None,
            "is_active": is_active == "on",  # Checkbox value
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "created_by": current_user.id  # Store user ObjectId instead of username
        }

        # Insert category
        result = await db.categories.insert_one(category_doc)

        # Redirect with success message
        return RedirectResponse(
            url="/categories/?success=Category created successfully",
            status_code=302
        )

    except Exception as e:
        print(f"Error creating category: {e}")
        return RedirectResponse(
            url="/categories/?error=Failed to create category",
            status_code=302
        )
