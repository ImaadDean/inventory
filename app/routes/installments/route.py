from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from ...utils.auth import get_current_user, require_admin_or_manager, verify_token, get_user_by_username
from ...models import User, InstallmentStatus, PaymentStatus
from ...config.database import get_database
from ...utils.timezone import now_kampala, kampala_to_utc
from bson import ObjectId

router = APIRouter(prefix="/installments", tags=["Installments Web"])
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
    if not user or not user.is_active:
        return None

    return user


@router.get("/", response_class=HTMLResponse)
async def installments_page(request: Request):
    """Installments management page (Admin/Manager only)"""
    # Get current user from cookie
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    # Check if user has admin or manager role
    if current_user.role not in ['admin', 'inventory_manager']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin or Manager role required."
        )

    # Just render the page template - data will be loaded via API calls
    return templates.TemplateResponse(
        "installments/index.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Installment Management"
        }
    )


@router.get("/create", response_class=HTMLResponse)
async def create_installment_page(request: Request):
    """Create new installment page (Admin/Manager only)"""
    # Get current user from cookie
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    # Check if user has admin or manager role
    if current_user.role not in ['admin', 'inventory_manager']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin or Manager role required."
        )

    return templates.TemplateResponse(
        "installments/create.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Create Installment Plan"
        }
    )


# Removed installment detail page route - using modal instead
