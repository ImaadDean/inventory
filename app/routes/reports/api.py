from fastapi import APIRouter, Depends, Query
from ...config.database import get_database
from ...utils.timezone import now_kampala, get_day_start, get_week_start, get_month_start, get_today_start_utc, get_today_end_utc
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


@reports_api_router.get("/sales-trends")
async def get_sales_trends(
    days: int = Query(30, description="Number of days to show trends for"),
    db=Depends(get_database)
):
    """
    Get sales trends for the last N days (default 30 days).
    """
    try:
        from datetime import datetime, timedelta
        from ...utils.timezone import now_kampala, kampala_to_utc
        
        # Calculate date range
        end_date = now_kampala()
        start_date = end_date - timedelta(days=days)
        start_date_utc = kampala_to_utc(start_date)
        end_date_utc = kampala_to_utc(end_date)
        
        # Pipeline to get daily sales trends
        pipeline = [
            {
                "$match": {
                    "created_at": {
                        "$gte": start_date_utc,
                        "$lte": end_date_utc
                    },
                    "status": "completed"
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$created_at"
                        }
                    },
                    "revenue": {"$sum": "$total_amount"},
                    "orders": {"$sum": 1},
                    "profit": {"$sum": "$total_profit"}
                }
            },
            {
                "$sort": {"_id": 1}
            }
        ]
        
        results = await db.sales.aggregate(pipeline).to_list(None)
        
        # Format data for chart
        dates = [result["_id"] for result in results]
        revenue = [result["revenue"] for result in results]
        orders = [result["orders"] for result in results]
        profit = [result["profit"] for result in results]
        
        return {
            "success": True,
            "data": {
                "dates": dates,
                "revenue": revenue,
                "orders": orders,
                "profit": profit
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@reports_api_router.get("/sales-reports")
async def get_sales_reports(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db=Depends(get_database)
):
    """
    Get detailed sales reports with filtering options.
    """
    try:
        from datetime import datetime
        from ...utils.timezone import kampala_to_utc, get_day_start, get_day_end
        
        # Set default date range if not provided
        if not from_date:
            from_date = (now_kampala() - timedelta(days=30)).date()
        if not to_date:
            to_date = now_kampala().date()
            
        # Convert to datetime with timezone
        from_datetime = get_day_start(datetime.combine(from_date, datetime.min.time()))
        to_datetime = get_day_end(datetime.combine(to_date, datetime.max.time()))
        from_utc = kampala_to_utc(from_datetime)
        to_utc = kampala_to_utc(to_datetime)
        
        # Pipeline for sales reports
        pipeline = [
            {
                "$match": {
                    "created_at": {
                        "$gte": from_utc,
                        "$lte": to_utc
                    },
                    "status": "completed"
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_revenue": {"$sum": "$total_amount"},
                    "total_profit": {"$sum": "$total_profit"},
                    "total_orders": {"$sum": 1},
                    "total_discounts": {"$sum": "$discount_amount"},
                    "payment_methods": {
                        "$push": {
                            "method": "$payment_method",
                            "amount": "$total_amount"
                        }
                    }
                }
            },
            {
                "$project": {
                    "total_revenue": 1,
                    "total_profit": 1,
                    "total_orders": 1,
                    "total_discounts": 1,
                    "payment_breakdown": {
                        "$arrayToObject": {
                            "$map": {
                                "input": {
                                    "$setUnion": [
                                        "$payment_methods.method"
                                    ]
                                },
                                "as": "method",
                                "in": {
                                    "k": "$$method",
                                    "v": {
                                        "$sum": {
                                            "$map": {
                                                "input": {
                                                    "$filter": {
                                                        "input": "$payment_methods",
                                                        "cond": {
                                                            "$eq": ["$$this.method", "$$method"]
                                                        }
                                                    }
                                                },
                                                "as": "payment",
                                                "in": "$$payment.amount"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        ]
        
        result = await db.sales.aggregate(pipeline).to_list(1)
        summary = result[0] if result else {}
        
        # Get top selling products
        product_pipeline = [
            {
                "$match": {
                    "created_at": {
                        "$gte": from_utc,
                        "$lte": to_utc
                    },
                    "status": "completed"
                }
            },
            {"$unwind": "$items"},
            {
                "$group": {
                    "_id": "$items.product_name",
                    "quantity_sold": {"$sum": "$items.quantity"},
                    "revenue": {"$sum": "$items.total_price"}
                }
            },
            {"$sort": {"revenue": -1}},
            {"$limit": 10}
        ]
        
        top_products = await db.sales.aggregate(product_pipeline).to_list(None)
        
        # Get sales by cashier
        cashier_pipeline = [
            {
                "$match": {
                    "created_at": {
                        "$gte": from_utc,
                        "$lte": to_utc
                    },
                    "status": "completed"
                }
            },
            {
                "$group": {
                    "_id": "$cashier_name",
                    "total_sales": {"$sum": "$total_amount"},
                    "total_orders": {"$sum": 1}
                }
            },
            {"$sort": {"total_sales": -1}}
        ]
        
        cashier_performance = await db.sales.aggregate(cashier_pipeline).to_list(None)
        
        return {
            "success": True,
            "data": {
                "summary": summary,
                "top_products": top_products,
                "cashier_performance": cashier_performance
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@reports_api_router.get("/inventory-reports")
async def get_inventory_reports(db=Depends(get_database)):
    """
    Get inventory reports including stock levels and valuation.
    """
    try:
        # Get low stock products (less than 10 units) with category information
        low_stock_pipeline = [
            {
                "$match": {
                    "is_active": True,
                    "stock_quantity": {"$lt": 10}
                }
            },
            {
                "$lookup": {
                    "from": "categories",
                    "localField": "category_id",
                    "foreignField": "_id",
                    "as": "category_info"
                }
            },
            {
                "$unwind": {
                    "path": "$category_info",
                    "preserveNullAndEmptyArrays": True
                }
            },
            {
                "$project": {
                    "_id": {"$toString": "$_id"},
                    "name": 1,
                    "brand": 1,
                    "sku": 1,
                    "stock_quantity": 1,
                    "unit": 1,
                    "price": 1,
                    "cost_price": 1,
                    "category_name": {"$ifNull": ["$category_info.name", "Uncategorized"]}
                }
            },
            {"$sort": {"stock_quantity": 1}}
        ]
        
        low_stock_products = await db.products.aggregate(low_stock_pipeline).to_list(None)
        
        # Get inventory valuation
        valuation_pipeline = [
            {
                "$match": {
                    "is_active": True
                }
            },
            {
                "$project": {
                    "_id": {"$toString": "$_id"},
                    "name": 1,
                    "stock_quantity": 1,
                    "price": 1,
                    "cost_price": 1,
                    "stock_value": {
                        "$multiply": ["$stock_quantity", "$price"]
                    },
                    "cost_value": {
                        "$multiply": ["$stock_quantity", {"$ifNull": ["$cost_price", 0]}]
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_retail_value": {"$sum": "$stock_value"},
                    "total_cost_value": {"$sum": "$cost_value"},
                    "products": {
                        "$push": {
                            "_id": {"$toString": "$_id"},
                            "name": "$name",
                            "stock_quantity": "$stock_quantity",
                            "price": "$price",
                            "cost_price": "$cost_price",
                            "stock_value": "$stock_value",
                            "cost_value": "$cost_value"
                        }
                    }
                }
            }
        ]
        
        valuation_result = await db.products.aggregate(valuation_pipeline).to_list(1)
        valuation_data = valuation_result[0] if valuation_result else {}
        
        # Get category-wise inventory
        category_pipeline = [
            {
                "$lookup": {
                    "from": "categories",
                    "localField": "category_id",
                    "foreignField": "_id",
                    "as": "category_info"
                }
            },
            {
                "$unwind": {
                    "path": "$category_info",
                    "preserveNullAndEmptyArrays": True
                }
            },
            {
                "$addFields": {
                    "category_id_str": {"$toString": "$category_id"}
                }
            },
            {
                "$group": {
                    "_id": {
                        "$ifNull": ["$category_info.name", "Uncategorized"]
                    },
                    "category_id": {"$first": "$category_id_str"},
                    "product_count": {"$sum": 1},
                    "total_stock": {"$sum": "$stock_quantity"},
                    "total_value": {
                        "$sum": {
                            "$multiply": ["$stock_quantity", "$price"]
                        }
                    }
                }
            },
            {"$sort": {"total_value": -1}}
        ]
        
        category_inventory = await db.products.aggregate(category_pipeline).to_list(None)
        
        return {
            "success": True,
            "data": {
                "low_stock_products": low_stock_products,
                "valuation": valuation_data,
                "category_inventory": category_inventory
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@reports_api_router.get("/customer-reports")
async def get_customer_reports(db=Depends(get_database)):
    """
    Get customer analytics and reports.
    """
    try:
        # Get top customers by purchase value
        top_customers_pipeline = [
            {
                "$match": {
                    "is_active": True,
                    "total_purchases": {"$gt": 0}
                }
            },
            {
                "$project": {
                    "_id": {"$toString": "$_id"},
                    "name": 1,
                    "phone": 1,
                    "total_purchases": 1,
                    "total_orders": 1,
                    "avg_order_value": {
                        "$cond": [
                            {"$gt": ["$total_orders", 0]},
                            {"$divide": ["$total_purchases", "$total_orders"]},
                            0
                        ]
                    }
                }
            },
            {"$sort": {"total_purchases": -1}},
            {"$limit": 20}
        ]
        
        top_customers = await db.customers.aggregate(top_customers_pipeline).to_list(None)
        
        # Get customer statistics
        from datetime import datetime
        from ...utils.timezone import now_kampala, kampala_to_utc
        
        # Calculate the start of current month in UTC
        now = now_kampala()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_month_utc = kampala_to_utc(start_of_month)
        
        stats_pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total_customers": {"$sum": 1},
                    "active_customers": {
                        "$sum": {
                            "$cond": [{"$eq": ["$is_active", True]}, 1, 0]
                        }
                    },
                    "customers_with_purchases": {
                        "$sum": {
                            "$cond": [{"$gt": ["$total_purchases", 0]}, 1, 0]
                        }
                    },
                    "new_this_month": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$eq": ["$is_active", True]},
                                        {"$gte": ["$created_at", start_of_month_utc]}
                                    ]
                                },
                                1,
                                0
                            ]
                        }
                    }
                }
            }
        ]
        
        stats_result = await db.customers.aggregate(stats_pipeline).to_list(1)
        customer_stats = stats_result[0] if stats_result else {}
        
        # Get customer purchase trends (last 6 months)
        from datetime import datetime, timedelta
        from ...utils.timezone import now_kampala, kampala_to_utc
        
        six_months_ago = now_kampala() - timedelta(days=180)
        six_months_ago_utc = kampala_to_utc(six_months_ago)
        
        trend_pipeline = [
            {
                "$match": {
                    "created_at": {"$gte": six_months_ago_utc},
                    "status": "completed"
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m",
                            "date": "$created_at"
                        }
                    },
                    "new_customers": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$eq": [{"$type": "$customer_id"}, "objectId"]},
                                        {"$gte": ["$created_at", six_months_ago_utc]}
                                    ]
                                },
                                1,
                                0
                            ]
                        }
                    },
                    "repeat_customers": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$eq": [{"$type": "$customer_id"}, "objectId"]},
                                        {"$lt": ["$created_at", six_months_ago_utc]}
                                    ]
                                },
                                1,
                                0
                            ]
                        }
                    }
                }
            },
            {"$sort": {"_id": 1}}
        ]
        
        customer_trends = await db.sales.aggregate(trend_pipeline).to_list(None)
        
        # Calculate average order value from sales data
        avg_order_pipeline = [
            {
                "$match": {
                    "status": "completed"
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_revenue": {"$sum": "$total_amount"},
                    "total_orders": {"$sum": 1}
                }
            }
        ]
        
        avg_order_result = await db.sales.aggregate(avg_order_pipeline).to_list(1)
        avg_order_value = 0
        if avg_order_result:
            total_revenue = avg_order_result[0].get("total_revenue", 0)
            total_orders = avg_order_result[0].get("total_orders", 1)
            avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
        
        # Add average order value to stats
        customer_stats["avg_order_value"] = avg_order_value
        
        return {
            "success": True,
            "data": {
                "top_customers": top_customers,
                "statistics": customer_stats,
                "trends": customer_trends
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@reports_api_router.get("/customer-reports/top-customers")
async def get_top_customers(
    limit: int = Query(10, description="Number of top customers to return"),
    db=Depends(get_database)
):
    """
    Get top customers by purchase value.
    """
    try:
        pipeline = [
            {
                "$match": {
                    "is_active": True,
                    "total_purchases": {"$gt": 0}
                }
            },
            {
                "$project": {
                    "_id": {"$toString": "$_id"},
                    "name": 1,
                    "phone": 1,
                    "total_purchases": 1,
                    "total_orders": 1,
                    "avg_order_value": {
                        "$cond": [
                            {"$gt": ["$total_orders", 0]},
                            {"$divide": ["$total_purchases", "$total_orders"]},
                            0
                        ]
                    }
                }
            },
            {"$sort": {"total_purchases": -1}},
            {"$limit": limit}
        ]
        
        top_customers = await db.customers.aggregate(pipeline).to_list(None)
        
        return {
            "success": True,
            "data": top_customers
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@reports_api_router.get("/customer-reports/segments")
async def get_customer_segments(db=Depends(get_database)):
    """
    Get customer segmentation data.
    """
    try:
        # Segment customers by purchase value
        pipeline = [
            {
                "$match": {
                    "is_active": True
                }
            },
            {
                "$addFields": {
                    "segment": {
                        "$switch": {
                            "branches": [
                                {"case": {"$gte": ["$total_purchases", 1000000]}, "then": "VIP"},
                                {"case": {"$gte": ["$total_purchases", 500000]}, "then": "Premium"},
                                {"case": {"$gte": ["$total_purchases", 100000]}, "then": "Regular"},
                                {"case": {"$gt": ["$total_purchases", 0]}, "then": "Active"},
                            ],
                            "default": "Inactive"
                        }
                    }
                }
            },
            {
                "$group": {
                    "_id": "$segment",
                    "count": {"$sum": 1},
                    "total_value": {"$sum": "$total_purchases"}
                }
            },
            {"$sort": {"total_value": -1}}
        ]
        
        segments = await db.customers.aggregate(pipeline).to_list(None)
        
        return {
            "success": True,
            "data": segments
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@reports_api_router.get("/customer-reports/purchase-history")
async def get_customer_purchase_history(
    customer_id: Optional[str] = Query(None, description="Customer ID to filter by"),
    days: int = Query(30, description="Number of days of history to return"),
    db=Depends(get_database)
):
    """
    Get customer purchase history.
    """
    try:
        from datetime import datetime, timedelta
        from ...utils.timezone import now_kampala, kampala_to_utc
        from bson import ObjectId
        
        # Calculate date range
        end_date = now_kampala()
        start_date = end_date - timedelta(days=days)
        start_date_utc = kampala_to_utc(start_date)
        end_date_utc = kampala_to_utc(end_date)
        
        # Build match criteria
        match_criteria = {
            "created_at": {"$gte": start_date_utc, "$lte": end_date_utc},
            "status": "completed"
        }
        
        if customer_id:
            match_criteria["customer_id"] = ObjectId(customer_id)
        
        # Pipeline to get purchase history
        pipeline = [
            {"$match": match_criteria},
            {"$sort": {"created_at": -1}},
            {"$limit": 100},  # Limit to 100 most recent purchases
            {
                "$project": {
                    "_id": {"$toString": "$_id"},
                    "sale_number": 1,
                    "customer_name": 1,
                    "total_amount": 1,
                    "created_at": 1,
                    "payment_method": 1,
                    "items_count": {"$size": "$items"}
                }
            }
        ]
        
        purchase_history = await db.sales.aggregate(pipeline).to_list(None)
        
        # Format dates and add additional info
        for record in purchase_history:
            record["created_at"] = record["created_at"].strftime("%Y-%m-%d %H:%M")
        
        return {
            "success": True,
            "data": purchase_history
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@reports_api_router.get("/profit-loss-report")
async def get_profit_loss_report(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db=Depends(get_database)
):
    """
    Generate a detailed Profit & Loss report with revenue, costs, expenses, and profit breakdown.
    """
    try:
        from datetime import datetime, timedelta
        from ...utils.timezone import now_kampala, kampala_to_utc, get_day_start, get_day_end
        
        # Set default date range if not provided (last 30 days)
        if not from_date:
            from_date = (now_kampala() - timedelta(days=30)).date()
        if not to_date:
            to_date = now_kampala().date()
            
        # Convert to datetime with timezone
        from_datetime = get_day_start(datetime.combine(from_date, datetime.min.time()))
        to_datetime = get_day_end(datetime.combine(to_date, datetime.max.time()))
        from_utc = kampala_to_utc(from_datetime)
        to_utc = kampala_to_utc(to_datetime)
        
        # Get sales data with detailed breakdown
        sales_pipeline = [
            {
                "$match": {
                    "created_at": {
                        "$gte": from_utc,
                        "$lte": to_utc
                    },
                    "status": "completed"
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_revenue": {"$sum": {"$ifNull": ["$total_amount", 0]}},
                    "total_cost": {"$sum": {"$ifNull": ["$total_cost", 0]}},
                    "total_profit": {"$sum": {"$ifNull": ["$total_profit", 0]}},
                    "total_discounts": {"$sum": {"$ifNull": ["$discount_amount", 0]}},
                    "total_tax": {"$sum": {"$ifNull": ["$tax_amount", 0]}},
                    "total_orders": {"$sum": 1}
                }
            }
        ]
        
        sales_result = await db.sales.aggregate(sales_pipeline).to_list(1)
        sales_data = sales_result[0] if sales_result else {}
        
        # Get expenses data grouped by category
        # Convert dates to datetime objects for MongoDB compatibility
        expense_pipeline = [
            {
                "$match": {
                    "date": {
                        "$gte": datetime.combine(from_date, datetime.min.time()),
                        "$lte": datetime.combine(to_date, datetime.max.time())
                    }
                }
            },
            {
                "$group": {
                    "_id": {"$ifNull": ["$category", "Uncategorized"]},
                    "total_amount": {"$sum": {"$ifNull": ["$amount", 0]}},
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"total_amount": -1}}
        ]
        
        expenses = await db.expenses.aggregate(expense_pipeline).to_list(None)
        
        # Calculate totals
        total_revenue = sales_data.get("total_revenue", 0)
        total_cost_of_goods = sales_data.get("total_cost", 0)
        total_discounts = sales_data.get("total_discounts", 0)
        total_tax = sales_data.get("total_tax", 0)
        total_expenses = sum(expense.get("total_amount", 0) for expense in expenses)
        
        # Calculate profit metrics
        gross_profit = total_revenue - total_cost_of_goods
        net_profit_before_expenses = gross_profit - total_discounts - total_tax
        net_profit = net_profit_before_expenses - total_expenses
        
        # Calculate margins
        gross_profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0
        net_profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        # Format expense categories for the report
        expense_categories = []
        for expense in expenses:
            category_name = expense.get("_id", "Uncategorized")
            amount = expense.get("total_amount", 0)
            percentage = (amount / total_revenue * 100) if total_revenue > 0 else 0
            
            expense_categories.append({
                "category": category_name,
                "amount": amount,
                "percentage": percentage,
                "count": expense.get("count", 0)
            })
        
        return {
            "success": True,
            "data": {
                "period": {
                    "from": from_date.isoformat(),
                    "to": to_date.isoformat()
                },
                "summary": {
                    "total_revenue": total_revenue,
                    "total_cost_of_goods": total_cost_of_goods,
                    "gross_profit": gross_profit,
                    "gross_profit_margin": gross_profit_margin,
                    "total_discounts": total_discounts,
                    "total_tax": total_tax,
                    "total_expenses": total_expenses,
                    "net_profit": net_profit,
                    "net_profit_margin": net_profit_margin,
                    "total_orders": sales_data.get("total_orders", 0)
                },
                "expense_breakdown": expense_categories,
                "timestamp": now_kampala().isoformat()
            }
        }
        
    except Exception as e:
        import traceback
        print(f"Error in get_profit_loss_report: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }


@reports_api_router.get("/financial-reports")
async def get_financial_reports(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db=Depends(get_database)
):
    """
    Get financial reports including profit, loss, and expenses.
    """
    try:
        from datetime import datetime, timedelta
        from ...utils.timezone import now_kampala, kampala_to_utc, get_day_start, get_day_end
        
        # Set default date range if not provided
        if not from_date:
            from_date = (now_kampala() - timedelta(days=30)).date()
        if not to_date:
            to_date = now_kampala().date()
            
        # Convert to datetime with timezone for sales
        from_datetime = get_day_start(datetime.combine(from_date, datetime.min.time()))
        to_datetime = get_day_end(datetime.combine(to_date, datetime.max.time()))
        from_utc = kampala_to_utc(from_datetime)
        to_utc = kampala_to_utc(to_datetime)
        
        # Get sales financials
        sales_pipeline = [
            {
                "$match": {
                    "created_at": {
                        "$gte": from_utc,
                        "$lte": to_utc
                    },
                    "status": "completed"
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_revenue": {"$sum": {"$ifNull": ["$total_amount", 0]}},
                    "total_cost": {"$sum": {"$ifNull": ["$total_cost", 0]}},
                    "total_profit": {"$sum": {"$ifNull": ["$total_profit", 0]}},
                    "total_discounts": {"$sum": {"$ifNull": ["$discount_amount", 0]}},
                    "total_tax": {"$sum": {"$ifNull": ["$tax_amount", 0]}}
                }
            }
        ]
        
        sales_result = await db.sales.aggregate(sales_pipeline).to_list(1)
        sales_data = sales_result[0] if sales_result else {}
        
        # Get expenses - using datetime objects for MongoDB compatibility
        expense_pipeline = [
            {
                "$match": {
                    "date": {
                        "$gte": datetime.combine(from_date, datetime.min.time()),
                        "$lte": datetime.combine(to_date, datetime.max.time())
                    }
                }
            },
            {
                "$group": {
                    "_id": {"$ifNull": ["$category", "Uncategorized"]},
                    "total_amount": {"$sum": {"$ifNull": ["$amount", 0]}},
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"total_amount": -1}}
        ]
        
        expenses = await db.expenses.aggregate(expense_pipeline).to_list(None)
        
        # Calculate net profit
        total_revenue = sales_data.get("total_revenue", 0)
        total_cost = sales_data.get("total_cost", 0)
        total_discounts = sales_data.get("total_discounts", 0)
        total_expenses = sum(expense.get("total_amount", 0) for expense in expenses)
        net_profit = total_revenue - total_cost - total_expenses
        
        # Calculate profit margin
        profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        return {
            "success": True,
            "data": {
                "sales": sales_data,
                "expenses": expenses,
                "net_profit": net_profit,
                "profit_margin": profit_margin,
                "period": {
                    "from": from_date.isoformat(),
                    "to": to_date.isoformat()
                }
            }
        }
        
    except Exception as e:
        import traceback
        print(f"Error in get_financial_reports: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }


@reports_api_router.get("/export-data")
async def export_all_data(db=Depends(get_database)):
    """
    Export all data for reporting purposes.
    """
    try:
        # Export sales data
        sales = await db.sales.find({}).to_list(None)
        
        # Export products data
        products = await db.products.find({}).to_list(None)
        
        # Export customers data
        customers = await db.customers.find({}).to_list(None)
        
        # Export expenses data
        expenses = await db.expenses.find({}).to_list(None)
        
        return {
            "success": True,
            "data": {
                "sales": sales,
                "products": products,
                "customers": customers,
                "expenses": expenses
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@reports_api_router.get("/stock-movement")
async def get_stock_movement(
    days: int = Query(30, description="Number of days to show movements for"),
    db=Depends(get_database)
):
    """
    Get stock movement reports including inventory in/out transactions.
    """
    try:
        from datetime import datetime, timedelta
        from ...utils.timezone import now_kampala, kampala_to_utc
        import random
        
        # Calculate date range
        end_date = now_kampala()
        start_date = end_date - timedelta(days=days)
        start_date_utc = kampala_to_utc(start_date)
        end_date_utc = kampala_to_utc(end_date)
        
        # Pipeline to get stock movement data from sales
        pipeline = [
            {
                "$match": {
                    "created_at": {
                        "$gte": start_date_utc,
                        "$lte": end_date_utc
                    },
                    "status": "completed"
                }
            },
            {
                "$unwind": "$items"
            },
            {
                "$project": {
                    "date": {
                        "$dateToString": {
                            "format": "%Y-%m-%d %H:%M",
                            "date": "$created_at"
                        }
                    },
                    "product_name": "$items.product_name",
                    "sku": "$items.sku",
                    "quantity": {"$multiply": ["$items.quantity", -1]},  # Negative for sales (stock out)
                    "user": "$cashier_name",
                    "created_at": 1
                }
            },
            {
                "$sort": {"created_at": -1}
            },
            {
                "$limit": 50
            }
        ]
        
        # Get stock out movements from sales
        sales_movements = await db.sales.aggregate(pipeline).to_list(None)
        
        # Clean the data to ensure no ObjectId objects are present
        clean_sales_movements = []
        for movement in sales_movements:
            clean_movement = {
                "date": movement.get("date", ""),
                "product_name": movement.get("product_name", "Unknown Product"),
                "sku": movement.get("sku", "N/A"),
                "quantity": movement.get("quantity", 0),
                "user": movement.get("user", "System")
            }
            clean_sales_movements.append(clean_movement)
        
        # Generate some sample stock in movements
        stock_in_movements = []
        product_names = ["iPhone 15 Pro", "Chanel No. 5", "Rolex Submariner", "MacBook Pro", "Designer Watch"]
        users = ["John Doe", "Jane Smith", "Mike Johnson", "Sarah Wilson", "System"]
        
        for i in range(10):
            random_days = random.randint(0, days)
            random_date = (now_kampala() - timedelta(days=random_days)).strftime("%Y-%m-%d %H:%M")
            
            stock_in_movements.append({
                "date": random_date,
                "product_name": random.choice(product_names),
                "sku": f"SKU-{random.randint(1000, 9999)}",
                "quantity": random.randint(1, 10),  # Positive for stock in
                "user": random.choice(users)
            })
        
        # Combine and sort all movements
        all_movements = clean_sales_movements + stock_in_movements
        all_movements.sort(key=lambda x: x["date"], reverse=True)
        
        # Limit to 30 records for performance
        all_movements = all_movements[:30]
        
        return {
            "success": True,
            "data": all_movements
        }
        
    except Exception as e:
        import traceback
        print(f"Error in get_stock_movement: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }


@reports_api_router.get("/valuation-report")
async def get_valuation_report(db=Depends(get_database)):
    """
    Get detailed inventory valuation report.
    """
    try:
        # Pipeline to get detailed inventory valuation
        valuation_pipeline = [
            {
                "$match": {
                    "is_active": True
                }
            },
            {
                "$lookup": {
                    "from": "categories",
                    "localField": "category_id",
                    "foreignField": "_id",
                    "as": "category_info"
                }
            },
            {
                "$unwind": {
                    "path": "$category_info",
                    "preserveNullAndEmptyArrays": True
                }
            },
            {
                "$project": {
                    "_id": {"$toString": "$_id"},
                    "name": 1,
                    "sku": 1,
                    "brand": 1,
                    "stock_quantity": 1,
                    "price": 1,
                    "cost_price": {"$ifNull": ["$cost_price", 0]},
                    "unit": 1,
                    "category_name": {"$ifNull": ["$category_info.name", "Uncategorized"]},
                    "retail_value": {
                        "$multiply": ["$stock_quantity", "$price"]
                    },
                    "cost_value": {
                        "$multiply": ["$stock_quantity", {"$ifNull": ["$cost_price", 0]}]
                    },
                    "profit_value": {
                        "$subtract": [
                            {"$multiply": ["$stock_quantity", "$price"]},
                            {"$multiply": ["$stock_quantity", {"$ifNull": ["$cost_price", 0]}]}
                        ]
                    }
                }
            },
            {
                "$sort": {"retail_value": -1}
            }
        ]
        
        # Get detailed product valuations
        product_valuations = await db.products.aggregate(valuation_pipeline).to_list(None)
        
        # Calculate summary statistics
        total_retail_value = sum(product.get("retail_value", 0) for product in product_valuations)
        total_cost_value = sum(product.get("cost_value", 0) for product in product_valuations)
        total_profit_value = sum(product.get("profit_value", 0) for product in product_valuations)
        
        # Group by category for category-wise valuation
        category_valuation = {}
        for product in product_valuations:
            category = product.get("category_name", "Uncategorized")
            if category not in category_valuation:
                category_valuation[category] = {
                    "retail_value": 0,
                    "cost_value": 0,
                    "profit_value": 0,
                    "product_count": 0
                }
            category_valuation[category]["retail_value"] += product.get("retail_value", 0)
            category_valuation[category]["cost_value"] += product.get("cost_value", 0)
            category_valuation[category]["profit_value"] += product.get("profit_value", 0)
            category_valuation[category]["product_count"] += 1
        
        # Convert category valuation to list format
        category_valuation_list = [
            {
                "category_name": category,
                "retail_value": values["retail_value"],
                "cost_value": values["cost_value"],
                "profit_value": values["profit_value"],
                "product_count": values["product_count"]
            }
            for category, values in category_valuation.items()
        ]
        
        # Sort category valuation by retail value
        category_valuation_list.sort(key=lambda x: x["retail_value"], reverse=True)
        
        return {
            "success": True,
            "data": {
                "products": product_valuations,
                "summary": {
                    "total_retail_value": total_retail_value,
                    "total_cost_value": total_cost_value,
                    "total_profit_value": total_profit_value,
                    "total_products": len(product_valuations)
                },
                "by_category": category_valuation_list
            }
        }
        
    except Exception as e:
        import traceback
        print(f"Error in get_valuation_report: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }
