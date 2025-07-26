from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from ...models import User
from ...utils.auth import get_current_user, verify_token, get_user_by_username
from ...config.database import get_database

templates = Jinja2Templates(directory="app/templates")
customers_routes = APIRouter(prefix="/customers", tags=["Customer Management Web"])


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


@customers_routes.get("/", response_class=HTMLResponse)
async def customers_page(request: Request):
    """Display customers management page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return templates.TemplateResponse(
        "customers/index.html",
        {"request": request, "user": current_user}
    )


@customers_routes.post("/", response_class=HTMLResponse)
async def create_customer(
    request: Request,
    name: str = Form(...),
    email: str = Form(None),
    phone: str = Form(None),
    address: str = Form(None),
    city: str = Form(None),
    postal_code: str = Form(None),
    country: str = Form(None),
    notes: str = Form(None)
):
    """Handle customer creation from form submission"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    db = await get_database()

    try:
        # Check if customer with same email already exists (if email provided)
        if email and email.strip():
            existing_customer = await db.customers.find_one({"email": email.strip()})
            if existing_customer:
                return RedirectResponse(
                    url="/customers/?error=Customer with this email already exists",
                    status_code=302
                )

        # Create customer document
        customer_doc = {
            "name": name.strip(),
            "email": email.strip() if email else None,
            "phone": phone.strip() if phone else None,
            "address": address.strip() if address else None,
            "city": city.strip() if city else None,
            "postal_code": postal_code.strip() if postal_code else None,
            "country": country.strip() if country else None,
            "date_of_birth": None,  # Can be added later via edit
            "is_active": True,
            "total_purchases": 0.0,
            "total_orders": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "last_purchase_date": None,
            "notes": notes.strip() if notes else None
        }

        # Insert customer
        result = await db.customers.insert_one(customer_doc)

        # Redirect with success message
        return RedirectResponse(
            url="/customers/?success=Customer created successfully",
            status_code=302
        )

    except Exception as e:
        print(f"Error creating customer: {e}")
        return RedirectResponse(
            url="/customers/?error=Failed to create customer",
            status_code=302
        )