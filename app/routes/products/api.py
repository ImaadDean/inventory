from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from typing import Optional
from datetime import datetime
from bson import ObjectId
from ...config.database import get_database
from ...schemas.product import (
    CategoryCreate, CategoryUpdate, CategoryResponse,
    ProductCreate, ProductUpdate, ProductResponse, ProductList, StockUpdate
)
from ...models import Product, Category, User
from ...utils.auth import require_admin_or_inventory, get_current_user, verify_token, get_user_by_username
from ...utils.expense_categories_init import create_restocking_expense

router = APIRouter(prefix="/api/products", tags=["Product Management API"])


async def get_current_user_hybrid(request: Request) -> User:
    """Get current user from either JWT token or cookie"""

    # Try cookie authentication first (for web interface)
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            # Handle Bearer prefix in cookie value
            token = access_token
            if access_token.startswith("Bearer "):
                token = access_token[7:]  # Remove "Bearer " prefix

            payload = verify_token(token)
            if payload:
                username = payload.get("sub")
                if username:
                    user = await get_user_by_username(username)
                    if user and user.is_active:
                        return user
        except Exception as e:
            print(f"Cookie auth failed: {e}")

    # Try JWT token authentication (for API clients)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            payload = verify_token(token)
            if payload:
                username = payload.get("sub")
                if username:
                    user = await get_user_by_username(username)
                    if user and user.is_active:
                        return user
        except Exception as e:
            print(f"JWT auth failed: {e}")

    # If both methods fail, raise authentication error
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/stats", response_model=dict)
async def get_product_stats():
    """Get product statistics for dashboard cards"""
    db = await get_database()

    # Get total products count
    total_products = await db.products.count_documents({"is_active": True})

    # Get in stock products (stock > 0)
    in_stock = await db.products.count_documents({
        "is_active": True,
        "stock_quantity": {"$gt": 0}
    })

    # Get low stock products using proper MongoDB query
    low_stock = await db.products.count_documents({
        "is_active": True,
        "stock_quantity": {"$gt": 0},
        "$expr": {"$lte": ["$stock_quantity", {"$ifNull": ["$min_stock_level", 10]}]}
    })

    # Get out of stock products (stock = 0)
    out_of_stock = await db.products.count_documents({
        "is_active": True,
        "stock_quantity": 0
    })

    return {
        "total_products": total_products,
        "in_stock": in_stock,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock
    }


@router.get("/suppliers/dropdown", response_model=dict)
async def get_suppliers_dropdown():
    """Get simple list of active suppliers for dropdowns - no auth required"""
    try:
        db = await get_database()
        suppliers_collection = db.suppliers

        # Get all suppliers first to see what we have
        all_suppliers = await suppliers_collection.find({}).to_list(length=None)

        # If no suppliers exist, return empty list
        if not all_suppliers:
            return {
                "suppliers": [],
                "total": 0
            }

        # Get only active suppliers with basic info
        cursor = suppliers_collection.find(
            {"is_active": True}
        ).sort("name", 1)

        suppliers = await cursor.to_list(length=None)

        # Format for dropdown
        suppliers_list = []
        for supplier in suppliers:
            suppliers_list.append({
                "id": str(supplier["_id"]),
                "name": supplier.get("name", "Unknown Supplier")
            })

        return {
            "suppliers": suppliers_list,
            "total": len(suppliers_list)
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch suppliers: {str(e)}"
        )


async def update_supplier_on_restock(db, supplier_name: str, product_id: str, product_name: str, product_sku: str):
    """Update supplier information when a product is restocked"""
    try:
        suppliers_collection = db.suppliers

        # Find the supplier by name (case-insensitive)
        supplier = await suppliers_collection.find_one({
            "name": {"$regex": f"^{supplier_name}$", "$options": "i"}
        })

        if not supplier:
            # If supplier doesn't exist, create a basic supplier record
            supplier_doc = {
                "name": supplier_name,
                "contact_person": None,
                "phone": None,
                "email": None,
                "address": None,
                "notes": f"Auto-created from product restocking",
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "created_by": "system",
                "products": [product_id],
                "last_order_date": datetime.utcnow(),
                "total_orders": 1
            }

            result = await suppliers_collection.insert_one(supplier_doc)
            if result.inserted_id:
                print(f"Created new supplier: {supplier_name}")
        else:
            # Update existing supplier
            supplier_id = supplier["_id"]
            current_products = supplier.get("products", [])

            # Add product to supplier's product list if not already there
            if product_id not in current_products:
                current_products.append(product_id)

            # Update supplier with new product and last order date
            update_doc = {
                "products": current_products,
                "last_order_date": datetime.utcnow(),
                "total_orders": supplier.get("total_orders", 0) + 1,
                "updated_at": datetime.utcnow()
            }

            await suppliers_collection.update_one(
                {"_id": supplier_id},
                {"$set": update_doc}
            )

            print(f"Updated supplier {supplier_name} with product {product_name}")

    except Exception as e:
        print(f"Error updating supplier on restock: {e}")
        # Don't raise exception as this is supplementary functionality


@router.get("/{product_id}", response_model=dict)
async def get_product_by_id(product_id: str):
    """Get a single product by ID"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Find the product with category information
        pipeline = [
            {"$match": {"_id": ObjectId(product_id)}},
            {"$lookup": {
                "from": "categories",
                "localField": "category_id",
                "foreignField": "_id",
                "as": "category"
            }}
        ]

        cursor = db.products.aggregate(pipeline)
        products_data = await cursor.to_list(length=1)

        if not products_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        product = products_data[0]
        category_name = product["category"][0]["name"] if product["category"] else "No Category"

        # Calculate profit margin
        profit_margin = None
        if product.get("cost_price") and product["cost_price"] > 0:
            profit_margin = ((product["price"] - product["cost_price"]) / product["cost_price"]) * 100

        # Determine stock status
        min_stock_level = product.get("min_stock_level", 10)
        is_low_stock = product["stock_quantity"] <= min_stock_level and product["stock_quantity"] > 0
        stock_status = "out-of-stock" if product["stock_quantity"] == 0 else ("low-stock" if is_low_stock else "in-stock")

        return {
            "id": str(product["_id"]),
            "name": product["name"],
            "description": product.get("description", ""),
            "sku": product["sku"],
            "barcode": product.get("barcode", ""),
            "category_id": str(product["category_id"]) if product.get("category_id") else None,
            "category_name": category_name,
            "price": product["price"],
            "cost_price": product.get("cost_price"),
            "stock_quantity": product["stock_quantity"],
            "min_stock_level": product["min_stock_level"],
            "max_stock_level": product.get("max_stock_level"),
            "unit": product["unit"],
            "supplier": product.get("supplier", ""),
            "location": product.get("location", ""),
            "is_active": product["is_active"],
            "is_low_stock": is_low_stock,
            "stock_status": stock_status,
            "profit_margin": profit_margin,
            "created_at": product["created_at"],
            "updated_at": product.get("updated_at")
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get product: {str(e)}"
        )




@router.get("/auth-test", response_model=dict)
async def test_authentication(request: Request, current_user: User = Depends(get_current_user_hybrid)):
    """Test endpoint to verify authentication is working"""
    return {
        "authenticated": True,
        "user": {
            "username": current_user.username,
            "email": current_user.email,
            "role": current_user.role,
            "is_active": current_user.is_active
        },
        "message": "Authentication successful!"
    }


@router.get("/", response_model=dict)
async def get_products(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    category_id: Optional[str] = Query(None),
    stock_status: Optional[str] = Query(None),  # "in-stock", "low-stock", "out-of-stock"
    is_active: Optional[bool] = Query(None),
    low_stock_only: Optional[bool] = Query(False),
    supplier: Optional[str] = Query(None)  # Filter by supplier name
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
    if supplier:
        # Filter by supplier name (case-insensitive)
        filter_query["supplier"] = {"$regex": f"^{supplier}$", "$options": "i"}

    # Handle stock status filtering
    if stock_status == "in-stock":
        # Products with stock > min_stock_level
        filter_query["stock_quantity"] = {"$gt": 0}
        filter_query["$expr"] = {"$gt": ["$stock_quantity", {"$ifNull": ["$min_stock_level", 10]}]}
    elif stock_status == "low-stock":
        # Products with 0 < stock <= min_stock_level
        filter_query["stock_quantity"] = {"$gt": 0}
        filter_query["$expr"] = {"$lte": ["$stock_quantity", {"$ifNull": ["$min_stock_level", 10]}]}
    elif stock_status == "out-of-stock":
        filter_query["stock_quantity"] = 0

    # Legacy support for low_stock_only parameter
    if low_stock_only:
        filter_query["stock_quantity"] = {"$gt": 0}
        filter_query["$expr"] = {"$lte": ["$stock_quantity", {"$ifNull": ["$min_stock_level", 10]}]}

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
        category_name = product["category"][0]["name"] if product["category"] else "No Category"

        # Calculate profit margin
        profit_margin = None
        if product.get("cost_price") and product["cost_price"] > 0:
            profit_margin = ((product["price"] - product["cost_price"]) / product["cost_price"]) * 100

        # Determine stock status (Low stock if below min_stock_level)
        min_stock_level = product.get("min_stock_level", 10)  # Default to 10 if not set
        is_low_stock = product["stock_quantity"] <= min_stock_level and product["stock_quantity"] > 0
        stock_status = "out-of-stock" if product["stock_quantity"] == 0 else ("low-stock" if is_low_stock else "in-stock")

        products.append({
            "id": str(product["_id"]),
            "name": product["name"],
            "description": product.get("description", ""),
            "sku": product["sku"],
            "barcode": product.get("barcode", ""),
            "category_id": str(product["category_id"]) if product.get("category_id") else None,
            "category_name": category_name,
            "price": product["price"],
            "cost_price": product.get("cost_price"),
            "stock_quantity": product["stock_quantity"],
            "min_stock_level": product["min_stock_level"],
            "max_stock_level": product.get("max_stock_level"),
            "unit": product["unit"],
            "supplier": product.get("supplier", ""),
            "location": product.get("location", ""),
            "is_active": product["is_active"],
            "is_low_stock": is_low_stock,
            "stock_status": stock_status,
            "profit_margin": profit_margin,
            "created_at": product["created_at"].isoformat(),
            "updated_at": product.get("updated_at", product["created_at"]).isoformat(),
            "created_by": str(product.get("created_by", ""))
        })

    return {
        "products": products,
        "total": total,
        "page": page,
        "size": size,
        "total_pages": (total + size - 1) // size
    }


@router.post("/{product_id}/restock", response_model=dict)
async def restock_product(
    product_id: str,
    stock_update: StockUpdate,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid)
):
    """Restock a product by adding quantity"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Find the product
        product = await db.products.find_one({"_id": ObjectId(product_id)})
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Validate quantity (must be positive for restocking)
        if stock_update.quantity <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Restock quantity must be positive"
            )

        # Calculate new stock quantity
        current_stock = product.get("stock_quantity", 0)
        new_stock = current_stock + stock_update.quantity

        # Update the product
        update_data = {
            "stock_quantity": new_stock,
            "updated_at": datetime.utcnow(),
            "last_restocked": datetime.utcnow()
        }

        result = await db.products.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update product stock"
            )

        # Log the restock activity (optional - you can create a stock_history collection)
        restock_log = {
            "product_id": ObjectId(product_id),
            "product_name": product["name"],
            "product_sku": product["sku"],
            "quantity_added": stock_update.quantity,
            "previous_stock": current_stock,
            "new_stock": new_stock,
            "reason": stock_update.reason or "Manual restock",
            "restocked_by": current_user.id,
            "restocked_by_username": current_user.username,
            "restocked_at": datetime.utcnow()
        }

        # Insert restock log (create collection if it doesn't exist)
        await db.restock_history.insert_one(restock_log)

        # Update supplier information if supplier is provided
        if stock_update.supplier_name:
            await update_supplier_on_restock(
                db=db,
                supplier_name=stock_update.supplier_name,
                product_id=product_id,
                product_name=product["name"],
                product_sku=product["sku"]
            )

        # Create automatic expense if cost information is provided
        expense_id = None
        if stock_update.unit_cost and stock_update.unit_cost > 0:
            total_cost = stock_update.unit_cost * stock_update.quantity
            expense_id = await create_restocking_expense(
                db=db,
                product_name=product["name"],
                quantity=stock_update.quantity,
                unit_cost=stock_update.unit_cost,
                total_cost=total_cost,
                supplier_name=stock_update.supplier_name,
                user_username=current_user.username,
                payment_method=stock_update.payment_method
            )

        response_data = {
            "success": True,
            "message": f"Successfully restocked {product['name']}",
            "product_id": product_id,
            "product_name": product["name"],
            "quantity_added": stock_update.quantity,
            "previous_stock": current_stock,
            "new_stock": new_stock,
            "reason": stock_update.reason or "Manual restock"
        }

        # Add expense information if created
        if expense_id:
            total_cost = stock_update.unit_cost * stock_update.quantity
            response_data["expense_created"] = {
                "expense_id": expense_id,
                "total_cost": total_cost,
                "message": f"Automatic expense created for UGX {total_cost:,.2f}"
            }

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restock product: {str(e)}"
        )


@router.get("/{product_id}", response_model=dict)
async def get_product(
    product_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid)
):
    """Get a single product by ID"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Get product
        product = await db.products.find_one({"_id": ObjectId(product_id)})
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Get category name
        category_name = "Uncategorized"
        if product.get("category_id"):
            category = await db.categories.find_one({"_id": product["category_id"]})
            if category:
                category_name = category["name"]

        return {
            "id": str(product["_id"]),
            "name": product["name"],
            "description": product.get("description", ""),
            "sku": product.get("sku", ""),
            "price": float(product["price"]),
            "cost": float(product.get("cost", 0)),
            "stock_quantity": product["stock_quantity"],
            "min_stock_level": product.get("min_stock_level", 0),
            "category_id": str(product["category_id"]) if product.get("category_id") else None,
            "category_name": category_name,
            "is_active": product.get("is_active", True),
            "created_at": product["created_at"].isoformat() if product.get("created_at") else None,
            "updated_at": product["updated_at"].isoformat() if product.get("updated_at") else None
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve product: {str(e)}"
        )


@router.put("/{product_id}", response_model=dict)
async def update_product(
    product_id: str,
    product_data: ProductUpdate,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid)
):
    """Update a product"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Check if product exists
        existing_product = await db.products.find_one({"_id": ObjectId(product_id)})
        if not existing_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Build update document with only provided fields
        update_doc = {"updated_at": datetime.utcnow()}

        # Handle each field that can be updated
        if product_data.name is not None:
            update_doc["name"] = product_data.name.strip()

        if product_data.description is not None:
            update_doc["description"] = product_data.description.strip() if product_data.description else None

        if product_data.barcode is not None:
            update_doc["barcode"] = product_data.barcode.strip() if product_data.barcode else None

        if product_data.category_id is not None:
            # Validate category exists
            try:
                category_object_id = ObjectId(product_data.category_id)
                category = await db.categories.find_one({"_id": category_object_id})
                if not category:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Selected category not found"
                    )
                update_doc["category_id"] = category_object_id
                update_doc["category_name"] = category["name"]
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid category selected"
                )

        if product_data.price is not None:
            update_doc["price"] = float(product_data.price)

        if product_data.cost_price is not None:
            update_doc["cost_price"] = float(product_data.cost_price) if product_data.cost_price > 0 else None

        if product_data.stock_quantity is not None:
            update_doc["stock_quantity"] = product_data.stock_quantity

        if product_data.min_stock_level is not None:
            update_doc["min_stock_level"] = product_data.min_stock_level

        if product_data.max_stock_level is not None:
            update_doc["max_stock_level"] = product_data.max_stock_level if product_data.max_stock_level > 0 else None

        if product_data.unit is not None:
            update_doc["unit"] = product_data.unit.strip() if product_data.unit else "pcs"

        if product_data.supplier is not None:
            update_doc["supplier"] = product_data.supplier.strip() if product_data.supplier else None

        if product_data.is_active is not None:
            update_doc["is_active"] = product_data.is_active

        # Update the product
        result = await db.products.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": update_doc}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update product"
            )

        return {
            "success": True,
            "message": "Product updated successfully",
            "product_id": product_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update product: {str(e)}"
        )


@router.delete("/{product_id}", response_model=dict)
async def delete_product(
    product_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_hybrid)
):
    """Delete a product"""
    try:
        db = await get_database()

        # Validate product ID
        if not ObjectId.is_valid(product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product ID"
            )

        # Check if product exists
        product = await db.products.find_one({"_id": ObjectId(product_id)})
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Check if product is used in any orders (optional safety check)
        orders_with_product = await db.orders.count_documents({
            "items.product_id": ObjectId(product_id)
        })

        if orders_with_product > 0:
            # Instead of preventing deletion, we could mark as inactive
            # For now, let's allow deletion but warn about it
            pass

        # Delete the product
        result = await db.products.delete_one({"_id": ObjectId(product_id)})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete product"
            )

        # Also delete any restock history for this product
        await db.restock_history.delete_many({"product_id": ObjectId(product_id)})

        return {
            "success": True,
            "message": f"Product '{product['name']}' deleted successfully",
            "deleted_product": {
                "id": product_id,
                "name": product["name"],
                "sku": product.get("sku", ""),
                "orders_affected": orders_with_product
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete product: {str(e)}"
        )