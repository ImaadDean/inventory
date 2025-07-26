from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional
from datetime import datetime
from bson import ObjectId
from ...config.database import get_database
from ...schemas.product import (
    CategoryCreate, CategoryUpdate, CategoryResponse,
    ProductCreate, ProductUpdate, ProductResponse, ProductList, StockUpdate
)
from ...models import Product, Category, User
from ...utils.auth import require_admin_or_inventory, get_current_user

router = APIRouter(prefix="/api/products", tags=["Product Management API"])


@router.get("/", response_model=ProductList)
async def get_products(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    category_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    low_stock_only: Optional[bool] = Query(False),
    current_user: User = Depends(get_current_user)
):
    """Get all products with pagination and filtering"""
    db = await get_database()

    # Build filter query
    filter_query = {}
    if search:
        filter_query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"sku": {"$regex": search, "$options": "i"}},
            {"barcode": {"$regex": search, "$options": "i"}},
            {"supplier": {"$regex": search, "$options": "i"}}
        ]
    if category_id and ObjectId.is_valid(category_id):
        filter_query["category_id"] = ObjectId(category_id)
    if is_active is not None:
        filter_query["is_active"] = is_active
    if low_stock_only:
        filter_query["$expr"] = {"$lte": ["$stock_quantity", "$min_stock_level"]}

    # Get total count
    total = await db.products.count_documents(filter_query)

    # Get products with pagination
    skip = (page - 1) * size
    pipeline = [
        {"$match": filter_query},
        {"$lookup": {
            "from": "categories",
            "localField": "category_id",
            "foreignField": "_id",
            "as": "category"
        }},
        {"$skip": skip},
        {"$limit": size},
        {"$sort": {"created_at": -1}}
    ]

    cursor = db.products.aggregate(pipeline)
    products_data = await cursor.to_list(length=size)

    products = []
    for product in products_data:
        category_name = product["category"][0]["name"] if product["category"] else None

        # Calculate profit margin
        profit_margin = None
        if product.get("cost_price") and product["cost_price"] > 0:
            profit_margin = ((product["price"] - product["cost_price"]) / product["cost_price"]) * 100

        products.append(ProductResponse(
            id=str(product["_id"]),
            name=product["name"],
            description=product.get("description"),
            sku=product["sku"],
            barcode=product.get("barcode"),
            category_id=str(product["category_id"]) if product.get("category_id") else None,
            category_name=category_name,
            price=product["price"],
            cost_price=product.get("cost_price"),
            stock_quantity=product["stock_quantity"],
            min_stock_level=product["min_stock_level"],
            max_stock_level=product.get("max_stock_level"),
            unit=product["unit"],
            supplier=product.get("supplier"),
            is_active=product["is_active"],
            is_low_stock=product["stock_quantity"] <= product["min_stock_level"],
            profit_margin=profit_margin,
            created_at=product["created_at"],
            updated_at=product.get("updated_at")
        ))

    return ProductList(
        products=products,
        total=total,
        page=page,
        size=size
    )