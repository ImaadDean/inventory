from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_user, verify_token, get_user_by_username
from app.models.user import User

# Initialize router and templates
suppliers_routes = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@suppliers_routes.get("/suppliers", response_class=HTMLResponse)
async def suppliers_page(request: Request):
    """Render the suppliers management page"""
    try:
        user = await get_current_user_hybrid(request)

        # Block cashiers from accessing suppliers
        if user.role == "cashier":
            return RedirectResponse(url="/pos", status_code=302)

        return templates.TemplateResponse("suppliers/index.html", {
            "request": request,
            "user": user
        })
    except HTTPException:
        # Redirect to login if not authenticated
        return RedirectResponse(url="/auth/login", status_code=302)
