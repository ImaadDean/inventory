from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional
from datetime import datetime, timedelta
from bson import ObjectId
from ...config.database import get_database
from ...schemas.dashboard import (
    ReportPeriod, SalesReport, InventoryReport, DashboardSummary,
    SalesOverview, InventoryOverview, TopSellingProduct, LowStockProduct
)
from ...models import User
from ...utils.auth import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard & Reports API"])


def get_date_range(period: ReportPeriod, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None):
    """Get start and end dates for the specified period"""
    now = datetime.utcnow()

    if period == ReportPeriod.TODAY:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == ReportPeriod.YESTERDAY:
        yesterday = now - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == ReportPeriod.THIS_WEEK:
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == ReportPeriod.LAST_WEEK:
        start = now - timedelta(days=now.weekday() + 7)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=6)
        end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == ReportPeriod.THIS_MONTH:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == ReportPeriod.LAST_MONTH:
        first_day_this_month = now.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        start = last_day_last_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = last_day_last_month.replace(hour=23, minute=59, second=59, microsecond=999999)
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

    return start, end


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(current_user: User = Depends(get_current_user)):
    """Get dashboard summary with key metrics"""
    db = await get_database()

    # Get today's date range
    today_start, today_end = get_date_range(ReportPeriod.TODAY)

    # Sales overview for today
    sales_pipeline = [
        {"$match": {"created_at": {"$gte": today_start, "$lte": today_end}}},
        {"$group": {
            "_id": None,
            "total_sales": {"$sum": "$total_amount"},
            "total_transactions": {"$sum": 1},
            "total_items": {"$sum": {"$sum": "$items.quantity"}}
        }}
    ]

    sales_cursor = db.sales.aggregate(sales_pipeline)
    sales_data = await sales_cursor.to_list(length=1)

    if sales_data:
        sales_info = sales_data[0]
        avg_transaction = sales_info["total_sales"] / sales_info["total_transactions"] if sales_info["total_transactions"] > 0 else 0
        sales_overview = SalesOverview(
            total_sales=sales_info["total_sales"],
            total_transactions=sales_info["total_transactions"],
            average_transaction_value=avg_transaction,
            total_items_sold=sales_info["total_items"]
        )
    else:
        sales_overview = SalesOverview(
            total_sales=0.0,
            total_transactions=0,
            average_transaction_value=0.0,
            total_items_sold=0
        )

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
        inventory_overview = InventoryOverview(
            total_products=inv_info["total_products"],
            active_products=inv_info["active_products"],
            low_stock_products=inv_info["low_stock_products"],
            out_of_stock_products=inv_info["out_of_stock_products"],
            total_inventory_value=inv_info["total_inventory_value"]
        )
    else:
        inventory_overview = InventoryOverview(
            total_products=0,
            active_products=0,
            low_stock_products=0,
            out_of_stock_products=0,
            total_inventory_value=0.0
        )

    # Recent sales count (last 24 hours)
    recent_sales_count = await db.sales.count_documents({
        "created_at": {"$gte": datetime.utcnow() - timedelta(hours=24)}
    })

    # Top selling products (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
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
        {"$limit": 5}
    ]

    top_products_cursor = db.sales.aggregate(top_products_pipeline)
    top_products_data = await top_products_cursor.to_list(length=5)

    top_selling_products = [
        TopSellingProduct(
            product_id=str(product["_id"]),
            product_name=product["product_name"],
            sku=product["sku"],
            quantity_sold=product["quantity_sold"],
            total_revenue=product["total_revenue"]
        )
        for product in top_products_data
    ]

    return DashboardSummary(
        sales_overview=sales_overview,
        inventory_overview=inventory_overview,
        recent_sales_count=recent_sales_count,
        low_stock_alerts=inventory_overview.low_stock_products,
        top_selling_products=top_selling_products
    )