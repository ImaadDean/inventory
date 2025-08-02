from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from decimal import Decimal
from bson import ObjectId
from ...models import User
from ...utils.auth import verify_token, get_user_by_username
from ...config.database import get_database

orders_routes = APIRouter(prefix="/orders", tags=["Orders Web"])
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


@orders_routes.get("/", response_class=HTMLResponse)
async def orders_page(request: Request):
    """Display orders management page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return templates.TemplateResponse(
        "orders/index.html",
        {"request": request, "user": current_user}
    )


@orders_routes.get("/{order_id}", response_class=HTMLResponse)
async def order_detail_page(request: Request, order_id: str):
    """Display order detail page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        db = await get_database()
        order = await db.orders.find_one({"_id": ObjectId(order_id)})
        
        if not order:
            return RedirectResponse(url="/orders/?error=Order not found", status_code=302)

        return templates.TemplateResponse(
            "orders/detail.html",
            {"request": request, "user": current_user, "order": order}
        )
    except Exception as e:
        return RedirectResponse(url="/orders/?error=Invalid order ID", status_code=302)
