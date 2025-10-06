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
    PerOrderPayment,
    PerOrderPaymentMethod
)
from ...utils.auth import get_current_user_hybrid_dependency
from ...utils.counter import get_next_sequence_value
from .utils import generate_per_order_number
from ...models.sale import Sale, SaleItem, PaymentMethod
from ...models.order import Order, OrderItem, OrderPaymentMethod
from pydantic import BaseModel
import asyncio
from ...utils.sale_number_generator import generate_unique_sale_number

class ConfirmPayload(BaseModel):
    payment_method: str

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

    for order in per_orders:
        order['id'] = str(order['_id'])

    # Convert ObjectId to string for each order and nested items
    def convert_objectid_to_str(obj):
        if isinstance(obj, dict):
            return {k: convert_objectid_to_str(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_objectid_to_str(elem) for elem in obj]
        elif isinstance(obj, ObjectId):
            return str(obj)
        elif hasattr(obj, 'value'):  # Handle enum values
            return obj.value
        return obj

    per_orders_serializable = [convert_objectid_to_str(order) for order in per_orders]

    for order in per_orders_serializable:
        order['id'] = order['_id']
        
        # Ensure payments are properly serialized
        if 'payments' in order and isinstance(order['payments'], list):
            for payment in order['payments']:
                if isinstance(payment, dict) and 'method' in payment:
                    # Handle both enum and string cases
                    if hasattr(payment['method'], 'value'):
                        payment['method'] = payment['method'].value
                    elif not isinstance(payment['method'], str):
                        payment['method'] = str(payment['method'])
                    
                    # Ensure amount_received is included if present
                    if 'amount_received' not in payment and 'amount' in payment:
                        payment['amount_received'] = payment['amount']

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

    # Add payment information if provided
    if per_order_in.payment:
        payment_method_str = per_order_in.payment.method
        # Convert string to enum
        try:
            payment_method_enum = PerOrderPaymentMethod(payment_method_str)
        except ValueError:
            payment_method_enum = PerOrderPaymentMethod.NOT_PAID
        
        # Create a payment record
        payment_record = PerOrderPayment(
            method=payment_method_enum,
            amount=total_amount,
            amount_received=per_order_in.payment.amount_received,  # Add this
            change=per_order_in.payment.change,  # Add this
            currency="UGX",
            status=PerOrderPaymentStatus.PENDING,
            reference=per_order_in.payment.reference
        )
        new_per_order.payments.append(payment_record)
        
        # Update payment status based on method
        if payment_method_str != "not_paid":
            new_per_order.payment_status = PerOrderPaymentStatus.PAID

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
    if 'items' in update_data or 'shipping_cost' in update_data or 'order_discount' in update_data:
        items = update_data.get('items', existing_per_order.get('items', []))
        shipping_cost = update_data.get('shipping_cost', existing_per_order.get('shipping_cost', 0))
        order_discount = update_data.get('order_discount', existing_per_order.get('order_discount', 0))

        subtotal = sum(item.get('total_price', 0) for item in items)
        item_discounts = sum(item.get('discount_amount', 0) for item in items)
        discount_total = item_discounts + order_discount
        total_amount = subtotal - discount_total + shipping_cost
        
        update_data['subtotal'] = subtotal
        update_data['discount_total'] = discount_total
        update_data['total_amount'] = total_amount

    update_data['updated_at'] = datetime.utcnow()

    # Handle payment information
    if 'payment' in update_data and update_data['payment'] is not None:
        payment_info = update_data['payment']
        payment_method_str = payment_info['method']
        
        # Convert string to enum
        try:
            payment_method_enum = PerOrderPaymentMethod(payment_method_str)
        except ValueError:
            payment_method_enum = PerOrderPaymentMethod.NOT_PAID
        
        # Create a payment record
        payment_record = PerOrderPayment(
            method=payment_method_enum,
            amount=update_data.get('total_amount', existing_per_order.get('total_amount', 0)),
            amount_received=payment_info.get('amount_received'),
            change=payment_info.get('change'),
            currency="UGX",
            status=PerOrderPaymentStatus.PAID if payment_method_str != "not_paid" else PerOrderPaymentStatus.PENDING,
        )
        
        # Update payment status based on method
        if 'payment_status' in update_data:
            update_data['payment_status'] = update_data['payment_status']
        elif payment_method_str != "not_paid":
            update_data['payment_status'] = PerOrderPaymentStatus.PAID
        else:
            update_data['payment_status'] = PerOrderPaymentStatus.PENDING
            
        # Replace payments array with the new payment
        update_data['payments'] = [payment_record.dict()]
    elif 'payment' in update_data and update_data['payment'] is None:
        # If payment is explicitly set to None, clear payments
        update_data['payments'] = []
        update_data['payment_status'] = PerOrderPaymentStatus.PENDING

    # Preserve payment information when not updating
    elif 'payments' not in update_data and 'payments' in existing_per_order:
        update_data['payments'] = existing_per_order['payments']
        update_data['payment_status'] = existing_per_order.get('payment_status', PerOrderPaymentStatus.PENDING)

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


@router.post("/{per_order_id}/confirm", response_model=dict)
async def confirm_per_order(
    per_order_id: str,
    payload: ConfirmPayload,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    db = await get_database()
    
    async with await db.client.start_session() as session:
        async with session.start_transaction():
            try:
                # 1. Fetch the PerOrder
                per_order = await db.per_orders.find_one({"_id": ObjectId(per_order_id)}, session=session)
                if not per_order:
                    raise HTTPException(status_code=404, detail="Per Order not found")

                if per_order.get("status") == "confirmed":
                    raise HTTPException(status_code=400, detail="Order already confirmed")

                # 2. Decrement stock for all items (but allow negative stock for per-orders)
                product_ids = [ObjectId(item["product_id"]) for item in per_order["items"]]
                products_map = {p["_id"]: p async for p in db.products.find({"_id": {"$in": product_ids}}, session=session)}

                product_updates = []
                stock_warnings = []
                for item in per_order["items"]:
                    product_id = ObjectId(item["product_id"])
                    product = products_map.get(product_id)
                    quantity_to_decrement = item["quantity"]

                    # Check stock but don't prevent confirmation for per-orders
                    if not product or product.get("stock_quantity", 0) < quantity_to_decrement:
                        # Add warning but continue processing
                        product_name = item.get("product_name", "Unknown Product")
                        current_stock = product.get("stock_quantity", 0) if product else 0
                        stock_warnings.append(f"Not enough stock for {product_name} (needed: {quantity_to_decrement}, available: {current_stock})")

                    # Still decrement stock even if it goes negative
                    product_updates.append(
                        db.products.update_one(
                            {"_id": product_id},
                            {"$inc": {"stock_quantity": -quantity_to_decrement}},
                            session=session
                        )
                    )
                
                if product_updates:
                    await asyncio.gather(*product_updates)

                # 3. Create Order document with consistent numbering
                order_count = await db.orders.count_documents({})
                order_number = f"ORD-{order_count + 1:06d}"
                order_items = [OrderItem(**item) for item in per_order["items"]]
                
                # Set payment status based on payment method
                payment_status = "paid" if payload.payment_method != "not_paid" else "pending"
                
                # Set order status based on payment method
                order_status = "completed" if payload.payment_method != "not_paid" else "active"
                
                # Convert payment method string to enum
                try:
                    payment_method_enum = OrderPaymentMethod(payload.payment_method)
                except ValueError:
                    payment_method_enum = OrderPaymentMethod.CASH  # Default to cash if invalid
                
                # Ensure all required fields have values
                tax_amount = per_order.get("tax_total", 0)
                paid_amount = per_order["total_amount"] if payload.payment_method != "not_paid" else 0
                balance = 0 if payload.payment_method != "not_paid" else per_order["total_amount"]
                
                new_order_obj = Order(
                    order_number=order_number,
                    client_id=per_order.get("customer_id"),
                    client_name=per_order["customer_name"],
                    client_phone=per_order.get("customer_phone"),
                    items=order_items,
                    subtotal=per_order["subtotal"],
                    tax=tax_amount,
                    discount=per_order["discount_total"],
                    total=per_order["total_amount"],
                    paid_amount=paid_amount,
                    balance=balance,
                    status=order_status,
                    payment_status=payment_status,
                    created_by=current_user.id,
                    payment_method=payment_method_enum,
                )
                order_result = await db.orders.insert_one(new_order_obj.dict(by_alias=True), session=session)

                # 4. Create Sale document
                sale_items = [
                    SaleItem(
                        product_id=ObjectId(item["product_id"]),
                        product_name=item["product_name"],
                        sku=products_map.get(ObjectId(item["product_id"]), {}).get("sku", ""),
                        quantity=item["quantity"],
                        unit_price=item["unit_price"],
                        cost_price=products_map.get(ObjectId(item["product_id"]), {}).get("cost_price", 0),
                        total_price=item["total_price"],
                        discount_amount=item.get("discount_amount", 0)
                    ) for item in per_order["items"]
                ]
                sale_number = await generate_unique_sale_number(db)
                
                # Set payment received based on payment method
                payment_received = per_order["total_amount"] if payload.payment_method != "not_paid" else 0
                change_given = 0  # Assuming no change for pre-orders
                
                # Set sale status based on payment method
                sale_status = "completed" if payload.payment_method != "not_paid" else "active"
                
                # Convert payment method string to enum
                try:
                    payment_method_enum = PaymentMethod(payload.payment_method)
                except ValueError:
                    payment_method_enum = PaymentMethod.CASH  # Default to cash if invalid
                
                new_sale_obj = Sale(
                    sale_number=sale_number,
                    customer_id=per_order.get("customer_id"),
                    customer_name=per_order["customer_name"],
                    cashier_id=current_user.id,
                    cashier_name=current_user.full_name,
                    items=sale_items,
                    subtotal=per_order["subtotal"],
                    discount_amount=per_order["discount_total"],
                    total_amount=per_order["total_amount"],
                    payment_method=payment_method_enum,
                    payment_received=payment_received,
                    change_given=change_given,
                    status=sale_status,
                )
                sale_result = await db.sales.insert_one(new_sale_obj.dict(by_alias=True), session=session)

                # 5. Update PerOrder status
                await db.per_orders.update_one(
                    {"_id": ObjectId(per_order_id)},
                    {"$set": {
                        "status": "confirmed",
                        "order_id": order_result.inserted_id,
                        "sale_id": sale_result.inserted_id
                    }},
                    session=session
                )

                # Prepare response with any stock warnings
                response_data = {
                    "success": True,
                    "message": "Order confirmed successfully",
                    "order_id": str(order_result.inserted_id),
                    "sale_id": str(sale_result.inserted_id)
                }
                
                if stock_warnings:
                    response_data["warnings"] = stock_warnings

                return response_data

            except Exception as e:
                await session.abort_transaction()
                # Log the exception for debugging
                import traceback
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")


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
