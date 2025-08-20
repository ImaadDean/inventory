from fastapi import APIRouter, Depends, Query
from ...config.database import get_database
from ...utils.timezone import now_kampala, get_day_start, get_week_start, get_month_start
from datetime import datetime, timedelta, date
from typing import Optional

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


@reports_api_router.get("/sales-data")
async def get_sales_data(
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db=Depends(get_database)
):
    """
    Get sales data for reports page including:
    - Today's sales
    - Payment method breakdown (cash, mobile money, etc.)
    - Cashier-specific sales data
    - Data for charts and tables
    """
    try:
        # Use provided dates or default to today
        if from_date and to_date:
            # Convert to datetime with EAT timezone handling
            from_datetime = datetime.combine(from_date, datetime.min.time())
            to_datetime = datetime.combine(to_date, datetime.max.time())
        else:
            # Default to today
            today = now_kampala().date()
            from_datetime = datetime.combine(today, datetime.min.time())
            to_datetime = datetime.combine(today, datetime.max.time())
        
        # Convert to UTC for database queries
        from_utc = get_today_start_utc().replace(
            year=from_datetime.year,
            month=from_datetime.month,
            day=from_datetime.day
        )
        to_utc = get_today_end_utc().replace(
            year=to_datetime.year,
            month=to_datetime.month,
            day=to_datetime.day
        )
        
        # Match criteria for sales
        match_criteria = {
            "created_at": {"$gte": from_utc, "$lte": to_utc},
            "status": "completed"
        }
        
        # Get sales data with payment method breakdown and profit calculation
        sales_pipeline = [
            {"$match": match_criteria},
            {"$unwind": "$items"},
            {"$lookup": {
                "from": "products",
                "localField": "items.product_id",
                "foreignField": "_id",
                "as": "product_info"
            }},
            {"$unwind": "$product_info"},
            {"$addFields": {
                "item_cost": {
                    "$cond": [
                        {"$eq": ["$product_info.is_decant", True]},
                        {
                            "$multiply": [
                                {"$divide": ["$product_info.original_cost", "$product_info.original_volume"]},
                                "$product_info.decant_volume"
                            ]
                        },
                        "$product_info.cost_price"
                    ]
                },
                "item_profit": {
                    "$subtract": [
                        {"$subtract": ["$items.total_price", {"$ifNull": ["$items.discount_amount", 0]}]},
                        {
                            "$multiply": [
                                {
                                    "$cond": [
                                        {"$eq": ["$product_info.is_decant", True]},
                                        {
                                            "$multiply": [
                                                {"$divide": ["$product_info.original_cost", "$product_info.original_volume"]},
                                                "$product_info.decant_volume"
                                            ]
                                        },
                                        "$product_info.cost_price"
                                    ]
                                },
                                "$items.quantity"
                            ]
                        }
                    ]
                }
            }},
            {"$group": {
                "_id": "$_id",
                "sale_number": {"$first": "$sale_number"},
                "total_amount": {"$first": "$total_amount"},
                "payment_method": {"$first": "$payment_method"},
                "created_at": {"$first": "$created_at"},
                "cashier_name": {"$first": "$cashier_name"},
                "customer_name": {"$first": "$customer_name"},
                "items": {"$first": "$items"},
                "sale_profit": {"$sum": "$item_profit"}
            }},
            {"$group": {
                "_id": None,
                "total_revenue": {"$sum": "$total_amount"},
                "total_profit": {"$sum": "$sale_profit"},
                "total_orders": {"$sum": 1},
                "cash_total": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$payment_method", "cash"]},
                            "$total_amount",
                            0
                        ]
                    }
                },
                "mobile_money_total": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$payment_method", "mobile_money"]},
                            "$total_amount",
                            0
                        ]
                    }
                },
                "card_total": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$payment_method", "card"]},
                            "$total_amount",
                            0
                        ]
                    }
                },
                "other_payment_total": {
                    "$sum": {
                        "$cond": [
                            {"$not": {"$in": ["$payment_method", ["cash", "mobile_money", "card"]]}},
                            "$total_amount",
                            0
                        ]
                    }
                }
            }}
        ]
        
        sales_result = await db.sales.aggregate(sales_pipeline).to_list(1)
        sales_summary = sales_result[0] if sales_result else {}
        
        # Get total profit from sales summary
        profit = sales_summary.get("total_profit", 0)
        
        # Calculate previous period for growth rate
        days_diff = (to_date - from_date).days if from_date and to_date else 0
        if days_diff == 0:
            # For single day, compare to previous day
            prev_from = from_datetime - timedelta(days=1)
            prev_to = to_datetime - timedelta(days=1)
        else:
            # For date range, compare to previous period
            prev_from = from_datetime - timedelta(days=days_diff+1)
            prev_to = to_datetime - timedelta(days=days_diff+1)
            
        prev_from_utc = get_today_start_utc().replace(
            year=prev_from.year,
            month=prev_from.month,
            day=prev_from.day
        )
        prev_to_utc = get_today_end_utc().replace(
            year=prev_to.year,
            month=prev_to.month,
            day=prev_to.day
        )
        
        prev_match_criteria = {
            "created_at": {"$gte": prev_from_utc, "$lte": prev_to_utc},
            "status": "completed"
        }
        
        prev_sales_pipeline = [
            {"$match": prev_match_criteria},
            {"$group": {
                "_id": None,
                "total_revenue": {"$sum": "$total_amount"}
            }}
        ]
        
        prev_sales_result = await db.sales.aggregate(prev_sales_pipeline).to_list(1)
        prev_revenue = prev_sales_result[0]["total_revenue"] if prev_sales_result else 0
        current_revenue = sales_summary.get("total_revenue", 0)
        
        # Calculate growth rate
        if prev_revenue > 0:
            growth_rate = ((current_revenue - prev_revenue) / prev_revenue) * 100
        else:
            growth_rate = 100 if current_revenue > 0 else 0
        
        # Get cashier-specific sales data
        cashier_pipeline = [
            {"$match": match_criteria},
            {"$group": {
                "_id": "$cashier_id",
                "cashier_name": {"$first": "$cashier_name"},
                "total_sales_count": {"$sum": 1},
                "total_revenue": {"$sum": "$total_amount"},
                "cash_total": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$payment_method", "cash"]},
                            "$total_amount",
                            0
                        ]
                    }
                },
                "mobile_money_total": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$payment_method", "mobile_money"]},
                            "$total_amount",
                            0
                        ]
                    }
                }
            }}
        ]
        
        cashier_results = await db.sales.aggregate(cashier_pipeline).to_list(None)
        
        # Format cashier data
        cashier_data = []
        for result in cashier_results:
            cashier_data.append({
                "cashier_id": str(result["_id"]),
                "cashier_name": result["cashier_name"],
                "total_sales_count": result["total_sales_count"],
                "total_revenue": result["total_revenue"],
                "cash_total": result["cash_total"],
                "mobile_money_total": result["mobile_money_total"]
            })
        
        # Get sales data for table with profit calculation
        sales_table_pipeline = [
            {"$match": match_criteria},
            {"$unwind": "$items"},
            {"$lookup": {
                "from": "products",
                "localField": "items.product_id",
                "foreignField": "_id",
                "as": "product_info"
            }},
            {"$unwind": "$product_info"},
            {"$addFields": {
                "item_cost": {
                    "$cond": [
                        {"$eq": ["$product_info.is_decant", True]},
                        {
                            "$multiply": [
                                {"$divide": ["$product_info.original_cost", "$product_info.original_volume"]},
                                "$product_info.decant_volume"
                            ]
                        },
                        "$product_info.cost_price"
                    ]
                },
                "item_profit": {
                    "$subtract": [
                        {"$subtract": ["$items.total_price", {"$ifNull": ["$items.discount_amount", 0]}]},
                        {
                            "$multiply": [
                                {
                                    "$cond": [
                                        {"$eq": ["$product_info.is_decant", True]},
                                        {
                                            "$multiply": [
                                                {"$divide": ["$product_info.original_cost", "$product_info.original_volume"]},
                                                "$product_info.decant_volume"
                                            ]
                                        },
                                        "$product_info.cost_price"
                                    ]
                                },
                                "$items.quantity"
                            ]
                        }
                    ]
                }
            }},
            {"$group": {
                "_id": "$_id",
                "sale_number": {"$first": "$sale_number"},
                "customer_name": {"$first": "$customer_name"},
                "created_at": {"$first": "$created_at"},
                "total_amount": {"$first": "$total_amount"},
                "status": {"$first": "$status"},
                "items_count": {"$sum": 1},
                "sale_profit": {"$sum": "$item_profit"}
            }},
            {"$sort": {"created_at": -1}},
            {"$limit": 50}  # Limit to 50 most recent sales
        ]
        
        sales_table_results = await db.sales.aggregate(sales_table_pipeline).to_list(None)
        
        # Format sales table data
        sales_table_data = []
        for sale in sales_table_results:
            sales_table_data.append({
                "date": sale["created_at"].strftime("%Y-%m-%d %H:%M"),
                "order_id": sale["sale_number"],
                "customer": sale.get("customer_name", "Walk-in Customer"),
                "items_count": sale["items_count"],
                "amount": sale["total_amount"],
                "profit": sale["sale_profit"],
                "status": sale["status"]
            })
        
        # Get chart data for sales trend
        trend_pipeline = [
            {"$match": match_criteria},
            {"$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$created_at"
                    }
                },
                "revenue": {"$sum": "$total_amount"},
                "orders": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        trend_results = await db.sales.aggregate(trend_pipeline).to_list(None)
        
        # Format trend data
        trend_labels = [result["_id"] for result in trend_results]
        trend_revenue = [result["revenue"] for result in trend_results]
        trend_orders = [result["orders"] for result in trend_results]
        
        # Get top products data
        top_products_pipeline = [
            {"$match": match_criteria},
            {"$unwind": "$items"},
            {"$group": {
                "_id": "$items.product_name",
                "revenue": {"$sum": "$items.total_price"},
                "quantity": {"$sum": "$items.quantity"}
            }},
            {"$sort": {"revenue": -1}},
            {"$limit": 10}
        ]
        
        top_products_results = await db.sales.aggregate(top_products_pipeline).to_list(None)
        
        # Format top products data
        top_products_labels = [result["_id"] for result in top_products_results]
        top_products_revenue = [result["revenue"] for result in top_products_results]
        
        # Prepare summary data
        total_revenue = sales_summary.get("total_revenue", 0)
        total_orders = sales_summary.get("total_orders", 0)
        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
        profit_margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
        
        summary = {
            "total_revenue": total_revenue,
            "profit": profit,
            "profit_margin": profit_margin,
            "total_orders": total_orders,
            "avg_order_value": avg_order_value,
            "cash_total": sales_summary.get("cash_total", 0),
            "mobile_money_total": sales_summary.get("mobile_money_total", 0),
            "card_total": sales_summary.get("card_total", 0),
            "other_payment_total": sales_summary.get("other_payment_total", 0),
            "growth_rate": growth_rate
        }
        
        # Prepare chart data
        chart_data = {
            "sales_trend": {
                "labels": trend_labels,
                "revenue": trend_revenue,
                "orders": trend_orders
            },
            "top_products": {
                "labels": top_products_labels,
                "revenue": top_products_revenue
            }
        }
        
        return {
            "success": True,
            "summary": summary,
            "cashier_data": cashier_data,
            "sales_data": sales_table_data,
            "chart_data": chart_data
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
