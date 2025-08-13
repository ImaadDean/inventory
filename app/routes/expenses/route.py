from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_user, get_current_user_hybrid, verify_token, get_user_by_username
from app.models.user import User

# Initialize router and templates
expenses_routes = APIRouter()
templates = Jinja2Templates(directory="app/templates")



@expenses_routes.get("/expenses", response_class=HTMLResponse)
async def expenses_page(request: Request):
    """Render the expenses management page"""
    try:
        user = await get_current_user_hybrid(request)

        # Block cashiers from accessing expenses
        if user.role == "cashier":
            return RedirectResponse(url="/pos", status_code=302)

        return templates.TemplateResponse("expenses/index.html", {
            "request": request,
            "user": user
        })
    except HTTPException:
        # Redirect to login if not authenticated
        return RedirectResponse(url="/auth/login", status_code=302)
