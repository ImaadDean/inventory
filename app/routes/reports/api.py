from fastapi import APIRouter, Depends
from ...config.database import get_database
from ...utils.timezone import now_kampala, get_day_start, get_week_start, get_month_start
from datetime import datetime, timedelta

reports_api_router = APIRouter()

@reports_api_router.get("/stats")
async def get_report_stats(db=Depends(get_database)):
    """
    Get key statistics for the reports dashboard.
    """
    now = now_kampala()
    today_start = get_day_start(now)
    week_start = get_week_start(now)
    month_start = get_month_start(now)

    # --- Aggregation Pipelines ---

    # Sales pipeline with improved profit calculation
    def get_sales_pipeline(start_date, end_date):
        return [
            {"$match": {"created_at": {"$gte": start_date, "$lt": end_date}, "status": "completed"}},
            {"$unwind": "$items"},
            {"$lookup": {
                "from": "products",
                "localField": "items.product_id",
                "foreignField": "_id",
                "as": "product_info"
            }},
            {"$unwind": "$product_info"},
            {"$addFields": {
                "calculated_cost": {
                    "$cond": {
                        "if": {"$eq": ["$product_info.is_decant", True]},
                        # For decants: (original_cost / original_volume) * decant_volume
                        "then": {
                            "$multiply": [
                                {"$divide": ["$product_info.original_cost", "$product_info.original_volume"]},
                                "$product_info.decant_volume"
                            ]
                        },
                        # For regular products: use cost_price directly
                        "else": "$items.cost_price"
                    }
                },
                "item_discount": {"$ifNull": ["$items.discount", 0]},
                "item_profit": {
                    "$subtract": [
                        "$items.total_price",
                        {
                            "$add": [
                                {
                                    "$cond": {
                                        "if": {"$eq": ["$product_info.is_decant", True]},
                                        "then": {
                                            "$multiply": [
                                                {"$divide": ["$product_info.original_cost", "$product_info.original_volume"]},
                                                "$product_info.decant_volume"
                                            ]
                                        },
                                        "else": "$items.cost_price"
                                    }
                                },
                                {"$ifNull": ["$items.discount", 0]}
                            ]
                        }
                    ]
                }
            }},
            {"$group": {
                "_id": None,
                "total_revenue": {"$sum": "$items.total_price"},
                "total_cost": {"$sum": "$calculated_cost"},
                "total_discount": {"$sum": "$item_discount"},
                "total_profit": {"$sum": "$item_profit"},
                "orders": {"$addToSet": "$_id"},
                "customers": {"$addToSet": "$customer_id"}
            }},
            {"$project": {
                "_id": 0,
                "revenue": "$total_revenue",
                "profit": "$total_profit",
                "total_cost": "$total_cost",
                "total_discount": "$total_discount",
                "orders": {"$size": "$orders"},
                "customers": {"$size": "$customers"}
            }}
        ]

    # --- Helper to run aggregation ---
    async def run_sales_aggregation(pipeline):
        result = await db.sales.aggregate(pipeline).to_list(1)
        return result[0] if result else {
            "revenue": 0, 
            "profit": 0, 
            "total_cost": 0, 
            "total_discount": 0, 
            "orders": 0, 
            "customers": 0
        }

    # --- Calculate stats for different periods ---
    today_stats = await run_sales_aggregation(get_sales_pipeline(today_start, now))
    week_stats = await run_sales_aggregation(get_sales_pipeline(week_start, now))
    month_stats = await run_sales_aggregation(get_sales_pipeline(month_start, now))

    # --- Total Stats ---
    total_orders_pipeline = [
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }}
    ]
    total_orders_result = await db.sales.aggregate(total_orders_pipeline).to_list(None)
    
    total_orders = 0
    incomplete_orders = 0
    for res in total_orders_result:
        if res['_id'] == 'completed':
            total_orders = res['count']
        else:
            incomplete_orders += res['count']

    total_products = await db.products.count_documents({})
    total_customers = await db.customers.count_documents({})

    total_stats = {
        "orders": total_orders,
        "incomplete_orders": incomplete_orders,
        "products": total_products,
        "customers": total_customers
    }

    return {
        "today": today_stats,
        "week": week_stats,
        "month": month_stats,
        "total": total_stats
    }
