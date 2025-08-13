from fastapi import APIRouter, Request, Depends, HTTPException, status, Query
from typing import List, Optional
from bson import ObjectId
from ...models import User
from ...schemas.scent import ScentCreate, ScentUpdate, ScentResponse
from ...utils.auth import get_current_user_hybrid, get_current_user_hybrid_dependency, verify_token, get_user_by_username
from ...config.database import get_database
from ...utils.timezone import now_kampala, kampala_to_utc

router = APIRouter(prefix="/api/scents", tags=["Scents API"])





@router.get("/debug/{scent_id}")
async def debug_scent_products(
    scent_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Debug endpoint to check scent-product relationships"""
    try:
        db = await get_database()

        if not ObjectId.is_valid(scent_id):
            return {"error": "Invalid scent ID"}

        scent_obj_id = ObjectId(scent_id)

        # Get the scent
        scent = await db.scents.find_one({"_id": scent_obj_id})
        if not scent:
            return {"error": "Scent not found"}

        # Get all products with scents
        all_products = await db.products.find({
            "is_active": True,
            "$or": [
                {"scent_ids": {"$exists": True, "$ne": []}},
                {"scent_id": {"$exists": True, "$ne": None}}
            ]
        }).to_list(length=None)

        # Test different query approaches
        count1 = await db.products.count_documents({
            "is_active": True,
            "scent_ids": scent_obj_id
        })

        count2 = await db.products.count_documents({
            "is_active": True,
            "scent_id": scent_obj_id
        })

        count3 = await db.products.count_documents({
            "is_active": True,
            "$or": [
                {"scent_ids": scent_obj_id},
                {"scent_id": scent_obj_id}
            ]
        })

        return {
            "scent": {
                "id": str(scent["_id"]),
                "name": scent["name"],
                "id_type": str(type(scent["_id"]))
            },
            "query_results": {
                "scent_ids_array_match": count1,
                "scent_id_single_match": count2,
                "combined_or_match": count3
            },
            "all_products_with_scents": [
                {
                    "name": p.get("name"),
                    "scent_ids": [str(x) for x in (p.get("scent_ids") or [])],
                    "scent_ids_types": [str(type(x)) for x in (p.get("scent_ids") or [])],
                    "scent_id": str(p.get("scent_id")) if p.get("scent_id") else None,
                    "scent_id_type": str(type(p.get("scent_id"))) if p.get("scent_id") else None
                }
                for p in all_products
            ]
        }

    except Exception as e:
        return {"error": str(e)}


@router.get("/stats", response_model=dict)
async def get_scents_stats(
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get scents statistics for dashboard cards"""
    try:
        db = await get_database()

        # Get total scents count
        total_scents = await db.scents.count_documents({})

        # Get active scents count
        active_scents = await db.scents.count_documents({"is_active": True})

        # Get inactive scents count
        inactive_scents = total_scents - active_scents

        # Get products using scents count
        # Count products that have either scent_ids or scent_id fields with actual values
        products_with_scents = await db.products.count_documents({
            "is_active": True,
            "$or": [
                {"scent_ids": {"$exists": True, "$ne": [], "$ne": None, "$not": {"$size": 0}}},
                {"scent_id": {"$exists": True, "$ne": None}}
            ]
        })

        return {
            "total_scents": total_scents,
            "active_scents": active_scents,
            "inactive_scents": inactive_scents,
            "products_with_scents": products_with_scents
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve scents statistics: {str(e)}"
        )


@router.get("/table", response_model=List[dict])
async def get_scents_for_table(
    active_only: Optional[bool] = Query(False),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get scents with product counts for the scents table"""
    try:
        db = await get_database()

        # Build query
        query = {}
        if active_only:
            query["is_active"] = True

        # Get scents
        scents = await db.scents.find(query).sort("name", 1).to_list(length=None)

        # Format response with accurate product counts
        scent_list = []
        for scent in scents:
            scent_obj_id = scent["_id"]
            scent_str_id = str(scent_obj_id)

            # Use the same query logic as the debug endpoint (which works)
            product_count = await db.products.count_documents({
                "is_active": True,
                "$or": [
                    {"scent_ids": scent_obj_id},
                    {"scent_id": scent_obj_id}
                ]
            })

            scent_data = {
                "id": str(scent["_id"]),
                "name": scent["name"],
                "description": scent.get("description"),
                "product_count": product_count,
                "is_active": scent.get("is_active", True),
                "created_at": scent["created_at"].isoformat() if scent.get("created_at") else None,
                "updated_at": scent["updated_at"].isoformat() if scent.get("updated_at") else None
            }
            scent_list.append(scent_data)

        return scent_list

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve scents for table: {str(e)}"
        )


@router.get("/", response_model=List[ScentResponse])
async def get_scents(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None),
    active_only: bool = Query(True),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get all scents with optional filtering"""
    try:
        db = await get_database()
        
        # Build query
        query = {}
        if active_only:
            query["is_active"] = True
        
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
                {"scent_family": {"$regex": search, "$options": "i"}},
                {"top_notes": {"$regex": search, "$options": "i"}},
                {"middle_notes": {"$regex": search, "$options": "i"}},
                {"base_notes": {"$regex": search, "$options": "i"}}
            ]
        
        # Get scents
        cursor = db.scents.find(query).skip(skip).limit(limit).sort("name", 1)
        scents = await cursor.to_list(length=limit)
        
        # Format response with product counts
        scent_list = []
        for scent in scents:
            scent_id = scent["_id"]

            # Count products using this specific scent
            # Handle both ObjectId and string formats to be safe
            scent_obj_id = scent_id  # This is already an ObjectId from the database
            scent_str_id = str(scent_id)  # Convert to string as well

            query = {
                "is_active": True,
                "$or": [
                    {"scent_ids": scent_obj_id},    # New format: ObjectId in array
                    {"scent_ids": scent_str_id},    # New format: string in array (just in case)
                    {"scent_id": scent_obj_id},     # Legacy format: single ObjectId
                    {"scent_id": scent_str_id}      # Legacy format: single string (just in case)
                ]
            }

            product_count = await db.products.count_documents(query)

            scent_data = {
                "id": str(scent["_id"]),
                "name": scent["name"],
                "description": scent.get("description"),
                "scent_family": scent.get("scent_family"),
                "top_notes": scent.get("top_notes"),
                "middle_notes": scent.get("middle_notes"),
                "base_notes": scent.get("base_notes"),
                "longevity": scent.get("longevity"),
                "sillage": scent.get("sillage"),
                "season": scent.get("season"),
                "occasion": scent.get("occasion"),
                "gender": scent.get("gender"),
                "is_active": scent.get("is_active", True),
                "product_count": product_count,  # Add product count
                "created_at": scent["created_at"].isoformat() if scent.get("created_at") else None,
                "updated_at": scent["updated_at"].isoformat() if scent.get("updated_at") else None
            }
            scent_list.append(scent_data)
        
        return scent_list
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve scents: {str(e)}"
        )


@router.get("/{scent_id}", response_model=ScentResponse)
async def get_scent(
    scent_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get a single scent by ID"""
    try:
        db = await get_database()
        
        # Validate scent ID
        if not ObjectId.is_valid(scent_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid scent ID"
            )
        
        # Get scent
        scent = await db.scents.find_one({"_id": ObjectId(scent_id)})
        if not scent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scent not found"
            )
        
        scent_data = {
            "id": str(scent["_id"]),
            "name": scent["name"],
            "description": scent.get("description"),
            "scent_family": scent.get("scent_family"),
            "top_notes": scent.get("top_notes"),
            "middle_notes": scent.get("middle_notes"),
            "base_notes": scent.get("base_notes"),
            "longevity": scent.get("longevity"),
            "sillage": scent.get("sillage"),
            "season": scent.get("season"),
            "occasion": scent.get("occasion"),
            "gender": scent.get("gender"),
            "is_active": scent.get("is_active", True),
            "created_at": scent["created_at"].isoformat() if scent.get("created_at") else None,
            "updated_at": scent["updated_at"].isoformat() if scent.get("updated_at") else None
        }
        
        return scent_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve scent: {str(e)}"
        )


@router.post("/", response_model=dict)
async def create_scent(
    scent_data: ScentCreate,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create a new scent"""
    try:
        db = await get_database()

        # Check if scent name already exists
        existing_scent = await db.scents.find_one({"name": {"$regex": f"^{scent_data.name}$", "$options": "i"}})
        if existing_scent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A scent with this name already exists"
            )

        # Create scent document
        scent_doc = {
            "name": scent_data.name,
            "description": scent_data.description,
            "scent_family": scent_data.scent_family,
            "top_notes": scent_data.top_notes,
            "middle_notes": scent_data.middle_notes,
            "base_notes": scent_data.base_notes,
            "longevity": scent_data.longevity,
            "sillage": scent_data.sillage,
            "season": scent_data.season,
            "occasion": scent_data.occasion,
            "gender": scent_data.gender,
            "is_active": True,
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": None
        }

        # Insert scent
        result = await db.scents.insert_one(scent_doc)

        return {
            "success": True,
            "message": "Scent created successfully",
            "scent_id": str(result.inserted_id)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scent: {str(e)}"
        )


@router.put("/{scent_id}", response_model=dict)
async def update_scent(
    scent_id: str,
    scent_data: ScentUpdate,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Update a scent"""
    try:
        db = await get_database()

        # Validate scent ID
        if not ObjectId.is_valid(scent_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid scent ID"
            )

        # Check if scent exists
        existing_scent = await db.scents.find_one({"_id": ObjectId(scent_id)})
        if not existing_scent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scent not found"
            )

        # Check if new name conflicts with existing scent
        if scent_data.name:
            name_conflict = await db.scents.find_one({
                "name": {"$regex": f"^{scent_data.name}$", "$options": "i"},
                "_id": {"$ne": ObjectId(scent_id)}
            })
            if name_conflict:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A scent with this name already exists"
                )

        # Build update document
        update_doc = {"updated_at": kampala_to_utc(now_kampala())}

        # Only update fields that are provided
        for field, value in scent_data.dict(exclude_unset=True).items():
            if value is not None:
                update_doc[field] = value

        # Update scent
        await db.scents.update_one(
            {"_id": ObjectId(scent_id)},
            {"$set": update_doc}
        )

        return {
            "success": True,
            "message": "Scent updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update scent: {str(e)}"
        )


@router.delete("/{scent_id}", response_model=dict)
async def delete_scent(
    scent_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Delete a scent"""
    try:
        db = await get_database()

        # Validate scent ID
        if not ObjectId.is_valid(scent_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid scent ID"
            )

        # Check if scent exists
        existing_scent = await db.scents.find_one({"_id": ObjectId(scent_id)})
        if not existing_scent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scent not found"
            )

        # Check if scent is used by any products
        products_using_scent = await db.products.count_documents({"scent_id": ObjectId(scent_id)})
        if products_using_scent > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete scent. It is currently used by {products_using_scent} product(s). Please remove the scent from all products first."
            )

        # Delete scent
        await db.scents.delete_one({"_id": ObjectId(scent_id)})

        return {
            "success": True,
            "message": "Scent deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete scent: {str(e)}"
        )