from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional
from datetime import datetime, timedelta
from ...utils.timezone import now_kampala, kampala_to_utc, get_day_start, get_week_start, get_month_start, get_year_start
from bson import ObjectId
from ...config.database import get_database
from ...schemas.dashboard import (
    ReportPeriod, SalesReport, InventoryReport, DashboardSummary,
    SalesOverview, InventoryOverview, TopSellingProduct, LowStockProduct
)
from ...models import User
from ...utils.auth import get_current_user, get_current_user_hybrid_dependency

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard & Reports API"])


def get_date_range(period: ReportPeriod, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None):
    """Get start and end dates for the specified period in Kampala timezone"""
    now = now_kampala()

    if period == ReportPeriod.TODAY:
        start = get_day_start(now)
        end = now
    elif period == ReportPeriod.YESTERDAY:
        yesterday = now - timedelta(days=1)
        start = get_day_start(yesterday)
        end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == ReportPeriod.THIS_WEEK:
        start = get_week_start(now)
        end = now
    elif period == ReportPeriod.LAST_WEEK:
        last_week = now - timedelta(days=7)
        start = get_week_start(last_week)
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    elif period == ReportPeriod.THIS_MONTH:
        start = get_month_start(now)
        end = now
    elif period == ReportPeriod.LAST_MONTH:
        last_month = now - timedelta(days=30)
        start = get_month_start(last_month)
        # Get last day of that month
        next_month = start.replace(month=start.month + 1) if start.month < 12 else start.replace(year=start.year + 1, month=1)
        end = next_month - timedelta(days=1)
        end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == ReportPeriod.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start date and end date are required for custom period"
            )
        start = start_date
        end = end_date
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid period"
        )

    # Convert Kampala timezone dates to UTC for database queries
    start_utc = kampala_to_utc(start)
    end_utc = kampala_to_utc(end)

    return start_utc, end_utc


@router.get("/summary")
async def get_dashboard_summary(current_user: User = Depends(get_current_user_hybrid_dependency())):
    """Get dashboard summary with key metrics"""
    db = await get_database()

    # Get today's date range
    today_start, today_end = get_date_range(ReportPeriod.TODAY)

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
            "total_inventory_value": {"$sum": {"$multiply": ["$stock_quantity", "$price"]}}
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

    # Recent activity (last 24 hours)
    twenty_four_hours_ago = kampala_to_utc(now_kampala() - timedelta(hours=24))

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
            "product_name": {"$first": "$items.name"},
            "sku": {"$first": "$items.sku"},
            "quantity_sold": {"$sum": "$items.quantity"},
            "total_revenue": {"$sum": "$items.total"}
        }},
        {"$sort": {"quantity_sold": -1}},
        {"$limit": 4}
    ]

    top_products_cursor = db.orders.aggregate(top_products_pipeline)
    top_products_data = await top_products_cursor.to_list(length=5)

    top_selling_products = [
        {
            "product_id": str(product["_id"]),
            "product_name": product["product_name"],
            "sku": product["sku"],
            "quantity_sold": product["quantity_sold"],
            "total_revenue": product["total_revenue"]
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


@router.get("/sales-chart")
async def get_sales_chart_data(current_user: User = Depends(get_current_user_hybrid_dependency())):
    """Get sales data for the last 7 days for chart display"""
    db = await get_database()

    # Get last 7 days of sales data using Kampala timezone
    sales_data = []
    labels = []

    now = now_kampala()

    for i in range(6, -1, -1):  # 6 days ago to today
        # Get the date in Kampala timezone
        kampala_date = now - timedelta(days=i)
        day_start = get_day_start(kampala_date)
        day_end = kampala_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Convert to UTC for database query
        day_start_utc = kampala_to_utc(day_start)
        day_end_utc = kampala_to_utc(day_end)

        # Get orders for this day (using orders collection instead of sales)
        orders_pipeline = [
            {"$match": {"created_at": {"$gte": day_start_utc, "$lte": day_end_utc}}},
            {"$group": {
                "_id": None,
                "total_sales": {"$sum": "$total"}
            }}
        ]

        orders_cursor = db.orders.aggregate(orders_pipeline)
        day_sales = await orders_cursor.to_list(length=1)

        daily_total = day_sales[0]["total_sales"] if day_sales else 0
        sales_data.append(daily_total)

        # Format day label
        if i == 0:
            labels.append("Today")
        elif i == 1:
            labels.append("Yesterday")
        else:
            labels.append(kampala_date.strftime("%a"))  # Mon, Tue, etc.

    # Debug information
    print(f"Sales chart data: {sales_data}")
    print(f"Labels: {labels}")
    print(f"Total revenue: {sum(sales_data)}")

    return {
        "success": True,
        "sales_data": sales_data,
        "labels": labels,
        "total_revenue": sum(sales_data)
    }


@router.get("/top-products-chart")
async def get_top_products_chart_data(current_user: User = Depends(get_current_user_hybrid_dependency())):
    """Get top selling products in the last 7 days for chart display"""
    db = await get_database()

    # Get last 7 days date range
    now = now_kampala()
    seven_days_ago = now - timedelta(days=7)
    start_utc = kampala_to_utc(get_day_start(seven_days_ago))
    end_utc = kampala_to_utc(now)

    # Get top selling products from orders in last 7 days
    top_products_pipeline = [
        {"$match": {"created_at": {"$gte": start_utc, "$lte": end_utc}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.product_id",
            "product_name": {"$first": "$items.name"},
            "sku": {"$first": "$items.sku"},
            "quantity_sold": {"$sum": "$items.quantity"},
            "total_sales": {"$sum": "$items.total"}
        }},
        {"$sort": {"total_sales": -1}},
        {"$limit": 8}  # Top 8 products for better chart display
    ]

    top_products_cursor = db.orders.aggregate(top_products_pipeline)
    top_products_data = await top_products_cursor.to_list(length=8)

    product_names = []
    sales_amounts = []

    for product in top_products_data:
        # Truncate long product names for better display
        product_name = product["product_name"] if product["product_name"] else "Unknown Product"
        if len(product_name) > 20:
            product_name = product_name[:17] + "..."

        product_names.append(product_name)
        sales_amounts.append(product["total_sales"])

    # If no products found, return default
    if not product_names:
        product_names = ["No sales data"]
        sales_amounts = [0]

    # Debug information
    print(f"Top products chart data: {product_names}")
    print(f"Sales amounts: {sales_amounts}")
    print(f"Total sales: {sum(sales_amounts)}")

    return {
        "success": True,
        "product_names": product_names,
        "sales_amounts": sales_amounts,
        "total_sales": sum(sales_amounts)
    }