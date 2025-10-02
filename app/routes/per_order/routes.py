from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from bson import ObjectId
from ...models import User, PerOrder
from ...utils.auth import get_current_user_hybrid
from ...config.database import get_database
from typing import Optional

import json
from bson import json_util

per_order_routes = APIRouter(prefix="/per-order", tags=["Per Order Web"])
templates = Jinja2Templates(directory="app/templates")

@per_order_routes.get("/{per_order_id}", response_class=HTMLResponse)
async def per_order_detail_page(request: Request, per_order_id: str, current_user: User = Depends(get_current_user_hybrid)):
    """Display detailed per order page"""

    try:
        db = await get_database()

        # Validate per order ID
        if not ObjectId.is_valid(per_order_id):
            return RedirectResponse(url="/per-order?error=Invalid per order ID", status_code=302)

        # Get per order details
        per_order = await db.per_orders.find_one({"_id": ObjectId(per_order_id)})

        if not per_order:
            return RedirectResponse(url="/per-order?error=Per order not found", status_code=302)

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
            
        # Ensure payments are properly serialized
        if 'payments' in per_order and isinstance(per_order['payments'], list):
            for payment in per_order['payments']:
                if isinstance(payment, dict) and 'method' in payment:
                    # Handle both enum and string cases
                    if hasattr(payment['method'], 'value'):
                        payment['method'] = payment['method'].value
                    elif not isinstance(payment['method'], str):
                        payment['method'] = str(payment['method'])
        
        # Debug: Print payment information
        print(f"DEBUG: Payment info for order {per_order.get('order_number', 'Unknown')}: {per_order.get('payments', 'No payments')}")

        # Get additional customer information if customer_id exists
        customer_info = None
        if per_order.get("customer_id"):
            try:
                customer_info = await db.customers.find_one({"_id": ObjectId(per_order["customer_id"])})
            except Exception:
                pass  # Continue without customer info if there's an error

        # Get creator information
        created_by_user = None
        if per_order.get("created_by"):
            try:
                created_by_user = await db.users.find_one({"_id": ObjectId(per_order["created_by"])})
            except Exception:
                pass

        # Get assigned user information if assigned_to exists
        assigned_user = None
        if per_order.get("assigned_to"):
            try:
                assigned_user = await db.users.find_one({"_id": ObjectId(per_order["assigned_to"])})
            except Exception:
                pass

        # Get original order information if original_order_id exists
        original_order = None
        if per_order.get("original_order_id"):
            try:
                original_order = await db.orders.find_one({"_id": ObjectId(per_order["original_order_id"])})
            except Exception:
                pass

        # Prepare context data
        context = {
            "request": request,
            "user": current_user,
            "per_order": per_order,
            "customer_info": customer_info,
            "created_by_user": created_by_user,
            "assigned_user": assigned_user,
            "original_order": original_order
        }

        return templates.TemplateResponse(
            "per_order/index.html",
            context
        )
        
    except Exception as e:
        print(f"Error loading per order detail: {e}")
        return RedirectResponse(url="/per-order?error=Failed to load per order details", status_code=302)


@per_order_routes.get("/", response_class=HTMLResponse)
async def per_order_list_page(request: Request, current_user: User = Depends(get_current_user_hybrid)):
    """Display per orders list page"""
    db = await get_database()
    per_orders = await db.per_orders.find().sort("created_at", -1).to_list(length=100)

    # Convert ObjectId to string for JSON serialization
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
    
    # Ensure payments are properly serialized
    for order in per_orders_serializable:
        if 'payments' in order and isinstance(order['payments'], list):
            for payment in order['payments']:
                if isinstance(payment, dict) and 'method' in payment and hasattr(payment['method'], 'value'):
                    payment['method'] = payment['method'].value

    context = {
        "request": request,
        "user": current_user,
        "per_orders": per_orders_serializable,
        "per_orders_json": json.loads(json_util.dumps(per_orders_serializable)),
        "per_order": None # Explicitly set per_order to None for the list view
    }

    return templates.TemplateResponse(
        "per_order/index.html",
        context
    )