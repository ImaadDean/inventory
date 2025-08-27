from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from typing import Optional, List
from datetime import datetime, date
from bson import ObjectId
import asyncio
from ...config.database import get_database
from ...models import User
from ...models.order import OrderUpdate
from ...utils.auth import get_current_user, get_current_user_hybrid_dependency, verify_token, get_user_by_username

router = APIRouter(prefix="/api/orders", tags=["Orders API"])


@router.put("/{order_id}", response_model=dict)
async def update_order(
    order_id: str,
    order_data: OrderUpdate,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Update an existing order, its corresponding sale record, and adjust product stock."""
    db = await get_database()
    client = db.client

    async with await client.start_session() as session:
        async with session.start_transaction():
            try:
                # 1. Fetch the existing order
                existing_order = await db.orders.find_one({"_id": ObjectId(order_id)}, session=session)
                if not existing_order:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

                # 2. Calculate stock changes
                stock_deltas = {}
                # Credit back the old items
                for item in existing_order.get("items", []):
                    product_id = str(item["product_id"])
                    stock_deltas[product_id] = stock_deltas.get(product_id, 0) + item["quantity"]

                # Debit the new items
                for item_data in order_data.items:
                    product_id = item_data.product_id
                    stock_deltas[product_id] = stock_deltas.get(product_id, 0) - item_data.quantity

                # 3. Validate new stock levels and prepare product updates
                product_updates = []
                for product_id, delta in stock_deltas.items():
                    if delta != 0:
                        product = await db.products.find_one({"_id": ObjectId(product_id)}, session=session)
                        if not product:
                            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with ID {product_id} not found")
                        
                        if product['stock_quantity'] + delta < 0:
                            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Not enough stock for product {product['name']}")
                        
                        product_updates.append(
                            db.products.update_one(
                                {"_id": ObjectId(product_id)},
                                {"$inc": {"stock_quantity": delta}},
                                session=session
                            )
                        )

                # 4. Prepare updated order items and calculate totals
                new_items = []
                new_subtotal = 0
                total_items_discount = 0

                for item_data in order_data.items:
                    product = await db.products.find_one({"_id": ObjectId(item_data.product_id)}, session=session)
                    total_price = item_data.quantity * item_data.unit_price
                    new_subtotal += total_price
                    total_items_discount += item_data.discount

                    new_items.append({
                        "product_id": item_data.product_id,
                        "product_name": product["name"],
                        "quantity": item_data.quantity,
                        "unit_price": item_data.unit_price,
                        "total_price": total_price,
                        "discount_amount": item_data.discount
                    })

                # 5. Calculate overall discount and total
                order_discount_amount = 0
                if order_data.discount_type == 'percentage':
                    order_discount_amount = (new_subtotal - total_items_discount) * (order_data.discount / 100)
                else:
                    order_discount_amount = order_data.discount

                total_discount = total_items_discount + order_discount_amount
                new_total = new_subtotal - total_discount

                # 6. Prepare the update data for the order
                order_update_data = {
                    "items": new_items,
                    "subtotal": new_subtotal,
                    "discount": total_discount,
                    "total": new_total,
                    "notes": order_data.notes or existing_order.get("notes"),
                    "updated_at": datetime.utcnow()
                }

                # 7. Handle client update
                if order_data.client_id:
                    client_doc = await db.customers.find_one({"_id": ObjectId(order_data.client_id)}, session=session)
                    if not client_doc:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
                    order_update_data["client_id"] = ObjectId(order_data.client_id)
                    order_update_data["client_name"] = client_doc["name"]
                    order_update_data["client_phone"] = client_doc.get("phone")

                # 8. Execute all database updates
                # Update stocks
                if product_updates:
                    await asyncio.gather(*product_updates)

                # Update order
                await db.orders.update_one(
                    {"_id": ObjectId(order_id)},
                    {"$set": order_update_data},
                    session=session
                )

                # 9. If there's a linked sale, update it too
                if existing_order.get("sale_id"):
                    sale_update_data = {
                        "items": [
                            {
                                "product_id": ObjectId(item["product_id"]),
                                "product_name": item["product_name"],
                                "sku": (await db.products.find_one({"_id": ObjectId(item["product_id"])}, session=session)).get("sku", ""),
                                "quantity": item["quantity"],
                                "unit_price": item["unit_price"],
                                "cost_price": (await db.products.find_one({"_id": ObjectId(item["product_id"])}, session=session)).get("cost_price", 0),
                                "total_price": item["total_price"],
                                "discount_amount": item["discount_amount"]
                            } for item in new_items
                        ],
                        "subtotal": new_subtotal,
                        "discount_amount": total_discount,
                        "total_amount": new_total,
                        "notes": order_data.notes or existing_order.get("notes"),
                        "updated_at": datetime.utcnow()
                    }
                    if order_data.client_id:
                        sale_update_data["customer_id"] = ObjectId(order_data.client_id)
                        sale_update_data["customer_name"] = order_update_data["client_name"]

                    await db.sales.update_one(
                        {"_id": existing_order["sale_id"]},
                        {"$set": sale_update_data},
                        session=session
                    )

            except HTTPException as e:
                await session.abort_transaction()
                raise e
            except Exception as e:
                await session.abort_transaction()
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {str(e)}")

    return {"success": True, "message": "Order updated successfully"}


@router.get("/", response_model=dict)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    order_type: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None)
):
    """Get all orders with pagination and filtering"""
    try:
        db = await get_database()
        
        # Build filter query
        filter_query = {}
        
        if search:
            filter_query["$or"] = [
                {"order_number": {"$regex": search, "$options": "i"}},
                {"client_name": {"$regex": search, "$options": "i"}},
                {"notes": {"$regex": search, "$options": "i"}}
            ]
        
        if status:
            filter_query["status"] = status

        if order_type:
            if order_type == "installment":
                filter_query["payment_method"] = "installment"
            elif order_type == "regular":
                filter_query["payment_method"] = {"$ne": "installment"}

        if client_id:
            filter_query["client_id"] = ObjectId(client_id)
            
        if date_from:
            filter_query["created_at"] = {"$gte": datetime.combine(date_from, datetime.min.time())}
            
        if date_to:
            if "created_at" in filter_query:
                filter_query["created_at"]["$lte"] = datetime.combine(date_to, datetime.max.time())
            else:
                filter_query["created_at"] = {"$lte": datetime.combine(date_to, datetime.max.time())}

        # Get total count
        total = await db.orders.count_documents(filter_query)

        # Get orders with pagination
        skip = (page - 1) * size
        cursor = db.orders.find(filter_query).skip(skip).limit(size).sort("created_at", -1)
        orders_data = await cursor.to_list(length=size)

        orders = []
        for order in orders_data:
            # Get user information for created_by field
            created_by_name = "System"
            if order.get("created_by"):
                try:
                    # Handle both ObjectId and string formats
                    created_by_id = order["created_by"]
                    if isinstance(created_by_id, str) and created_by_id:
                        created_by_id = ObjectId(created_by_id)
                    elif isinstance(created_by_id, ObjectId):
                        pass  # Already an ObjectId
                    else:
                        created_by_id = None

                    if created_by_id:
                        user = await db.users.find_one({"_id": created_by_id})
                        if user:
                            created_by_name = user.get("full_name", "Staff Member")
                except:
                    created_by_name = "Staff Member"

            client_phone = order.get("client_phone", "")
            client_id = order.get("client_id")
            if client_id:
                try:
                    if isinstance(client_id, str):
                        client_id = ObjectId(client_id)
                    
                    client = await db.customers.find_one({"_id": client_id})
                    if client and client.get("phone"):
                        client_phone = client.get("phone")
                except Exception:
                    pass # Ignore if client_id is invalid or client not found

            orders.append({
                "id": str(order["_id"]),
                "order_number": order["order_number"],
                "client_id": str(order.get("client_id", "")),
                "client_name": order.get("client_name", "Walk-in Client"),
                "client_email": order.get("client_email", ""),
                "client_phone": client_phone,
                "items": order["items"],
                "subtotal": order["subtotal"],
                "tax": order["tax"],
                "discount": order.get("discount", 0),
                "total": order["total"],
                "paid_amount": order.get("paid_amount", 0),
                "balance": order.get("balance", order["total"]),
                "status": order["status"],
                "payment_method": order.get("payment_method", "cash"),
                "payment_status": order.get("payment_status", "paid"),
                "notes": order.get("notes", ""),
                "created_at": order["created_at"].isoformat(),
                "updated_at": order.get("updated_at", order["created_at"]).isoformat(),
                "created_by": str(order.get("created_by", "")),
                "created_by_name": created_by_name
            })

        return {
            "orders": orders,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve orders: {str(e)}"
        )


@router.get("/test-stats")
async def test_stats():
    """Test stats endpoint"""
    return {"message": "test endpoint works"}


@router.get("/stats")
async def get_order_stats():
    """Get order statistics"""
    try:
        db = await get_database()

        # Count orders using aggregation
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total_orders": {"$sum": 1},
                    "completed_orders": {
                        "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                    },
                    "pending_orders": {
                        "$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}
                    },
                    "total_revenue": {"$sum": "$total"}
                }
            }
        ]

        result = await db.orders.aggregate(pipeline).to_list(1)

        if result:
            stats = result[0]
            return {
                "total_orders": stats.get("total_orders", 0),
                "completed_orders": stats.get("completed_orders", 0),
                "pending_orders": stats.get("pending_orders", 0),
                "total_revenue": stats.get("total_revenue", 0)
            }
        else:
            return {
                "total_orders": 0,
                "completed_orders": 0,
                "pending_orders": 0,
                "total_revenue": 0
            }

    except Exception as e:
        print(f"Stats API Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "total_orders": 0,
            "completed_orders": 0,
            "pending_orders": 0,
            "total_revenue": 0
        }


@router.get("/export")
async def export_orders(
    date_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="End date (YYYY-MM-DD)")
):
    """Export orders to CSV with optional date range filtering"""
    try:
        db = await get_database()

        # Build filter query for date range
        filter_query = {}

        if date_from or date_to:
            date_filter = {}
            if date_from:
                # Start of the day
                from datetime import datetime, time
                start_datetime = datetime.combine(date_from, time.min)
                date_filter["$gte"] = start_datetime

            if date_to:
                # End of the day
                from datetime import datetime, time
                end_datetime = datetime.combine(date_to, time.max)
                date_filter["$lte"] = end_datetime

            filter_query["created_at"] = date_filter

        # Get orders with optional date filtering
        orders_data = await db.orders.find(filter_query).sort("created_at", -1).to_list(None)

        # Prepare CSV data
        csv_data = []
        csv_data.append([
            "Order Number", "Client Name", "Client Phone", "Items Details",
            "Subtotal", "Discount", "Total", "Status", "Payment Method",
            "Payment Status", "Created At", "Processed By"
        ])

        for order in orders_data:
            # Get user information for created_by field
            created_by_name = "System"
            if order.get("created_by"):
                try:
                    created_by_id = order["created_by"]
                    if isinstance(created_by_id, str) and created_by_id:
                        created_by_id = ObjectId(created_by_id)
                    elif isinstance(created_by_id, ObjectId):
                        pass
                    else:
                        created_by_id = None

                    if created_by_id:
                        user = await db.users.find_one({"_id": created_by_id})
                        if user:
                            created_by_name = user.get("full_name", "Staff Member")
                except:
                    created_by_name = "Staff Member"

            # Format items details
            items_details = ""
            if order.get("items"):
                item_strings = []
                for item in order["items"]:
                    item_name = item.get("name", "Unknown Item")
                    item_sku = item.get("sku", "")
                    item_qty = item.get("quantity", 0)
                    item_price = item.get("price", 0)
                    item_total = item.get("total", 0)

                    # Format: "Product Name (SKU) - Qty: X @ Price each = Total"
                    if item_sku:
                        item_string = f"{item_name} ({item_sku}) - Qty: {item_qty} @ {item_price} each = {item_total}"
                    else:
                        item_string = f"{item_name} - Qty: {item_qty} @ {item_price} each = {item_total}"

                    item_strings.append(item_string)

                items_details = " | ".join(item_strings)
            else:
                items_details = "No items"

            csv_data.append([
                order.get("order_number", ""),
                order.get("client_name", "Walk-in Client"),
                order.get("client_phone", ""),
                items_details,
                order.get("subtotal", 0),
                order.get("discount", 0),
                order.get("total", 0),
                order.get("status", ""),
                order.get("payment_method", "cash"),
                order.get("payment_status", "paid"),
                order.get("created_at", "").strftime("%Y-%m-%d %H:%M:%S") if order.get("created_at") else "",
                created_by_name
            ])

        # Convert to CSV string
        import io
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(csv_data)
        csv_content = output.getvalue()
        output.close()

        # Return CSV response
        from fastapi.responses import Response
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=orders_export.csv"}
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export orders: {str(e)}"
        )


@router.get("/{order_id}", response_model=dict)
async def get_order(order_id: str):
    """Get a specific order by ID"""
    try:
        db = await get_database()
        
        order = await db.orders.find_one({"_id": ObjectId(order_id)})
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )

        # Get user information for created_by field
        created_by_name = "System"
        if order.get("created_by"):
            try:
                # Handle both ObjectId and string formats
                created_by_id = order["created_by"]
                if isinstance(created_by_id, str) and created_by_id:
                    created_by_id = ObjectId(created_by_id)
                elif isinstance(created_by_id, ObjectId):
                    pass  # Already an ObjectId
                else:
                    created_by_id = None

                if created_by_id:
                    user = await db.users.find_one({"_id": created_by_id})
                    if user:
                        created_by_name = user.get("full_name", "Staff Member")
            except:
                created_by_name = "Staff Member"

        return {
            "id": str(order["_id"]),
            "order_number": order["order_number"],
            "client_id": str(order.get("client_id", "")),
            "client_name": order.get("client_name", "Walk-in Client"),
            "client_email": order.get("client_email", ""),
            "client_phone": order.get("client_phone", ""),
            "items": order["items"],
            "subtotal": order["subtotal"],
            "tax": order["tax"],
            "discount": order.get("discount", 0),
            "total": order["total"],
            "paid_amount": order.get("paid_amount", 0),
            "balance": order.get("balance", order["total"]),
            "status": order["status"],
            "payment_method": order.get("payment_method", "cash"),
            "payment_status": order.get("payment_status", "paid"),
            "notes": order.get("notes", ""),
            "created_at": order["created_at"].isoformat(),
            "updated_at": order.get("updated_at", order["created_at"]).isoformat(),
            "created_by": str(order.get("created_by", "")),
            "created_by_name": created_by_name
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve order: {str(e)}"
        )


@router.put("/{order_id}/status")
async def update_order_status(
    order_id: str,
    status_data: dict,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Update order status"""
    try:

        db = await get_database()

        # Validate order exists
        order = await db.orders.find_one({"_id": ObjectId(order_id)})
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )

        new_status = status_data.get("status")
        if not new_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status is required"
            )

        # Validate status
        valid_statuses = ["pending", "active", "completed", "cancelled"]
        if new_status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )

        # Update order status
        update_data = {
            "status": new_status,
            "updated_at": datetime.utcnow()
        }

        # If marking as completed, also update payment status
        if new_status == "completed":
            update_data["payment_status"] = "paid"

        result = await db.orders.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update order status"
            )

        return {
            "success": True,
            "message": f"Order status updated to {new_status}",
            "order_id": order_id,
            "new_status": new_status
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update order status: {str(e)}"
        )


@router.delete("/{order_id}", response_model=dict)
async def delete_order(
    order_id: str,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Delete an order, restore product stock, and delete any associated sale."""
    db = await get_database()
    client = db.client

    async with await client.start_session() as session:
        async with session.start_transaction():
            try:
                # 1. Fetch the existing order
                existing_order = await db.orders.find_one({"_id": ObjectId(order_id)}, session=session)
                if not existing_order:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

                # 2. Restore stock for each item in the order
                if existing_order.get("items"):
                    product_updates = []
                    for item in existing_order["items"]:
                        product_id = item["product_id"]
                        quantity = item["quantity"]
                        
                        if not ObjectId.is_valid(product_id):
                            print(f"Warning: Invalid product_id '{product_id}' in order '{order_id}'. Skipping stock update for this item.")
                            continue

                        product_updates.append(
                            db.products.update_one(
                                {"_id": ObjectId(product_id)},
                                {"$inc": {"stock_quantity": quantity}},
                                session=session
                            )
                        )
                    
                    if product_updates:
                        await asyncio.gather(*product_updates)

                # 3. If there's a linked sale, delete it
                if existing_order.get("sale_id"):
                    await db.sales.delete_one(
                        {"_id": existing_order["sale_id"]},
                        session=session
                    )

                # 4. Delete the order itself
                await db.orders.delete_one({"_id": ObjectId(order_id)}, session=session)

            except Exception as e:
                await session.abort_transaction()
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {str(e)}")

    return {"success": True, "message": "Order deleted successfully and stock restored"}