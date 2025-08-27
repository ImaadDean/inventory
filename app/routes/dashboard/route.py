from fastapi import APIRouter, Request, Depends, HTTPException, status, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from ...utils.timezone import now_kampala, kampala_to_utc, get_day_start
from typing import Optional
from ...config.database import get_database
from ...models import User
from ...utils.auth import get_current_user, verify_token, get_user_by_username
from ...schemas.dashboard import SalesOverview, InventoryOverview, TopSellingProduct

templates = Jinja2Templates(directory="app/templates")
dashboard_routes = APIRouter(prefix="/dashboard", tags=["Dashboard Web"])


async def get_current_user_from_cookie(request: Request):
    """Get current user from cookie for HTML routes"""
    access_token = request.cookies.get("access_token")
    if not access_token:
        return None

    if access_token.startswith("Bearer "):
        token = access_token[7:]
    else:
        token = access_token

    payload = verify_token(token)
    if not payload:
        return None

    username = payload.get("sub")
    if not username:
        return None

    user = await get_user_by_username(username)
    return user


async def get_dashboard_data():
    """Get dashboard data for HTML templates"""
    db = await get_database()

    # Get today's date range in EAT
    today_start = kampala_to_utc(get_day_start())
    today_end = kampala_to_utc(get_day_start() + timedelta(days=1) - timedelta(microseconds=1))

    # Sales overview for today
    sales_pipeline = [
        {"$match": {"created_at": {"$gte": today_start, "$lte": today_end}}},
        {"$group": {
            "_id": None,
            "total_sales": {"$sum": "$total"},
            "total_transactions": {"$sum": 1},
            "total_items": {"$sum": {"$sum": "$items.quantity"}}
        }}
    ]

    sales_cursor = db.orders.aggregate(sales_pipeline)
    sales_data = await sales_cursor.to_list(length=1)

    if sales_data:
        sales_info = sales_data[0]
        avg_transaction = sales_info["total_sales"] / sales_info["total_transactions"] if sales_info["total_transactions"] > 0 else 0
        sales_overview = {
            "total_sales": sales_info["total_sales"],
            "total_transactions": sales_info["total_transactions"],
            "average_transaction_value": avg_transaction,
            "total_items_sold": sales_info["total_items"]
        }
    else:
        sales_overview = {
            "total_sales": 0.0,
            "total_transactions": 0,
            "average_transaction_value": 0.0,
            "total_items_sold": 0
        }

    # Inventory overview
    inventory_pipeline = [
        {"$group": {
            "_id": None,
            "total_products": {"$sum": 1},
            "active_products": {"$sum": {"$cond": [{"$eq": ["$is_active", True]}, 1, 0]}},
            "low_stock_products": {"$sum": {"$cond": [{"$lte": ["$stock_quantity", "$min_stock_level"]}, 1, 0]}},
            "out_of_stock_products": {"$sum": {"$cond": [{"$eq": ["$stock_quantity", 0]}, 1, 0]}},
            "total_inventory_value": {"$sum": {"$multiply": ["$stock_quantity", "$cost_price"]}}
        }}
    ]

    inventory_cursor = db.products.aggregate(inventory_pipeline)
    inventory_data = await inventory_cursor.to_list(length=1)

    if inventory_data:
        inv_info = inventory_data[0]
        inventory_overview = {
            "total_products": inv_info["total_products"],
            "active_products": inv_info["active_products"],
            "low_stock_products": inv_info["low_stock_products"],
            "out_of_stock_products": inv_info["out_of_stock_products"],
            "total_inventory_value": inv_info["total_inventory_value"]
        }
    else:
        inventory_overview = {
            "total_products": 0,
            "active_products": 0,
            "low_stock_products": 0,
            "out_of_stock_products": 0,
            "total_inventory_value": 0.0
        }

    # Recent activity (last 24 hours in Kampala timezone)
    kampala_now = now_kampala()
    twenty_four_hours_ago_kampala = kampala_now - timedelta(hours=24)
    twenty_four_hours_ago = kampala_to_utc(twenty_four_hours_ago_kampala)

    # Recent sales count
    recent_sales_count = await db.orders.count_documents({
        "created_at": {"$gte": twenty_four_hours_ago}
    })

    # Recent products added
    recent_products_count = await db.products.count_documents({
        "created_at": {"$gte": twenty_four_hours_ago}
    })

    # Recent clients added
    recent_clients_count = await db.customers.count_documents({
        "created_at": {"$gte": twenty_four_hours_ago}
    })

    # Products that went out of stock recently
    out_of_stock_count = await db.products.count_documents({
        "stock_quantity": 0,
        "is_active": True
    })

    # Products restocked recently (stock increased in last 24 hours)
    # This would require tracking stock changes, for now we'll use a placeholder
    recent_restocks_count = 0

    # Top selling products (last 30 days)
    thirty_days_ago = kampala_to_utc(now_kampala() - timedelta(days=30))
    top_products_pipeline = [
        {"$match": {"created_at": {"$gte": thirty_days_ago}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.product_id",
            "product_name": {"$first": "$items.product_name"},
            "sku": {"$first": "$items.sku"},
            "quantity_sold": {"$sum": "$items.quantity"},
            "total_revenue": {"$sum": "$items.total_price"}
        }},
        {"$sort": {"quantity_sold": -1}},
        {"$limit": 4},
        {
            "$addFields": {
                "product_oid": {
                    "$cond": {
                        "if": {"$eq": [{"$type": "$_id"}, "string"]},
                        "then": {"$toObjectId": "$_id"},
                        "else": "$_id"
                    }
                }
            }
        },
        {
            "$lookup": {
                "from": "products",
                "localField": "product_oid",
                "foreignField": "_id",
                "as": "product_details"
            }
        },
        {
            "$addFields": {
                "product_price": {
                    "$ifNull": [
                        {"$arrayElemAt": ["$product_details.price", 0]},
                        0
                    ]
                }
            }
        }
    ]

    top_products_cursor = db.orders.aggregate(top_products_pipeline)
    top_products_data = await top_products_cursor.to_list(length=5)

    top_selling_products = [
        {
            "product_id": str(product["_id"]),
            "product_name": product["product_name"],
            "sku": product["sku"],
            "quantity_sold": product["quantity_sold"],
            "total_revenue": product["total_revenue"],
            "price": product.get("product_price", 0)
        }
        for product in top_products_data
    ]

    return {
        "sales_overview": sales_overview,
        "inventory_overview": inventory_overview,
        "recent_sales_count": recent_sales_count,
        "recent_products_count": recent_products_count,
        "recent_clients_count": recent_clients_count,
        "out_of_stock_count": out_of_stock_count,
        "recent_restocks_count": recent_restocks_count,
        "low_stock_alerts": inventory_overview["low_stock_products"],
        "top_selling_products": top_selling_products
    }


@dashboard_routes.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Display main dashboard page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Block cashiers from accessing dashboard
    if current_user.role == "cashier":
        return RedirectResponse(url="/pos", status_code=302)

    try:
        # Get dashboard data directly from the function
        dashboard_data = await get_dashboard_data()

        return templates.TemplateResponse(
            "dashboard/index.html",
            {
                "request": request,
                "user": current_user,
                "dashboard": dashboard_data
            }
        )
    except Exception as e:
        print(f"Dashboard error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard")


@dashboard_routes.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    """Display reports page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Block cashiers from accessing reports
    if current_user.role == "cashier":
        return RedirectResponse(url="/pos", status_code=302)

    return templates.TemplateResponse(
        "dashboard/reports.html",
        {"request": request, "user": current_user}
    )