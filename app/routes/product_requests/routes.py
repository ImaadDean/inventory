from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_user_hybrid

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/product-requests", response_class=HTMLResponse)
async def product_requests_page(
    request: Request,
    user = Depends(get_current_user_hybrid)
):
    """Product requests management page"""
    return templates.TemplateResponse(
        "product_requests/index.html",
        {"request": request, "user": user}
    )
