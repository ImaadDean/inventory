from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
from ...config.database import get_database
from ...schemas.pos import (
    SaleCreate, SaleResponse, SaleList, SaleItemResponse, ProductSearch
)
from ...schemas.customer import CustomerCreate, CustomerResponse
from ...models import Sale, SaleItem, User, OrderPaymentStatus
from ...utils.auth import get_current_user, get_current_user_hybrid_dependency, verify_token, get_user_by_username
from ...utils.timezone import now_kampala, kampala_to_utc
from ...utils.decant_handler import process_decant_sale, calculate_decant_availability
import uuid

router = APIRouter(prefix="/api/pos", tags=["Point of Sale API"])


# Debug endpoints for troubleshooting
@router.get("/debug/test-connection")
async def test_pos_connection():
    """Test POS API connection and database access"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        db = await get_database()
        
        # Test basic database operations
        products_count = await db.products.count_documents({"is_active": True})
        customers_count = await db.customers.count_documents({"is_active": True})
        
        # Test product search
        sample_products = await db.products.find({"is_active": True, "stock_quantity": {"$gt": 0}}).limit(3).to_list(3)
        
        return {
            "status": "success",
            "database_connected": True,
            "active_products_count": products_count,
            "active_customers_count": customers_count,
            "sample_products": [
                {
                    "id": str(p["_id"]),
                    "name": p["name"],
                    "stock": p["stock_quantity"],
                    "price": p["price"]
                } for p in sample_products
            ],
            "message": "POS API is working correctly"
        }
    except Exception as e:
        logger.error(f"POS debug test failed: {str(e)}")
        return {
            "status": "error",
            "database_connected": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


@router.get("/debug/search-test")
async def test_search_endpoints(
    query: str = Query("test", min_length=1)
):
    """Test search functionality without authentication"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        db = await get_database()
        
        # Test product search
        product_search_query = {
            "$and": [
                {"is_active": True},
                {"stock_quantity": {"$gt": 0}},
                {"$or": [
                    {"name": {"$regex": query, "$options": "i"}},
                    {"barcode": {"$regex": query, "$options": "i"}}
                ]}
            ]
        }
        
        products = await db.products.find(product_search_query).limit(5).to_list(5)
        
        # Test customer search
        customer_search_query = {
            "$and": [
                {"is_active": True},
                {"$or": [
                    {"name": {"$regex": query, "$options": "i"}},
                    {"phone": {"$regex": query, "$options": "i"}}
                ]}
            ]
        }
        
        customers = await db.customers.find(customer_search_query).limit(5).to_list(5)
        
        return {
            "status": "success",
            "query": query,
            "products_found": len(products),
            "customers_found": len(customers),
            "products": [
                {
                    "id": str(p["_id"]),
                    "name": p["name"],
                    "stock": p["stock_quantity"],
                    "price": p["price"]
                } for p in products
            ],
            "customers": [
                {
                    "id": str(c["_id"]),
                    "name": c["name"],
                    "phone": c.get("phone", "")
                } for c in customers
            ]
        }
    except Exception as e:
        logger.error(f"POS search test failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }


@router.get("/products/search")
async def search_products(
    query: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Search products for POS (by name or barcode)"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"POS product search: query='{query}', limit={limit}, user={current_user.username if current_user else 'anonymous'}")
        db = await get_database()

        # Build search query
        search_query = {
            "$and": [
                {"is_active": True},
                {"stock_quantity": {"$gt": 0}},  # Only show products in stock
                {"$or": [
                    {"name": {"$regex": query, "$options": "i"}},
                    {"barcode": {"$regex": query, "$options": "i"}}
                ]}
            ]
        }

        logger.debug(f"MongoDB query: {search_query}")
        cursor = db.products.find(search_query).limit(limit)
        products_data = await cursor.to_list(length=limit)
        logger.info(f"Found {len(products_data)} products matching query")

        products = []
        for product in products_data:
            try:
                # Calculate decant availability
                decant_info = calculate_decant_availability(product)

                product_data = {
                    "id": str(product["_id"]),
                    "name": product["name"],
                    "barcode": product.get("barcode", ""),
                    "price": product["price"],
                    "stock_quantity": product["stock_quantity"],
                    "unit": product.get("unit", "pcs"),
                    "bottle_size_ml": product.get("bottle_size_ml"),
                    "decant": product.get("decant"),
                    "is_perfume_with_decants": decant_info["is_decantable"],
                    "available_decants": decant_info["available_decants"],
                    "opened_bottle_decants": decant_info.get("opened_bottle_decants", 0),
                    "has_opened_bottle": decant_info.get("has_opened_bottle", False),
                    "can_open_new_bottle": decant_info.get("can_open_new_bottle", False),
                    "opened_bottle_ml_left": decant_info.get("opened_bottle_ml_left", 0),
                    "stock_display": f"{product['stock_quantity']} pcs & {decant_info['opened_bottle_ml_left']}mls" if decant_info["is_decantable"] else f"{product['stock_quantity']} {product.get('unit', 'pcs')}"
                }

                products.append(product_data)
            except Exception as e:
                # Log the error but continue with other products
                logger.warning(f"Error processing product {product.get('name', 'unknown')}: {str(e)}")
                # Still add basic product info even if decant calculation fails
                try:
                    product_data = {
                        "id": str(product["_id"]),
                        "name": product["name"],
                        "barcode": product.get("barcode", ""),
                        "price": product["price"],
                        "stock_quantity": product["stock_quantity"],
                        "unit": product.get("unit", "pcs"),
                        "bottle_size_ml": product.get("bottle_size_ml"),
                        "decant": product.get("decant"),
                        "is_perfume_with_decants": False,
                        "available_decants": 0,
                        "opened_bottle_decants": 0,
                        "has_opened_bottle": False,
                        "can_open_new_bottle": False,
                        "opened_bottle_ml_left": 0,
                        "stock_display": f"{product['stock_quantity']} {product.get('unit', 'pcs')}"
                    }
                    products.append(product_data)
                except Exception as e2:
                    logger.error(f"Failed to create fallback product data: {str(e2)}")
                continue

        logger.info(f"Returning {len(products)} processed products")
        return products

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to search products: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search products: {str(e)}"
        )


@router.get("/customers/search")
async def search_customers(
    query: str = Query(..., min_length=2),
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Search customers for POS"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"POS customer search: query='{query}', limit={limit}, user={current_user.username}")
        db = await get_database()

        search_query = {
            "$and": [
                {"is_active": True},
                {"$or": [
                    {"name": {"$regex": query, "$options": "i"}},
                    {"phone": {"$regex": query, "$options": "i"}}
                ]}
            ]
        }

        logger.debug(f"MongoDB query: {search_query}")
        cursor = db.customers.find(search_query).limit(limit)
        customers_data = await cursor.to_list(length=limit)
        logger.info(f"Found {len(customers_data)} customers matching query")

        customers = [
            {
                "id": str(customer["_id"]),
                "name": customer["name"],
                "phone": customer.get("phone", ""),
                "address": customer.get("address", ""),
                "city": customer.get("city", ""),
                "country": customer.get("country", "")
            }
            for customer in customers_data
        ]

        logger.info(f"Returning {len(customers)} customers")
        return {"customers": customers}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to search customers: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search customers: {str(e)}"
        )


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer_pos(customer_data: CustomerCreate, current_user: User = Depends(get_current_user_hybrid_dependency())):
    """Create a new customer from POS"""
    db = await get_database()

    try:
        # Validate required fields
        if not customer_data.name or not customer_data.name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer name is required"
            )

        if not customer_data.phone or not customer_data.phone.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer phone number is required"
            )



        # Check if customer with same phone already exists
        existing_phone = await db.customers.find_one({"phone": customer_data.phone.strip()})
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer with this phone number already exists"
            )

        # Create customer document
        customer_doc = {
            "name": customer_data.name.strip(),
            "phone": customer_data.phone.strip(),
            "address": customer_data.address.strip() if customer_data.address else None,
            "city": customer_data.city.strip() if customer_data.city else None,
            "country": customer_data.country.strip() if customer_data.country else None,
            "date_of_birth": customer_data.date_of_birth,
            "is_active": True,
            "total_purchases": 0.0,
            "total_orders": 0,
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": kampala_to_utc(now_kampala()),
            "last_purchase_date": None,
            "notes": customer_data.notes.strip() if customer_data.notes else None
        }

        # Insert customer
        result = await db.customers.insert_one(customer_doc)

        # Get the created customer
        created_customer = await db.customers.find_one({"_id": result.inserted_id})

        return CustomerResponse(
            id=str(created_customer["_id"]),
            name=created_customer["name"],
            phone=created_customer.get("phone"),
            address=created_customer.get("address"),
            city=created_customer.get("city"),
            country=created_customer.get("country"),
            date_of_birth=created_customer.get("date_of_birth"),
            is_active=created_customer["is_active"],
            total_purchases=created_customer["total_purchases"],
            total_orders=created_customer["total_orders"],
            created_at=created_customer["created_at"],
            updated_at=created_customer.get("updated_at"),
            last_purchase_date=created_customer.get("last_purchase_date"),
            notes=created_customer.get("notes")
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create customer: {str(e)}"
        )


@router.post("/sales", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
async def create_sale(sale_data: SaleCreate, current_user: User = Depends(get_current_user_hybrid_dependency())):
    """Create a new sale from POS"""
    try:

        db = await get_database()

        # Generate sale number
        sale_count = await db.sales.count_documents({})
        sale_number = f"SALE-{sale_count + 1:06d}"

        # Calculate totals
        subtotal = 0
        sale_items = []

        for item_data in sale_data.items:
            # Get product details
            product = await db.products.find_one({"_id": ObjectId(item_data.product_id)})
            if not product:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product with ID {item_data.product_id} not found"
                )

            # Check stock availability
            if product["stock_quantity"] < item_data.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock for product {product['name']}. Available: {product['stock_quantity']}, Requested: {item_data.quantity}"
                )

            # Calculate item totals
            unit_price = product["price"]
            total_price = unit_price * item_data.quantity
            subtotal += total_price

            sale_items.append({
                "product_id": ObjectId(item_data.product_id),
                "product_name": product["name"],
                "quantity": item_data.quantity,
                "unit_price": unit_price,
                "total_price": total_price,
                "discount_amount": item_data.discount_amount
            })

        # Calculate tax and total
        tax_amount = subtotal * sale_data.tax_rate
        total_amount = subtotal + tax_amount - sale_data.discount_amount

        # Calculate change
        change_given = max(0, sale_data.payment_received - total_amount) if sale_data.payment_method == "cash" else 0

        # Create sale document
        sale_doc = {
            "sale_number": sale_number,
            "customer_id": ObjectId(sale_data.customer_id) if sale_data.customer_id else None,
            "customer_name": sale_data.customer_name,
            "cashier_id": ObjectId(current_user.id),
            "cashier_name": current_user.username,
            "items": sale_items,
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "discount_amount": sale_data.discount_amount,
            "total_amount": total_amount,
            "payment_method": sale_data.payment_method,
            "payment_received": sale_data.payment_received,
            "change_given": change_given,
            "status": "completed",
            "notes": sale_data.notes,
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": kampala_to_utc(now_kampala())
        }

        # Insert sale
        result = await db.sales.insert_one(sale_doc)

        # Also create an order record for unified order management
        order_count = await db.orders.count_documents({})
        order_number = f"ORD-{order_count + 1:06d}"

        # Prepare order items
        order_items = []
        for item in sale_items:
            order_items.append({
                "product_id": str(item["product_id"]),
                "product_name": item["product_name"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "total_price": item["total_price"],
                "discount_amount": item["discount_amount"]
            })

        # Create order document for regular sale
        order_doc = {
            "order_number": order_number,
            "client_id": ObjectId(sale_data.customer_id) if sale_data.customer_id else None,
            "client_name": sale_data.customer_name or "Walk-in Client",
            "client_email": "",
            "client_phone": "",
            "items": order_items,
            "subtotal": subtotal,
            "tax": tax_amount,
            "discount": sale_data.discount_amount,
            "total": total_amount,
            "status": "completed",  # Regular sales are completed immediately
            "payment_method": sale_data.payment_method,
            "payment_status": OrderPaymentStatus.PAID if sale_data.payment_method != "not_paid" else OrderPaymentStatus.PENDING,
            "notes": sale_data.notes or "",
            "sale_id": result.inserted_id,  # Link to the sale record
            "created_by": current_user.id,
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": kampala_to_utc(now_kampala())
        }

        # Insert order
        await db.orders.insert_one(order_doc)

        # Update product stock quantities
        for item in sale_items:
            # Check if this is a decant sale by looking at the product
            product = await db.products.find_one({"_id": item["product_id"]})

            # Check if this is a decant sale (price matches decant price)
            is_decant_sale = False
            if product and product.get("decant") and product["decant"].get("is_decantable"):
                decant_price = product["decant"].get("decant_price")
                if decant_price and abs(item["unit_price"] - decant_price) < 0.01:  # Allow for small floating point differences
                    is_decant_sale = True

            if is_decant_sale:
                # Handle decant sale - reduce ml instead of stock count
                success, message, updated_product = await process_decant_sale(
                    db, item["product_id"], item["quantity"]
                )
                if not success:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to process decant sale for {item['product_name']}: {message}"
                    )
            else:
                # Handle regular product sale - reduce stock count
                await db.products.update_one(
                    {"_id": item["product_id"]},
                    {"$inc": {"stock_quantity": -item["quantity"]}}
                )

        # Update customer statistics if customer exists
        if sale_data.customer_id:
            await db.customers.update_one(
                {"_id": ObjectId(sale_data.customer_id)},
                {
                    "$inc": {
                        "total_purchases": total_amount,
                        "total_orders": 1
                    },
                    "$set": {
                        "last_purchase_date": kampala_to_utc(now_kampala()),
                        "updated_at": kampala_to_utc(now_kampala())
                    }
                }
            )

        # Get the created sale for response
        created_sale = await db.sales.find_one({"_id": result.inserted_id})

        # Convert to response format
        sale_items_response = [
            SaleItemResponse(
                product_id=str(item["product_id"]),
                product_name=item["product_name"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                total_price=item["total_price"],
                discount_amount=item["discount_amount"]
            )
            for item in created_sale["items"]
        ]

        return SaleResponse(
            id=str(created_sale["_id"]),
            sale_number=created_sale["sale_number"],
            customer_id=str(created_sale["customer_id"]) if created_sale.get("customer_id") else None,
            customer_name=created_sale.get("customer_name"),
            cashier_id=str(created_sale["cashier_id"]),
            cashier_name=created_sale["cashier_name"],
            items=sale_items_response,
            subtotal=created_sale["subtotal"],
            tax_amount=created_sale["tax_amount"],
            discount_amount=created_sale["discount_amount"],
            total_amount=created_sale["total_amount"],
            payment_method=created_sale["payment_method"],
            payment_received=created_sale["payment_received"],
            change_given=created_sale["change_given"],
            status=created_sale["status"],
            notes=created_sale.get("notes"),
            created_at=created_sale["created_at"],
            updated_at=created_sale.get("updated_at")
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create sale: {str(e)}"
        )


@router.post("/orders")
async def create_order(order_data: dict, current_user: User = Depends(get_current_user_hybrid_dependency())):
    """Create a new order from POS sale"""
    try:
        db = await get_database()

        # Generate order number
        order_count = await db.orders.count_documents({})
        order_number = f"ORD-{order_count + 1:06d}"

        # Create order document
        order_doc = {
            "order_number": order_number,
            "client_id": ObjectId(order_data["client_id"]) if order_data.get("client_id") else None,
            "client_name": order_data.get("client_name", "Walk-in Client"),
            "client_email": order_data.get("client_email", ""),
            "client_phone": order_data.get("client_phone", ""),
            "items": order_data["items"],
            "subtotal": order_data["subtotal"],
            "tax": order_data["tax"],
            "discount": order_data.get("discount", 0),
            "total": order_data["total"],
            "status": "completed" if order_data.get("payment_method") != "not_paid" else "pending",
            "payment_method": order_data.get("payment_method", "cash"),
            "payment_status": "paid" if order_data.get("payment_method") != "not_paid" else "pending",
            "notes": order_data.get("notes", ""),
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": kampala_to_utc(now_kampala()),
            "created_by": ObjectId(order_data["created_by"]) if order_data.get("created_by") and ObjectId.is_valid(order_data["created_by"]) else None
        }

        # Insert order
        result = await db.orders.insert_one(order_doc)

        # Update product stock quantities only if payment is made
        if order_data.get("payment_method") != "not_paid":
            for item in order_data["items"]:
                # Check if this is a decant sale by looking at the product
                product = await db.products.find_one({"_id": ObjectId(item["product_id"])})

                # Check if this is a decant sale (price matches decant price)
                is_decant_sale = False
                if product and product.get("decant") and product["decant"].get("is_decantable"):
                    decant_price = product["decant"].get("decant_price")
                    item_unit_price = item.get("unit_price", item.get("price", 0))
                    if decant_price and abs(item_unit_price - decant_price) < 0.01:
                        is_decant_sale = True

                if is_decant_sale:
                    # Handle decant sale - reduce ml instead of stock count
                    success, message, updated_product = await process_decant_sale(
                        db, ObjectId(item["product_id"]), item["quantity"]
                    )
                    if not success:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Failed to process decant sale for {item.get('product_name', 'product')}: {message}"
                        )
                else:
                    # Handle regular product sale - reduce stock count
                    await db.products.update_one(
                        {"_id": ObjectId(item["product_id"])},
                        {"$inc": {"stock_quantity": -item["quantity"]}}
                    )

        # Update customer statistics if not a guest and payment is made
        if (order_data.get("client_id") and
            not order_data.get("is_guest_client", False) and
            order_data.get("payment_method") != "not_paid"):
            await db.customers.update_one(
                {"_id": ObjectId(order_data["client_id"])},
                {
                    "$inc": {
                        "total_purchases": order_data["total"],
                        "total_orders": 1
                    },
                    "$set": {
                        "last_purchase_date": kampala_to_utc(now_kampala()),
                        "updated_at": kampala_to_utc(now_kampala())
                    }
                }
            )

        return {
            "id": str(result.inserted_id),
            "order_number": order_number,
            "message": "Order created successfully"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create order: {str(e)}"
        )


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
