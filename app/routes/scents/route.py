from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from typing import Optional
from ...models import User
from ...utils.auth import get_current_user, verify_token, get_user_by_username
from ...config.database import get_database
from ...utils.timezone import now_kampala, kampala_to_utc

templates = Jinja2Templates(directory="app/templates")
scents_routes = APIRouter(prefix="/scents", tags=["Scents Management Web"])


async def get_current_user_from_cookie(request: Request):
    """Get current user from cookie for web routes"""
    try:
        token = request.cookies.get("access_token")
        if not token:
            return None
        
        # Remove 'Bearer ' prefix if present
        if token.startswith("Bearer "):
            token = token[7:]
        
        payload = verify_token(token)
        if not payload:
            return None
        
        username = payload.get("sub")
        if not username:
            return None
        
        user = await get_user_by_username(username)
        return user
    except Exception:
        return None


@scents_routes.get("/", response_class=HTMLResponse)
async def scents_page(request: Request):
    """Display scents management page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return templates.TemplateResponse(
        "scents/index.html",
        {"request": request, "user": current_user}
    )


@scents_routes.post("/", response_class=HTMLResponse)
async def create_scent(
    request: Request,
    name: str = Form(...),
    description: str = Form(None),
    scent_family: str = Form(None),
    top_notes: str = Form(None),
    middle_notes: str = Form(None),
    base_notes: str = Form(None),
    longevity: str = Form(None),
    sillage: str = Form(None),
    season: str = Form(None),
    occasion: str = Form(None),
    gender: str = Form(None),
    is_active: bool = Form(True)
):
    """Handle scent creation from form submission"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        db = await get_database()
        
        # Check if scent name already exists
        existing_scent = await db.scents.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
        if existing_scent:
            return RedirectResponse(url="/scents?error=A scent with this name already exists", status_code=302)
        
        # Create scent document
        scent_doc = {
            "name": name.strip(),
            "description": description.strip() if description else None,
            "scent_family": scent_family.strip() if scent_family else None,
            "top_notes": top_notes.strip() if top_notes else None,
            "middle_notes": middle_notes.strip() if middle_notes else None,
            "base_notes": base_notes.strip() if base_notes else None,
            "longevity": longevity.strip() if longevity else None,
            "sillage": sillage.strip() if sillage else None,
            "season": season.strip() if season else None,
            "occasion": occasion.strip() if occasion else None,
            "gender": gender.strip() if gender else None,
            "is_active": is_active,
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": None
        }
        
        # Insert scent
        result = await db.scents.insert_one(scent_doc)
        
        return RedirectResponse(url="/scents?success=Scent created successfully", status_code=302)
        
    except Exception as e:
        return RedirectResponse(url=f"/scents?error=Failed to create scent: {str(e)}", status_code=302)


@scents_routes.post("/{scent_id}/update", response_class=HTMLResponse)
async def update_scent(
    request: Request,
    scent_id: str,
    name: str = Form(...),
    description: str = Form(None),
    scent_family: str = Form(None),
    top_notes: str = Form(None),
    middle_notes: str = Form(None),
    base_notes: str = Form(None),
    longevity: str = Form(None),
    sillage: str = Form(None),
    season: str = Form(None),
    occasion: str = Form(None),
    gender: str = Form(None),
    is_active: bool = Form(True)
):
    """Handle scent update from form submission"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        db = await get_database()
        
        # Validate scent ID
        if not ObjectId.is_valid(scent_id):
            return RedirectResponse(url="/scents?error=Invalid scent ID", status_code=302)
        
        # Check if scent exists
        existing_scent = await db.scents.find_one({"_id": ObjectId(scent_id)})
        if not existing_scent:
            return RedirectResponse(url="/scents?error=Scent not found", status_code=302)
        
        # Check if new name conflicts with existing scent
        name_conflict = await db.scents.find_one({
            "name": {"$regex": f"^{name}$", "$options": "i"},
            "_id": {"$ne": ObjectId(scent_id)}
        })
        if name_conflict:
            return RedirectResponse(url="/scents?error=A scent with this name already exists", status_code=302)
        
        # Build update document
        update_doc = {
            "name": name.strip(),
            "description": description.strip() if description else None,
            "scent_family": scent_family.strip() if scent_family else None,
            "top_notes": top_notes.strip() if top_notes else None,
            "middle_notes": middle_notes.strip() if middle_notes else None,
            "base_notes": base_notes.strip() if base_notes else None,
            "longevity": longevity.strip() if longevity else None,
            "sillage": sillage.strip() if sillage else None,
            "season": season.strip() if season else None,
            "occasion": occasion.strip() if occasion else None,
            "gender": gender.strip() if gender else None,
            "is_active": is_active,
            "updated_at": kampala_to_utc(now_kampala())
        }
        
        # Update scent
        await db.scents.update_one(
            {"_id": ObjectId(scent_id)},
            {"$set": update_doc}
        )
        
        return RedirectResponse(url="/scents?success=Scent updated successfully", status_code=302)
        
    except Exception as e:
        return RedirectResponse(url=f"/scents?error=Failed to update scent: {str(e)}", status_code=302)


@scents_routes.post("/{scent_id}/delete", response_class=HTMLResponse)
async def delete_scent(request: Request, scent_id: str):
    """Handle scent deletion"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        db = await get_database()
        
        # Validate scent ID
        if not ObjectId.is_valid(scent_id):
            return RedirectResponse(url="/scents?error=Invalid scent ID", status_code=302)
        
        # Check if scent exists
        existing_scent = await db.scents.find_one({"_id": ObjectId(scent_id)})
        if not existing_scent:
            return RedirectResponse(url="/scents?error=Scent not found", status_code=302)
        
        # Check if scent is used by any products
        products_using_scent = await db.products.count_documents({"scent_id": ObjectId(scent_id)})
        if products_using_scent > 0:
            return RedirectResponse(url=f"/scents?error=Cannot delete scent. It is currently used by {products_using_scent} product(s)", status_code=302)
        
        # Delete scent
        await db.scents.delete_one({"_id": ObjectId(scent_id)})
        
        return RedirectResponse(url="/scents?success=Scent deleted successfully", status_code=302)
        
    except Exception as e:
        return RedirectResponse(url=f"/scents?error=Failed to delete scent: {str(e)}", status_code=302)