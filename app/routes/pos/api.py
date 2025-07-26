from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
from ...config.database import get_database
from ...schemas.pos import (
    SaleCreate, SaleResponse, SaleList, SaleItemResponse, ProductSearch
)
from ...models import Sale, SaleItem, User
from ...utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/api/pos", tags=["Point of Sale API"])


@router.get("/products/search", response_model=List[ProductSearch])
async def search_products(
    query: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user)
):
    """Search products for POS (by name, SKU, or barcode)"""
    db = await get_database()

    # Build search query
    search_query = {
        "$and": [
            {"is_active": True},
            {"stock_quantity": {"$gt": 0}},  # Only show products in stock
            {"$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"sku": {"$regex": query, "$options": "i"}},
                {"barcode": {"$regex": query, "$options": "i"}}
            ]}
        ]
    }

    cursor = db.products.find(search_query).limit(limit)
    products_data = await cursor.to_list(length=limit)

    products = [
        ProductSearch(
            id=str(product["_id"]),
            name=product["name"],
            sku=product["sku"],
            barcode=product.get("barcode"),
            price=product["price"],
            stock_quantity=product["stock_quantity"],
            unit=product["unit"]
        )
        for product in products_data
    ]

    return products


@router.get("/sales", response_model=SaleList)
async def get_sales(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """Get all sales with pagination and filtering"""
    db = await get_database()

    # Build filter query
    filter_query = {}
    if search:
        filter_query["$or"] = [
            {"sale_number": {"$regex": search, "$options": "i"}},
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"cashier_name": {"$regex": search, "$options": "i"}}
        ]

    # Get total count
    total = await db.sales.count_documents(filter_query)

    # Get sales with pagination
    skip = (page - 1) * size
    cursor = db.sales.find(filter_query).skip(skip).limit(size).sort("created_at", -1)
    sales_data = await cursor.to_list(length=size)

    sales = []
    for sale in sales_data:
        sale_items_response = [
            SaleItemResponse(
                product_id=str(item["product_id"]),
                product_name=item["product_name"],
                sku=item["sku"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                total_price=item["total_price"],
                discount_amount=item["discount_amount"]
            )
            for item in sale["items"]
        ]

        sales.append(SaleResponse(
            id=str(sale["_id"]),
            sale_number=sale["sale_number"],
            customer_id=str(sale["customer_id"]) if sale.get("customer_id") else None,
            customer_name=sale.get("customer_name"),
            cashier_id=str(sale["cashier_id"]),
            cashier_name=sale["cashier_name"],
            items=sale_items_response,
            subtotal=sale["subtotal"],
            tax_amount=sale["tax_amount"],
            discount_amount=sale["discount_amount"],
            total_amount=sale["total_amount"],
            payment_method=sale["payment_method"],
            payment_received=sale["payment_received"],
            change_given=sale["change_given"],
            status=sale["status"],
            notes=sale.get("notes"),
            created_at=sale["created_at"],
            updated_at=sale.get("updated_at")
        ))

    return SaleList(
        sales=sales,
        total=total,
        page=page,
        size=size
    )