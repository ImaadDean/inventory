from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from typing import Optional, List
from bson import ObjectId
from ...config.database import get_database
from ...schemas.product_request import ProductRequestCreate, ProductRequestUpdate, ProductRequestResponse, ProductRequestListResponse
from ...models.product_request import ProductRequest, ProductRequestStatus
from ...models.user import User
from ...utils.auth import get_current_user_hybrid_dependency
from ...utils.timezone import now_kampala, kampala_to_utc

router = APIRouter(prefix="/api/product-requests", tags=["Product Request Management API"])

@router.post("/", response_model=ProductRequestResponse)
async def create_product_request(
    request_data: ProductRequestCreate,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create a new product request"""
    db = await get_database()

    request_doc = {
        "product_name": request_data.product_name,
        "customer_name": request_data.customer_name,
        "customer_contact": request_data.customer_contact,
        "status": ProductRequestStatus.PENDING,
        "notes": request_data.notes,
        "created_at": kampala_to_utc(now_kampala()),
        "created_by": current_user.id
    }

    result = await db.product_requests.insert_one(request_doc)

    if not result.inserted_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product request"
        )

    created_request = await db.product_requests.find_one({"_id": result.inserted_id})

    if created_request:
        created_request["id"] = str(created_request["_id"])

    return ProductRequestResponse.model_validate(created_request)

@router.get("/", response_model=ProductRequestListResponse)
async def get_product_requests(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100)
):
    """Get a paginated list of product requests"""
    db = await get_database()
    
    skip = (page - 1) * size
    
    total_requests = await db.product_requests.count_documents({})
    total_pages = (total_requests + size - 1) // size

    pipeline = [
        {"$skip": skip},
        {"$limit": size},
        {"$lookup": {
            "from": "users",
            "localField": "created_by",
            "foreignField": "_id",
            "as": "creator_info"
        }},
        {"$addFields": {
            "created_by_username": {"$arrayElemAt": ["$creator_info.username", 0]},
            "id": {"$toString": "$_id"},
            "created_by": {"$toString": "$created_by"}
        }},
        {"$project": {
            "creator_info": 0,
            "_id": 0
        }}
    ]

    requests_data = await db.product_requests.aggregate(pipeline).to_list(length=None)

    processed_requests = []
    for req in requests_data:
        # Ensure created_by is a string
        if "created_by" in req and isinstance(req["created_by"], ObjectId):
            req["created_by"] = str(req["created_by"])
        # Ensure id is a string (already handled by aggregation, but for safety)
        if "_id" in req and "id" not in req:
            req["id"] = str(req["_id"])
        processed_requests.append(req)
    
    return {
        "total": total_requests,
        "pages": total_pages,
        "page": page,
        "items": [ProductRequestResponse.model_validate(req) for req in processed_requests]
    }

@router.get("/{request_id}", response_model=ProductRequestResponse)
async def get_product_request(
    request_id: str,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get a single product request by ID"""
    db = await get_database()

    if not ObjectId.is_valid(request_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request ID"
        )

    pipeline = [
        {"$match": {"_id": ObjectId(request_id)}},
        {"$lookup": {
            "from": "users",
            "localField": "created_by",
            "foreignField": "_id",
            "as": "creator_info"
        }},
        {"$addFields": {
            "created_by_username": {"$arrayElemAt": ["$creator_info.username", 0]},
            "id": {"$toString": "$_id"},
            "created_by": {"$toString": "$created_by"}
        }},
        {"$project": {
            "creator_info": 0,
            "_id": 0
        }}
    ]

    request_data = await db.product_requests.aggregate(pipeline).to_list(length=1)

    if not request_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product request not found"
        )

    # The aggregation pipeline already ensures 'id' and 'created_by' are strings
    return ProductRequestResponse.model_validate(request_data[0])