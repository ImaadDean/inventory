from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from decimal import Decimal
from bson import ObjectId
from ...models import User
from ...utils.auth import verify_token, get_user_by_username
from ...config.database import get_database

sales_routes = APIRouter(prefix="/sales", tags=["Sales Web"])
templates = Jinja2Templates(directory="app/templates")


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


@sales_routes.get("/", response_class=HTMLResponse)
async def sales_page(request: Request):
    """Display sales management page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return templates.TemplateResponse(
        "sales/index.html",
        {"request": request, "user": current_user}
    )


@sales_routes.get("/{sale_id}", response_class=HTMLResponse)
async def sale_detail_page(request: Request, sale_id: str):
    """Display sale detail page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        db = await get_database()
        sale = await db.sales.find_one({"_id": ObjectId(sale_id)})
        
        if not sale:
            return RedirectResponse(url="/sales/?error=Sale not found", status_code=302)

        return templates.TemplateResponse(
            "sales/detail.html",
            {"request": request, "user": current_user, "sale": sale}
        )
    except Exception as e:
        return RedirectResponse(url="/sales/?error=Invalid sale ID", status_code=302)