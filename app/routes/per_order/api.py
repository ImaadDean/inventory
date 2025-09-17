from fastapi import APIRouter, Depends, HTTPException, status, Query
from bson import ObjectId
from typing import Optional, Dict, Any
from datetime import datetime
from ...config.database import get_database
from ...models.user import User
from ...models.per_order import PerOrder, PerOrderCreate, PerOrderUpdate
from ...utils.auth import get_current_user_hybrid_dependency
from .utils import generate_per_order_number

router = APIRouter(
    prefix="/api/per-order",
    tags=["Per Order API"],
    dependencies=[Depends(get_current_user_hybrid_dependency())]
)


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


@router.get("/{per_order_id}", response_model=dict)
async def get_per_order_details(
    per_order_id: str,
    include_customer: bool = Query(True, description="Include customer details"),
    include_original_order: bool = Query(True, description="Include original order details"),
    include_assigned_user: bool = Query(True, description="Include assigned user details"),
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
        order["id"] = str(order["_id"])
        del order["_id"]
        
        # Convert other ObjectIds to strings
        if order.get("client_id"):
            order["client_id"] = str(order["client_id"])
        if order.get("created_by"):
            order["created_by"] = str(order["created_by"])
        if order.get("sale_id"):
            order["sale_id"] = str(order["sale_id"])
        if order.get("installment_id"):
            order["installment_id"] = str(order["installment_id"])

        # Convert datetime objects to ISO format
        if order.get("created_at"):
            order["created_at"] = order["created_at"].isoformat()
        if order.get("updated_at"):
            order["updated_at"] = order["updated_at"].isoformat()

        # Prepare response data
        response_data = {
            "order": order,
            "customer": None,
            "created_by": None,
            "related_sale": None,
            "related_installment": None
        }

        # Get customer information if requested and client_id exists
        if include_customer and order.get("client_id"):
            try:
                customer = await db.customers.find_one({"_id": ObjectId(order["client_id"])})
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
        if order.get("created_by"):
            try:
                creator = await db.users.find_one({"_id": ObjectId(order["created_by"])})
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
        if include_sale and order.get("sale_id"):
            try:
                sale = await db.sales.find_one({"_id": ObjectId(order["sale_id"])})
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
        if include_installment and order.get("installment_id"):
            try:
                installment = await db.installments.find_one({"_id": ObjectId(order["installment_id"])})
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
