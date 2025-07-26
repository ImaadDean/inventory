from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from ...models import User
from ...utils.auth import get_current_user, verify_token, get_user_by_username

templates = Jinja2Templates(directory="app/templates")
pos_routes = APIRouter(prefix="/pos", tags=["Point of Sale Web"])


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


@pos_routes.get("/", response_class=HTMLResponse)
async def pos_page(request: Request):
    """Display POS interface page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return templates.TemplateResponse(
        "pos/index.html",
        {"request": request, "user": current_user}
    )