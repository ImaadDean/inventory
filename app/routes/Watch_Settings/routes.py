from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from ...utils.auth import verify_token, get_user_by_username
from ...models import User

templates = Jinja2Templates(directory="app/templates")
watch_settings_routes = APIRouter(prefix="/products/watch-settings", tags=["Watch Settings Web"])

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

@watch_settings_routes.get("/", response_class=HTMLResponse)
async def watch_settings_page(request: Request):
    """Display watch settings management page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    # For now, we just render the page.
    # Later, we can pass data for the tables from the database.
    return templates.TemplateResponse(
        "Watch_Settings/index.html",
        {"request": request, "user": current_user}
    )