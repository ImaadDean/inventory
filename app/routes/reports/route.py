from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from bson import ObjectId
from ...config.database import get_database
from ...utils.timezone import now_kampala, kampala_to_utc, get_day_start, get_week_start, get_month_start
from ...utils.auth import get_current_user, verify_token, get_user_by_username
from ...models import User

# Create router
reports_routes = APIRouter()

# Templates
templates = Jinja2Templates(directory="app/templates")

# Register timezone template filters
from ...utils.template_filters import TEMPLATE_FILTERS
for filter_name, filter_func in TEMPLATE_FILTERS.items():
    templates.env.filters[filter_name] = filter_func


async def get_current_user_from_cookie(request: Request):
    """Get current user from cookie for HTML routes"""
    access_token = request.cookies.get("access_token")
    print(f"🔍 Auth Debug - access_token from cookie: {access_token[:50] if access_token else 'None'}...")

    if not access_token:
        print("🔍 Auth Debug - No access token found in cookies")
        return None

    if access_token.startswith("Bearer "):
        token = access_token[7:]
    else:
        token = access_token

    payload = verify_token(token)
    if not payload:
        print("🔍 Auth Debug - Token verification failed")
        return None

    username = payload.get("sub")
    if not username:
        print("🔍 Auth Debug - No username in token payload")
        return None

    user = await get_user_by_username(username)
    if not user or not user.is_active:
        print(f"🔍 Auth Debug - User not found or inactive: {username}")
        return None

    print(f"🔍 Auth Debug - Successfully authenticated user: {username}")
    return user


@reports_routes.get("/", response_class=HTMLResponse)
async def reports_dashboard(request: Request):
    """Main reports dashboard"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Block cashiers from accessing reports
    if current_user.role == "cashier":
        return RedirectResponse(url="/pos", status_code=302)

    return templates.TemplateResponse(
        "reports/index.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Reports Dashboard"
        }
    )


@reports_routes.get("/sales", response_class=HTMLResponse)
async def sales_report(request: Request):
    """Sales reports page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Block cashiers from accessing sales reports
    if current_user.role == "cashier":
        return RedirectResponse(url="/pos", status_code=302)

    return templates.TemplateResponse(
        "reports/sales.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Sales Reports"
        }
    )


@reports_routes.get("/inventory", response_class=HTMLResponse)
async def inventory_report(request: Request):
    """Inventory reports page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Block cashiers from accessing inventory reports
    if current_user.role == "cashier":
        return RedirectResponse(url="/pos", status_code=302)

    return templates.TemplateResponse(
        "reports/inventory.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Inventory Reports"
        }
    )


@reports_routes.get("/customers", response_class=HTMLResponse)
async def customers_report(request: Request):
    """Customer reports page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Block cashiers from accessing customer reports
    if current_user.role == "cashier":
        return RedirectResponse(url="/pos", status_code=302)

    return templates.TemplateResponse(
        "reports/customers.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Customer Reports"
        }
    )


@reports_routes.get("/financial", response_class=HTMLResponse)
async def financial_report(request: Request):
    """Financial reports page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Block cashiers from accessing financial reports
    if current_user.role == "cashier":
        return RedirectResponse(url="/pos", status_code=302)

    return templates.TemplateResponse(
        "reports/financial.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Financial Reports"
        }
    )


@reports_routes.get("/test-chart", response_class=HTMLResponse)
async def test_chart(request: Request):
    """Test chart page for debugging"""
    return templates.TemplateResponse("test_chart.html", {"request": request})
