from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
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
    if not user or not user.is_active:
        return None

    return user


@reports_routes.get("/", response_class=HTMLResponse)
async def reports_dashboard(request: Request):
    """Main reports dashboard"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        db = await get_database()
        
        # Get current time in Kampala timezone
        now = now_kampala()
        today_start = get_day_start(now)
        week_start = get_week_start(now)
        month_start = get_month_start(now)
        
        # Convert to UTC for database queries
        today_start_utc = kampala_to_utc(today_start)
        week_start_utc = kampala_to_utc(week_start)
        month_start_utc = kampala_to_utc(month_start)
        
        # Get basic statistics
        stats = {
            "today": {
                "orders": await db.orders.count_documents({"created_at": {"$gte": today_start_utc}}),
                "revenue": 0,
                "customers": 0
            },
            "week": {
                "orders": await db.orders.count_documents({"created_at": {"$gte": week_start_utc}}),
                "revenue": 0,
                "customers": 0
            },
            "month": {
                "orders": await db.orders.count_documents({"created_at": {"$gte": month_start_utc}}),
                "revenue": 0,
                "customers": 0
            },
            "total": {
                "orders": await db.orders.count_documents({}),
                "products": await db.products.count_documents({}),
                "customers": await db.customers.count_documents({}),
                "categories": await db.categories.count_documents({})
            }
        }
        
        # Calculate revenue for each period
        for period, period_start in [("today", today_start_utc), ("week", week_start_utc), ("month", month_start_utc)]:
            revenue_pipeline = [
                {"$match": {"created_at": {"$gte": period_start}}},
                {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
            ]
            revenue_result = await db.orders.aggregate(revenue_pipeline).to_list(length=1)
            stats[period]["revenue"] = revenue_result[0]["total"] if revenue_result else 0
            
            # Count unique customers for the period
            customer_pipeline = [
                {"$match": {"created_at": {"$gte": period_start}}},
                {"$group": {"_id": "$customer_id"}},
                {"$count": "unique_customers"}
            ]
            customer_result = await db.orders.aggregate(customer_pipeline).to_list(length=1)
            stats[period]["customers"] = customer_result[0]["unique_customers"] if customer_result else 0
        
        return templates.TemplateResponse(
            "reports/index.html",
            {
                "request": request,
                "user": current_user,
                "stats": stats,
                "current_date": now,
                "page_title": "Reports Dashboard"
            }
        )
        
    except Exception as e:
        print(f"Error in reports dashboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to load reports dashboard")


@reports_routes.get("/sales", response_class=HTMLResponse)
async def sales_report(request: Request):
    """Sales reports page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

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

    return templates.TemplateResponse(
        "reports/financial.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Financial Reports"
        }
    )
