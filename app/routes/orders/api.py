from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional, List
from datetime import datetime, date
from bson import ObjectId
from ...config.database import get_database
from ...models import User
from ...utils.auth import get_current_user

router = APIRouter(prefix="/api/orders", tags=["Orders API"])


@router.get("/", response_model=dict)
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
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

            orders.append({
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



