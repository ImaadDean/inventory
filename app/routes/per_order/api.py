from fastapi import APIRouter, Depends, HTTPException, status, Query
from bson import ObjectId
from typing import Optional, Dict, Any
from datetime import datetime
from ...config.database import get_database
from ...models.user import User
from ...models.per_order import (
    PerOrder,
    PerOrderCreate,
    PerOrderUpdate,
    PerOrderStatus,
    PerOrderStatusHistory,
    PerOrderPaymentStatus,
)
from ...utils.auth import get_current_user_hybrid_dependency
from .utils import generate_per_order_number

router = APIRouter(
    prefix="/api/per-order",
    tags=["Per Order API"],
    dependencies=[Depends(get_current_user_hybrid_dependency())]
)


@router.get("/", response_model=dict)
async def list_per_orders(
    page: int = 1,
    size: int = 10,
    search: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """List per orders with pagination and filtering"""
    db = await get_database()
    query = {}

    if search:
        query["$or"] = [
            {"order_number": {"$regex": search, "$options": "i"}},
            {"customer_name": {"$regex": search, "$options": "i"}},
        ]

    if status:
        query["status"] = status

    if date_from and date_to:
        query["created_at"] = {"$gte": date_from, "$lte": date_to}
    elif date_from:
        query["created_at"] = {"$gte": date_from}
    elif date_to:
        query["created_at"] = {"$lte": date_to}

    total = await db.per_orders.count_documents(query)
    per_orders = await db.per_orders.find(query).sort("created_at", -1).skip((page - 1) * size).limit(size).to_list(length=size)

    # Convert ObjectId to string for each order and nested items
    def convert_objectid_to_str(obj):
        if isinstance(obj, dict):
            return {k: convert_objectid_to_str(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_objectid_to_str(elem) for elem in obj]
        elif isinstance(obj, ObjectId):
            return str(obj)
        return obj

    per_orders_serializable = [convert_objectid_to_str(order) for order in per_orders]

    return {
        "orders": per_orders_serializable,
        "page": page,
        "size": size,
        "total": total,
        "total_pages": (total + size - 1) // size
    }


@router.post("/", response_model=PerOrder, status_code=status.HTTP_201_CREATED)
async def create_per_order(
    per_order_in: PerOrderCreate,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create a new per order"""
    db = await get_database()

    # Calculate totals from items
    subtotal = sum(item.total_price for item in per_order_in.items)
    discount_total = sum(item.discount_amount for item in per_order_in.items)
    total_amount = subtotal - discount_total + per_order_in.shipping_cost

    # Create PerOrder object
    new_per_order = PerOrder(
        **per_order_in.dict(),
        order_number=await generate_per_order_number(),
        subtotal=subtotal,
        discount_total=discount_total,
        total_amount=total_amount,
        created_by=current_user.id,
        payment_status=PerOrderPaymentStatus.PENDING,
        status=PerOrderStatus.PENDING,
        status_history=[
            PerOrderStatusHistory(
                status=PerOrderStatus.PENDING,
                changed_by=current_user.id
            )
        ]
    )

    # Insert into database
    result = await db.per_orders.insert_one(new_per_order.dict(by_alias=True))
    created_order = await db.per_orders.find_one({"_id": result.inserted_id})

    return created_order


@router.put("/{per_order_id}", response_model=PerOrder)
async def update_per_order(
    per_order_id: str,
    per_order_in: PerOrderUpdate,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """
    Update an existing per order.

    This endpoint saves changes to a per order without affecting product stock levels.
    Stock adjustments are handled when converting a per order to a final order.
    """
    db = await get_database()

    if not ObjectId.is_valid(per_order_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid per order ID")

    existing_per_order = await db.per_orders.find_one({"_id": ObjectId(per_order_id)})
    if not existing_per_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Per order not found")

    update_data = per_order_in.dict(exclude_unset=True)

    if not update_data:
        return existing_per_order

    # Recalculate totals if items or shipping cost changed
    if 'items' in update_data or 'shipping_cost' in update_data:
        items = update_data.get('items', existing_per_order.get('items', []))
        shipping_cost = update_data.get('shipping_cost', existing_per_order.get('shipping_cost', 0))

        subtotal = sum(item.get('total_price', 0) for item in items)
        discount_total = sum(item.get('discount_amount', 0) for item in items)
        total_amount = subtotal - discount_total + shipping_cost
        
        update_data['subtotal'] = subtotal
        update_data['discount_total'] = discount_total
        update_data['total_amount'] = total_amount

    update_data['updated_at'] = datetime.utcnow()

    # Handle status history
    if 'status' in update_data and update_data['status'] != existing_per_order.get('status'):
        new_status_entry = PerOrderStatusHistory(
            status=update_data['status'],
            changed_by=current_user.id
        )
        await db.per_orders.update_one(
            {"_id": ObjectId(per_order_id)},
            {
                "$set": update_data,
                "$push": {"status_history": new_status_entry.dict()}
            }
        )
    else:
        await db.per_orders.update_one(
            {"_id": ObjectId(per_order_id)},
            {"$set": update_data}
        )

    updated_order = await db.per_orders.find_one({"_id": ObjectId(per_order_id)})
    return updated_order


@router.get("/stats", response_model=dict)
async def get_per_order_stats(
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get per order statistics"""
    db = await get_database()

    total_orders = await db.per_orders.count_documents({})
    pending_orders = await db.per_orders.count_documents({"status": "pending"})
    delivered_orders = await db.per_orders.count_documents({"status": "delivered"})

    pipeline = [
        {
            "$group": {
                "_id": None,
                "total_revenue": {"$sum": "$total_amount"}
            }
        }
    ]
    total_revenue_result = await db.per_orders.aggregate(pipeline).to_list(length=1)
    total_revenue = total_revenue_result[0]["total_revenue"] if total_revenue_result else 0

    pipeline = [
        {"$unwind": "$items"},
        {
            "$group": {
                "_id": "$items.product_name",
                "total_ordered": {"$sum": "$items.quantity"}
            }
        },
        {"$sort": {"total_ordered": -1}},
        {"$limit": 5}
    ]
    most_ordered_products = await db.per_orders.aggregate(pipeline).to_list(length=5)

    return {
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "delivered_orders": delivered_orders,
        "total_revenue": total_revenue,
        "most_ordered_products": most_ordered_products
    }


@router.get("/{per_order_id}", response_model=dict)
async def get_per_order_details(
    per_order_id: str,
    include_customer: bool = Query(True, description="Include customer details"),
    include_original_order: bool = Query(True, description="Include original order details"),
    include_assigned_user: bool = Query(True, description="Include assigned user details"),
    include_sale: bool = Query(False, description="Include related sale details"),
    include_installment: bool = Query(False, description="Include related installment details"),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get comprehensive per order details with related information"""
    try:
        db = await get_database()
        
        # Validate per order ID
        if not ObjectId.is_valid(per_order_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid per order ID"
            )

        # Get per order
        per_order = await db.per_orders.find_one({"_id": ObjectId(per_order_id)})
        if not per_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Per order not found"
            )

        # Convert ObjectId to string for JSON serialization
        per_order["id"] = str(per_order["_id"])
        del per_order["_id"]
        
        # Convert other ObjectIds to strings
        if per_order.get("client_id"):
            per_order["client_id"] = str(per_order["client_id"])
        if per_order.get("created_by"):
            per_order["created_by"] = str(per_order["created_by"])
        if per_order.get("sale_id"):
            per_order["sale_id"] = str(per_order["sale_id"])
        if per_order.get("installment_id"):
            per_order["installment_id"] = str(per_order["installment_id"])

        # Convert datetime objects to ISO format
        if per_order.get("created_at"):
            per_order["created_at"] = per_order["created_at"].isoformat()
        if per_order.get("updated_at"):
            per_order["updated_at"] = per_order["updated_at"].isoformat()

        # Prepare response data
        response_data = {
            "order": per_order,
            "customer": None,
            "created_by": None,
            "related_sale": None,
            "related_installment": None
        }

        # Get customer information if requested and client_id exists
        if include_customer and per_order.get("client_id"):
            try:
                customer = await db.customers.find_one({"_id": ObjectId(per_order["client_id"])})
                if customer:
                    customer["id"] = str(customer["_id"])
                    del customer["_id"]
                    if customer.get("created_at"):
                        customer["created_at"] = customer["created_at"].isoformat()
                    if customer.get("updated_at"):
                        customer["updated_at"] = customer["updated_at"].isoformat()
                    if customer.get("last_purchase_date"):
                        customer["last_purchase_date"] = customer["last_purchase_date"].isoformat()
                    response_data["customer"] = customer
            except Exception as e:
                print(f"Error fetching customer: {e}")

        # Get creator information
        if per_order.get("created_by"):
            try:
                creator = await db.users.find_one({"_id": ObjectId(per_order["created_by"])})
                if creator:
                    response_data["created_by"] = {
                        "id": str(creator["_id"]),
                        "username": creator.get("username"),
                        "full_name": creator.get("full_name"),
                        "role": creator.get("role")
                    }
            except Exception as e:
                print(f"Error fetching creator: {e}")

        # Get related sale information if requested and sale_id exists
        if include_sale and per_order.get("sale_id"):
            try:
                sale = await db.sales.find_one({"_id": ObjectId(per_order["sale_id"])})
                if sale:
                    sale["id"] = str(sale["_id"])
                    del sale["_id"]
                    if sale.get("customer_id"):
                        sale["customer_id"] = str(sale["customer_id"])
                    if sale.get("cashier_id"):
                        sale["cashier_id"] = str(sale["cashier_id"])
                    if sale.get("created_at"):
                        sale["created_at"] = sale["created_at"].isoformat()
                    if sale.get("updated_at"):
                        sale["updated_at"] = sale["updated_at"].isoformat()
                    response_data["related_sale"] = sale
            except Exception as e:
                print(f"Error fetching related sale: {e}")

        # Get related installment information if requested and installment_id exists
        if include_installment and per_order.get("installment_id"):
            try:
                installment = await db.installments.find_one({"_id": ObjectId(per_order["installment_id"])})
                if installment:
                    installment["id"] = str(installment["_id"])
                    del installment["_id"]
                    if installment.get("customer_id"):
                        installment["customer_id"] = str(installment["customer_id"])
                    if installment.get("order_id"):
                        installment["order_id"] = str(installment["order_id"])
                    if installment.get("created_by"):
                        installment["created_by"] = str(installment["created_by"])
                    if installment.get("approved_by"):
                        installment["approved_by"] = str(installment["approved_by"])
                    if installment.get("created_at"):
                        installment["created_at"] = installment["created_at"].isoformat()
                    if installment.get("updated_at"):
                        installment["updated_at"] = installment["updated_at"].isoformat()
                    if installment.get("completed_at"):
                        installment["completed_at"] = installment["completed_at"].isoformat()
                    
                    # Convert payment dates
                    if installment.get("payments"):
                        for payment in installment["payments"]:
                            if payment.get("due_date"):
                                payment["due_date"] = payment["due_date"].isoformat()
                            if payment.get("payment_date"):
                                payment["payment_date"] = payment["payment_date"].isoformat()
                    
                    response_data["related_installment"] = installment
            except Exception as e:
                print(f"Error fetching related installment: {e}")

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve order details: {str(e)}"
        )


@router.get("/stats", response_model=dict)
async def get_per_order_stats(
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get per order statistics"""
    db = await get_database()

    total_orders = await db.per_orders.count_documents({})
    pending_orders = await db.per_orders.count_documents({"status": "pending"})
    delivered_orders = await db.per_orders.count_documents({"status": "delivered"})

    pipeline = [
        {
            "$group": {
                "_id": None,
                "total_revenue": {"$sum": "$total_amount"}
            }
        }
    ]
    total_revenue_result = await db.per_orders.aggregate(pipeline).to_list(length=1)
    total_revenue = total_revenue_result[0]["total_revenue"] if total_revenue_result else 0

    pipeline = [
        {"$unwind": "$items"},
        {
            "$group": {
                "_id": "$items.product_name",
                "total_ordered": {"$sum": "$items.quantity"}
            }
        },
        {"$sort": {"total_ordered": -1}},
        {"$limit": 5}
    ]
    most_ordered_products = await db.per_orders.aggregate(pipeline).to_list(length=5)

    return {
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "delivered_orders": delivered_orders,
        "total_revenue": total_revenue,
        "most_ordered_products": most_ordered_products
    }


@router.get("/{order_id}/summary", response_model=dict)
async def get_order_summary(
    order_id: str,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get a quick summary of order information"""
    try:
        db = await get_database()
        
        # Validate order ID
        if not ObjectId.is_valid(order_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid order ID"
            )
        
        # Get order
        order = await db.orders.find_one({"_id": ObjectId(order_id)})
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )

        # Calculate summary statistics
        total_items = len(order.get("items", []))
        total_quantity = sum(item.get("quantity", 0) for item in order.get("items", []))
        payment_percentage = ((order.get("paid_amount", 0) / order.get("total", 1)) * 100) if order.get("total", 0) > 0 else 0

        summary = {
            "order_id": str(order["_id"]),
            "order_number": order.get("order_number"),
            "client_name": order.get("client_name"),
            "status": order.get("status"),
            "payment_status": order.get("payment_status"),
            "total_amount": order.get("total", 0),
            "paid_amount": order.get("paid_amount", 0),
            "balance": order.get("balance", 0),
            "payment_percentage": round(payment_percentage, 1),
            "total_items": total_items,
            "total_quantity": total_quantity,
            "created_at": order.get("created_at").isoformat() if order.get("created_at") else None,
            "updated_at": order.get("updated_at").isoformat() if order.get("updated_at") else None
        }

        return {"summary": summary}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve order summary: {str(e)}"
        )
