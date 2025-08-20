from fastapi import APIRouter, HTTPException, status, Depends, Query, Request, Body
from typing import Optional, List
from datetime import datetime, date
from bson import ObjectId
from ...config.database import get_database
from ...models import User
from ...utils.auth import get_current_user, get_current_user_hybrid_dependency, verify_token, get_user_by_username
from ...models.sale import Sale, SaleItem

router = APIRouter(prefix="/api/sales", tags=["Sales API"])


@router.get("/", response_model=dict)
async def get_sales(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None)
):
    """Get all sales with pagination and filtering"""
    try:
        db = await get_database()
        
        # Build filter query
        filter_query = {}
        
        if search:
            filter_query["$or"] = [
                {"sale_number": {"$regex": search, "$options": "i"}},
                {"customer_name": {"$regex": search, "$options": "i"}},
                {"notes": {"$regex": search, "$options": "i"}}
            ]
        
        if status:
            filter_query["status"] = status

        if client_id:
            filter_query["customer_id"] = ObjectId(client_id)
            
        if date_from:
            filter_query["created_at"] = {"$gte": datetime.combine(date_from, datetime.min.time())}
            
        if date_to:
            if "created_at" in filter_query:
                filter_query["created_at"]["$lte"] = datetime.combine(date_to, datetime.max.time())
            else:
                filter_query["created_at"] = {"$lte": datetime.combine(date_to, datetime.max.time())}

        # Get total count
        total = await db.sales.count_documents(filter_query)

        # Get sales with pagination
        skip = (page - 1) * size
        cursor = db.sales.find(filter_query).skip(skip).limit(size).sort("created_at", -1)
        sales_data = await cursor.to_list(length=size)

        sales = []
        for sale in sales_data:
            # Get user information for cashier_id field
            cashier_name = "System"
            if sale.get("cashier_id"):
                try:
                    # Handle both ObjectId and string formats
                    cashier_id = sale["cashier_id"]
                    if isinstance(cashier_id, str) and cashier_id:
                        cashier_id = ObjectId(cashier_id)
                    elif isinstance(cashier_id, ObjectId):
                        pass  # Already an ObjectId
                    else:
                        cashier_id = None

                    if cashier_id:
                        user = await db.users.find_one({"_id": cashier_id})
                        if user:
                            cashier_name = user.get("full_name", "Staff Member")
                except:
                    cashier_name = "Staff Member"

            client_phone = sale.get("client_phone", "")
            client_id = sale.get("client_id")
            if client_id:
                try:
                    if isinstance(client_id, str):
                        client_id = ObjectId(client_id)
                    
                    client = await db.customers.find_one({"_id": client_id})
                    if client and client.get("phone"):
                        client_phone = client.get("phone")
                except Exception:
                    pass # Ignore if client_id is invalid or client not found

            sales.append({
                "id": str(sale["_id"]),
                "sale_number": sale["sale_number"],
                "customer_id": str(sale.get("customer_id", "")),
                "customer_name": sale.get("customer_name", "Walk-in Customer"),
                "customer_email": sale.get("customer_email", ""),
                "customer_phone": client_phone,
                "items": sale["items"],
                "subtotal": sale["subtotal"],
                "tax_amount": sale.get("tax_amount", 0),
                "discount_amount": sale.get("discount_amount", 0),
                "total_amount": sale["total_amount"],
                "total_profit": sale.get("total_profit", 0),
                "status": sale["status"],
                "payment_method": sale.get("payment_method", "cash"),
                "payment_received": sale.get("payment_received", 0),
                "change_given": sale.get("change_given", 0),
                "notes": sale.get("notes", ""),
                "created_at": sale["created_at"].isoformat(),
                "updated_at": sale.get("updated_at", sale["created_at"]).isoformat(),
                "cashier_id": str(sale.get("cashier_id", "")),
                "cashier_name": cashier_name
            })

        return {
            "sales": sales,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve sales: {str(e)}"
        )


@router.get("/stats")
async def get_sales_stats():
    """Get sales statistics"""
    try:
        db = await get_database()

        # Count sales using aggregation
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total_sales": {"$sum": 1},
                    "completed_sales": {
                        "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                    },
                    "pending_sales": {
                        "$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}
                    },
                    "total_revenue": {"$sum": "$total_amount"},
                    "total_profit": {"$sum": "$total_profit"}
                }
            }
        ]

        result = await db.sales.aggregate(pipeline).to_list(1)

        if result:
            stats = result[0]
            return {
                "total_sales": stats.get("total_sales", 0),
                "completed_sales": stats.get("completed_sales", 0),
                "pending_sales": stats.get("pending_sales", 0),
                "total_revenue": stats.get("total_revenue", 0),
                "total_profit": stats.get("total_profit", 0)
            }
        else:
            return {
                "total_sales": 0,
                "completed_sales": 0,
                "pending_sales": 0,
                "total_revenue": 0,
                "total_profit": 0
            }

    except Exception as e:
        print(f"Stats API Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "total_sales": 0,
            "completed_sales": 0,
            "pending_sales": 0,
            "total_revenue": 0,
            "total_profit": 0
        }


@router.get("/export")
async def export_sales(
    date_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="End date (YYYY-MM-DD)")
):
    """Export sales to CSV with optional date range filtering"""
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

        # Get sales with optional date filtering
        sales_data = await db.sales.find(filter_query).sort("created_at", -1).to_list(None)

        # Prepare CSV data
        csv_data = []
        csv_data.append([
            "Sale Number", "Customer Name", "Customer Phone", "Items Details",
            "Subtotal", "Discount", "Total", "Profit", "Status", "Payment Method",
            "Payment Received", "Change Given", "Created At", "Processed By"
        ])

        for sale in sales_data:
            # Get user information for cashier_id field
            cashier_name = "System"
            if sale.get("cashier_id"):
                try:
                    cashier_id = sale["cashier_id"]
                    if isinstance(cashier_id, str) and cashier_id:
                        cashier_id = ObjectId(cashier_id)
                    elif isinstance(cashier_id, ObjectId):
                        pass
                    else:
                        cashier_id = None

                    if cashier_id:
                        user = await db.users.find_one({"_id": cashier_id})
                        if user:
                            cashier_name = user.get("full_name", "Staff Member")
                except:
                    cashier_name = "Staff Member"

            # Format items details
            items_details = ""
            if sale.get("items"):
                item_strings = []
                for item in sale["items"]:
                    item_name = item.get("product_name", "Unknown Item")
                    item_sku = item.get("sku", "")
                    item_qty = item.get("quantity", 0)
                    item_price = item.get("unit_price", 0)
                    item_total = item.get("total_price", 0)

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
                sale.get("sale_number", ""),
                sale.get("customer_name", "Walk-in Customer"),
                sale.get("customer_phone", ""),
                items_details,
                sale.get("subtotal", 0),
                sale.get("discount_amount", 0),
                sale.get("total_amount", 0),
                sale.get("total_profit", 0),
                sale.get("status", ""),
                sale.get("payment_method", "cash"),
                sale.get("payment_received", 0),
                sale.get("change_given", 0),
                sale.get("created_at", "").strftime("%Y-%m-%d %H:%M:%S") if sale.get("created_at") else "",
                cashier_name
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
            headers={"Content-Disposition": "attachment; filename=sales_export.csv"}
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export sales: {str(e)}"
        )


@router.get("/{sale_id}", response_model=dict)
async def get_sale(sale_id: str):
    """Get a specific sale by ID"""
    try:
        db = await get_database()
        
        sale = await db.sales.find_one({"_id": ObjectId(sale_id)})
        if not sale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sale not found"
            )

        # Get user information for cashier_id field
        cashier_name = "System"
        if sale.get("cashier_id"):
            try:
                # Handle both ObjectId and string formats
                cashier_id = sale["cashier_id"]
                if isinstance(cashier_id, str) and cashier_id:
                    cashier_id = ObjectId(cashier_id)
                elif isinstance(cashier_id, ObjectId):
                    pass  # Already an ObjectId
                else:
                    cashier_id = None

                if cashier_id:
                    user = await db.users.find_one({"_id": cashier_id})
                    if user:
                        cashier_name = user.get("full_name", "Staff Member")
            except:
                cashier_name = "Staff Member"

        return {
            "id": str(sale["_id"]),
            "sale_number": sale["sale_number"],
            "customer_id": str(sale.get("customer_id", "")),
            "customer_name": sale.get("customer_name", "Walk-in Customer"),
            "customer_email": sale.get("customer_email", ""),
            "customer_phone": sale.get("customer_phone", ""),
            "items": sale["items"],
            "subtotal": sale["subtotal"],
            "tax_amount": sale.get("tax_amount", 0),
            "discount_amount": sale.get("discount_amount", 0),
            "total_amount": sale["total_amount"],
            "total_profit": sale.get("total_profit", 0),
            "status": sale["status"],
            "payment_method": sale.get("payment_method", "cash"),
            "payment_received": sale.get("payment_received", 0),
            "change_given": sale.get("change_given", 0),
            "notes": sale.get("notes", ""),
            "created_at": sale["created_at"].isoformat(),
            "updated_at": sale.get("updated_at", sale["created_at"]).isoformat(),
            "cashier_id": str(sale.get("cashier_id", "")),
            "cashier_name": cashier_name
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve sale: {str(e)}"
        )


@router.put("/{sale_id}/status")
async def update_sale_status(
    sale_id: str,
    status_data: dict,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Update sale status"""
    try:

        db = await get_database()

        # Validate sale exists
        sale = await db.sales.find_one({"_id": ObjectId(sale_id)})
        if not sale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sale not found"
            )

        new_status = status_data.get("status")
        if not new_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status is required"
            )

        # Validate status
        valid_statuses = ["pending", "completed", "cancelled", "refunded"]
        if new_status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )

        # Update sale status
        update_data = {
            "status": new_status,
            "updated_at": datetime.utcnow()
        }

        result = await db.sales.update_one(
            {"_id": ObjectId(sale_id)},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update sale status"
            )

        return {
            "success": True,
            "message": f"Sale status updated to {new_status}",
            "sale_id": sale_id,
            "new_status": new_status
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update sale status: {str(e)}"
        )
@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_sale(
    sale_data: dict,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create a new sale"""
    try:
        db = await get_database()
        
        # Validate required fields
        required_fields = ["sale_number", "items", "subtotal", "total_amount", "payment_method"]
        for field in required_fields:
            if field not in sale_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required field: {field}"
                )
        
        # Validate items
        if not sale_data.get("items") or len(sale_data["items"]) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one item is required"
            )
        
        # Calculate profit for each item and total profit
        total_profit = 0
        for item in sale_data["items"]:
            # Calculate item profit: (unit_price - cost_price) * quantity - discount_amount
            unit_profit = item.get("unit_price", 0) - item.get("cost_price", 0)
            item_profit = (unit_profit * item.get("quantity", 0)) - item.get("discount_amount", 0)
            item["profit"] = max(0, item_profit)  # Ensure profit is not negative
            total_profit += item["profit"]
        
        # Add tracking information
        sale_data["cashier_id"] = current_user.id
        sale_data["cashier_name"] = current_user.full_name
        sale_data["created_at"] = datetime.utcnow()
        sale_data["updated_at"] = datetime.utcnow()
        sale_data["total_profit"] = total_profit
        
        # Set default status if not provided
        if "status" not in sale_data:
            sale_data["status"] = "completed"
        
        # Insert sale into database
        result = await db.sales.insert_one(sale_data)
        
        if result.inserted_id:
            return {
                "success": True,
                "message": "Sale created successfully",
                "sale_id": str(result.inserted_id)
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create sale"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create sale: {str(e)}"
        )


@router.delete("/{sale_id}", response_model=dict)
async def delete_sale(
    sale_id: str,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Delete a sale by ID"""
    try:
        db = await get_database()
        
        # Check if sale exists
        sale = await db.sales.find_one({"_id": ObjectId(sale_id)})
        if not sale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sale not found"
            )
        
        # Check if user has permission to delete (only admins or the creator)
        if current_user.role != "admin" and str(sale.get("cashier_id")) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this sale"
            )
        
        # Delete sale
        result = await db.sales.delete_one({"_id": ObjectId(sale_id)})
        
        if result.deleted_count == 1:
            return {
                "success": True,
                "message": "Sale deleted successfully"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete sale"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete sale: {str(e)}"
        )