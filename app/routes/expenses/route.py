from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_user, verify_token, get_user_by_username
from app.models.user import User

# Initialize router and templates
expenses_routes = APIRouter()
templates = Jinja2Templates(directory="app/templates")

async def get_current_user_hybrid(request: Request) -> User:
    """Get current user from either JWT token or cookie"""
    
    # Try cookie authentication first (for web interface)
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            # Handle Bearer prefix in cookie value
            token = access_token
            if access_token.startswith("Bearer "):
                token = access_token[7:]  # Remove "Bearer " prefix
            
            payload = verify_token(token)
            if payload:
                username = payload.get("sub")
                if username:
                    user = await get_user_by_username(username)
                    if user and user.is_active:
                        return user
        except Exception:
            pass
    
    # If no valid authentication found, raise HTTPException to redirect to login
    raise HTTPException(
        status_code=401,
        detail="Authentication required"
    )

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
