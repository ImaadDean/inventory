from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from app.utils.auth import get_current_user_hybrid_dependency
from app.models.user import User
from app.config.database import get_database
from app.utils.timezone import now_kampala, kampala_to_utc
from bson import ObjectId
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/api/product-requests/", response_model=dict)
async def get_product_requests(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get product requests with pagination and filtering"""
    try:
        db = await get_database()
        requests_collection = db.product_requests
        
        query = {}
        
        if search:
            query["$or"] = [
                {"product_name": {"$regex": search, "$options": "i"}},
                {"customer_name": {"$regex": search, "$options": "i"}},
                {"notes": {"$regex": search, "$options": "i"}}
            ]
        
        if status:
            query["status"] = status
            
        total = await requests_collection.count_documents(query)
        
        skip = (page - 1) * size
        cursor = requests_collection.find(query).skip(skip).limit(size).sort("created_at", -1)
        requests = await cursor.to_list(length=size)
        
        for request in requests:
            request["id"] = str(request["_id"])
            del request["_id"]
            
        return {
            "requests": requests,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size
        }
        
    except Exception as e:
        logger.error(f"Error fetching product requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch product requests")

@router.post("/api/product-requests/", response_model=dict)
async def create_product_request(
    request_data: dict,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create a new product request"""
    try:
        db = await get_database()
        requests_collection = db.product_requests
        
        request_doc = {
            "product_name": request_data.get("product_name"),
            "customer_name": request_data.get("customer_name"),
            "customer_contact": request_data.get("customer_contact"),
            "quantity": request_data.get("quantity", 1),
            "notes": request_data.get("notes"),
            "status": "pending",
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": kampala_to_utc(now_kampala()),
            "created_by": user.username
        }
        
        result = await requests_collection.insert_one(request_doc)
        
        if result.inserted_id:
            return {
                "message": "Product request created successfully",
                "request_id": str(result.inserted_id)
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create product request")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating product request: {e}")
        raise HTTPException(status_code=500, detail="Failed to create product request")

@router.get("/api/product-requests/{request_id}", response_model=dict)
async def get_product_request(
    request_id: str,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get a specific product request by ID"""
    try:
        db = await get_database()
        requests_collection = db.product_requests
        
        request = await requests_collection.find_one({"_id": ObjectId(request_id)})
        
        if not request:
            raise HTTPException(status_code=404, detail="Product request not found")
        
        request["id"] = str(request["_id"])
        del request["_id"]
        
        return request
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching product request: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch product request")

@router.put("/api/product-requests/{request_id}", response_model=dict)
async def update_product_request(
    request_id: str,
    request_data: dict,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Update a product request"""
    try:
        db = await get_database()
        requests_collection = db.product_requests
        
        existing = await requests_collection.find_one({"_id": ObjectId(request_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Product request not found")
        
        update_doc = {
            "updated_at": kampala_to_utc(now_kampala()),
            "updated_by": user.username
        }
        
        for key, value in request_data.items():
            if key not in ["id", "_id"]:
                update_doc[key] = value
        
        result = await requests_collection.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": update_doc}
        )
        
        if result.modified_count > 0:
            return {"message": "Product request updated successfully"}
        else:
            return {"message": "No changes made to product request"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating product request: {e}")
        raise HTTPException(status_code=500, detail="Failed to update product request")

@router.delete("/api/product-requests/{request_id}", response_model=dict)
async def delete_product_request(
    request_id: str,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Delete a product request"""
    try:
        db = await get_database()
        requests_collection = db.product_requests
        
        existing = await requests_collection.find_one({"_id": ObjectId(request_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Product request not found")
        
        result = await requests_collection.delete_one({"_id": ObjectId(request_id)})
        
        if result.deleted_count > 0:
            return {"message": "Product request deleted successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete product request")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting product request: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete product request")
