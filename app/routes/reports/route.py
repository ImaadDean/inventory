from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from ...config.database import get_database
from ...utils.timezone import now_kampala, kampala_to_utc, get_day_start, get_week_start, get_month_start
from ...utils.auth import get_current_user, verify_token, get_user_by_username
from ...models import User

# Create router
reports_routes = APIRouter()

# Templates
templates = Jinja2Templates(directory="app/templates")

# Register timezone template filters
from ...utils.template_filters import TEMPLATE_FILTERS
for filter_name, filter_func in TEMPLATE_FILTERS.items():
    templates.env.filters[filter_name] = filter_func


async def get_current_user_from_cookie(request: Request):
    """Get current user from cookie for HTML routes"""
    access_token = request.cookies.get("access_token")
    print(f"🔍 Auth Debug - access_token from cookie: {access_token[:50] if access_token else 'None'}...")

    if not access_token:
        print("🔍 Auth Debug - No access token found in cookies")
        return None

    if access_token.startswith("Bearer "):
        token = access_token[7:]
    else:
        token = access_token

    payload = verify_token(token)
    if not payload:
        print("🔍 Auth Debug - Token verification failed")
        return None

    username = payload.get("sub")
    if not username:
        print("🔍 Auth Debug - No username in token payload")
        return None

    user = await get_user_by_username(username)
    if not user or not user.is_active:
        print(f"🔍 Auth Debug - User not found or inactive: {username}")
        return None

    print(f"🔍 Auth Debug - Successfully authenticated user: {username}")
    return user


@reports_routes.get("/", response_class=HTMLResponse)
async def reports_dashboard(request: Request):
    """Main reports dashboard"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        db = await get_database()
        
        # Get current time in Kampala timezone
        now = now_kampala()
        today_start = get_day_start(now)
        week_start = get_week_start(now)
        month_start = get_month_start(now)
        
        # Convert to UTC for database queries
        today_start_utc = kampala_to_utc(today_start)
        week_start_utc = kampala_to_utc(week_start)
        month_start_utc = kampala_to_utc(month_start)

        # Debug: Print date ranges
        print(f"🔍 Debug - Current Kampala time: {now}")
        print(f"🔍 Debug - Today start UTC: {today_start_utc}")
        print(f"🔍 Debug - Week start UTC: {week_start_utc}")
        print(f"🔍 Debug - Month start UTC: {month_start_utc}")

        # Debug: Check total orders in database
        total_orders_debug = await db.orders.count_documents({})
        completed_orders_debug = await db.orders.count_documents({"status": "Completed"})
        print(f"🔍 Debug - Total orders in DB: {total_orders_debug}")
        print(f"🔍 Debug - Completed orders in DB: {completed_orders_debug}")

        # Debug: Check recent orders
        recent_orders = await db.orders.find({}).sort("created_at", -1).limit(3).to_list(length=3)
        print(f"🔍 Debug - Recent orders:")
        for order in recent_orders:
            print(f"  - {order.get('order_number', 'No number')}: {order.get('created_at')} - Status: {order.get('status')} - Total: {order.get('total', 0)}")
        
        # Using datetime objects for comparison with MongoDB

        # Get basic statistics (using orders collection with correct status and datetime comparison)
        stats = {
            "today": {
                "orders": await db.orders.count_documents({"created_at": {"$gte": today_start_utc}, "status": "completed"}),
                "revenue": 0,
                "customers": 0,
                "profit": 0,
                "profit_margin": 0
            },
            "week": {
                "orders": await db.orders.count_documents({"created_at": {"$gte": week_start_utc}, "status": "completed"}),
                "revenue": 0,
                "customers": 0,
                "profit": 0,
                "profit_margin": 0
            },
            "month": {
                "orders": await db.orders.count_documents({"created_at": {"$gte": month_start_utc}, "status": "completed"}),
                "revenue": 0,
                "customers": 0,
                "profit": 0,
                "profit_margin": 0
            },
            "total": {
                "orders": await db.orders.count_documents({"status": "completed"}),
                "incomplete_orders": await db.orders.count_documents({"status": {"$ne": "completed"}}),
                "products": await db.products.count_documents({}),
                "customers": await db.customers.count_documents({}),
                "categories": await db.categories.count_documents({})
            }
        }
        
        # Calculate revenue for each period (using orders collection with correct status)
        for period, period_start in [("today", today_start_utc), ("week", week_start_utc), ("month", month_start_utc)]:
            # Use datetime objects for comparison since orders store created_at as datetime
            revenue_pipeline = [
                {"$match": {
                    "created_at": {"$gte": period_start},  # Use datetime comparison
                    "status": "completed"  # Use lowercase status
                }},
                {"$group": {"_id": None, "total": {"$sum": "$total"}}}
            ]
            revenue_result = await db.orders.aggregate(revenue_pipeline).to_list(length=1)
            stats[period]["revenue"] = revenue_result[0]["total"] if revenue_result else 0

            # Count unique customers for the period
            customer_pipeline = [
                {"$match": {
                    "created_at": {"$gte": period_start},  # Use datetime comparison
                    "status": "completed",  # Use lowercase status
                    "client_id": {"$ne": None}  # Only count orders with customers
                }},
                {"$group": {"_id": "$client_id"}},
                {"$count": "unique_customers"}
            ]
            customer_result = await db.orders.aggregate(customer_pipeline).to_list(length=1)
            stats[period]["customers"] = customer_result[0]["unique_customers"] if customer_result else 0

            # Calculate profit for the period (revenue - cost) using orders
            profit_pipeline = [
                {"$match": {
                    "created_at": {"$gte": period_start},  # Use datetime comparison
                    "status": "completed"  # Use lowercase status
                }},
                {"$unwind": "$items"},  # Unwind items array to process each item
                {"$lookup": {  # Join with products to get cost_price and decant info
                    "from": "products",
                    "let": {"product_id": "$items.product_id"},
                    "pipeline": [
                        {"$match": {
                            "$expr": {
                                "$or": [
                                    {"$eq": ["$_id", {"$toObjectId": "$$product_id"}]},
                                    {"$eq": ["$_id", "$$product_id"]}
                                ]
                            }
                        }}
                    ],
                    "as": "product_info"
                }},
                {"$unwind": {"path": "$product_info", "preserveNullAndEmptyArrays": True}},
                {"$addFields": {
                    "item_cost": {
                        "$cond": {
                            "if": {"$and": [
                                {"$ne": ["$product_info", None]},
                                {"$ne": ["$product_info.cost_price", None]},
                                {"$gt": ["$product_info.cost_price", 0]}
                            ]},
                            "then": {
                                "$cond": {
                                    # Check if this is a decant sale (item price matches decant price)
                                    "if": {"$and": [
                                        {"$ne": ["$product_info.decant", None]},
                                        {"$eq": ["$product_info.decant.is_decantable", True]},
                                        {"$ne": ["$product_info.decant.decant_price", None]},
                                        {"$ne": ["$product_info.bottle_size_ml", None]},
                                        {"$ne": ["$product_info.decant.decant_size_ml", None]},
                                        {"$gt": ["$product_info.bottle_size_ml", 0]},
                                        {"$gt": ["$product_info.decant.decant_size_ml", 0]},
                                        # Check if item price matches decant price (within 1 UGX tolerance)
                                        {"$lte": [
                                            {"$abs": {"$subtract": ["$items.price", "$product_info.decant.decant_price"]}},
                                            1
                                        ]}
                                    ]},
                                    # This is a decant sale - calculate proportional cost
                                    "then": {
                                        "$multiply": [
                                            "$product_info.cost_price",
                                            {"$divide": [
                                                "$product_info.decant.decant_size_ml",
                                                "$product_info.bottle_size_ml"
                                            ]}
                                        ]
                                    },
                                    # This is a regular sale - use full cost price
                                    "else": "$product_info.cost_price"
                                }
                            },
                            "else": 0
                        }
                    }
                }},
                {"$group": {
                    "_id": None,
                    "total_revenue": {"$sum": "$items.total"},  # Use items.total for orders
                    "total_cost": {"$sum": {
                        "$multiply": ["$items.quantity", "$item_cost"]
                    }}
                }},
                {"$project": {
                    "profit": {"$subtract": ["$total_revenue", "$total_cost"]},
                    "profit_margin": {
                        "$cond": {
                            "if": {"$gt": ["$total_revenue", 0]},
                            "then": {
                                "$multiply": [
                                    {"$divide": [
                                        {"$subtract": ["$total_revenue", "$total_cost"]},
                                        "$total_revenue"
                                    ]},
                                    100
                                ]
                            },
                            "else": 0
                        }
                    }
                }}
            ]

            profit_result = await db.orders.aggregate(profit_pipeline).to_list(length=1)
            if profit_result:
                stats[period]["profit"] = profit_result[0].get("profit", 0)
                stats[period]["profit_margin"] = profit_result[0].get("profit_margin", 0)
            else:
                stats[period]["profit"] = 0
                stats[period]["profit_margin"] = 0
        
        return templates.TemplateResponse(
            "reports/index.html",
            {
                "request": request,
                "user": current_user,
                "stats": stats,
                "current_date": now,
                "page_title": "Reports Dashboard"
            }
        )
        
    except Exception as e:
        print(f"Error in reports dashboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to load reports dashboard")


@reports_routes.get("/debug")
async def debug_orders_data(request: Request):
    """Debug endpoint to check orders data"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        db = await get_database()

        # Get sample orders
        orders = await db.orders.find({}).sort("created_at", -1).limit(3).to_list(length=3)

        debug_info = {
            "total_orders": await db.orders.count_documents({}),
            "completed_orders": await db.orders.count_documents({"status": "completed"}),
            "completed_orders_cap": await db.orders.count_documents({"status": "Completed"}),
            "sample_orders": []
        }

        for order in orders:
            debug_info["sample_orders"].append({
                "order_number": order.get("order_number"),
                "status": order.get("status"),
                "total": order.get("total"),
                "created_at": str(order.get("created_at")),
                "created_at_type": str(type(order.get("created_at"))),
                "client_name": order.get("client_name"),
                "items": order.get("items", [])[:1] if order.get("items") else [],  # Show first item only
                "items_count": len(order.get("items", []))
            })

        return debug_info

    except Exception as e:
        return {"error": str(e)}


@reports_routes.get("/sales", response_class=HTMLResponse)
async def sales_report(request: Request):
    """Sales reports page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return templates.TemplateResponse(
        "reports/sales.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Sales Reports"
        }
    )


@reports_routes.get("/test-sales-api", response_class=HTMLResponse)
async def test_sales_api(request: Request):
    """Test page for sales API debugging"""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sales API Test</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .result { margin: 10px 0; padding: 10px; border: 1px solid #ccc; }
            .error { background-color: #ffebee; border-color: #f44336; }
            .success { background-color: #e8f5e8; border-color: #4caf50; }
            button { padding: 10px 20px; margin: 5px; }
        </style>
    </head>
    <body>
        <h1>Sales API Test</h1>

        <div>
            <label>From Date: <input type="date" id="fromDate"></label>
            <label>To Date: <input type="date" id="toDate"></label>
            <button onclick="testSalesAPI()">Test Sales API</button>
        </div>

        <div id="results"></div>

        <script>
            // Set default dates
            const today = new Date();
            const weekAgo = new Date(today);
            weekAgo.setDate(today.getDate() - 7);

            document.getElementById('fromDate').value = weekAgo.toISOString().split('T')[0];
            document.getElementById('toDate').value = today.toISOString().split('T')[0];

            async function testSalesAPI() {
                const resultsDiv = document.getElementById('results');
                resultsDiv.innerHTML = '<div class="result">Testing...</div>';

                const fromDate = document.getElementById('fromDate').value;
                const toDate = document.getElementById('toDate').value;

                console.log('Testing with dates:', { fromDate, toDate });

                try {
                    const url = `/reports/api/sales-data?from_date=${fromDate}&to_date=${toDate}`;
                    console.log('Fetching from:', url);

                    const response = await fetch(url, {
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json',
                            'Content-Type': 'application/json'
                        }
                    });

                    console.log('Response status:', response.status);
                    console.log('Response headers:', [...response.headers.entries()]);

                    if (!response.ok) {
                        const errorText = await response.text();
                        throw new Error(`HTTP ${response.status}: ${errorText}`);
                    }

                    const data = await response.json();
                    console.log('Response data:', data);

                    resultsDiv.innerHTML = `
                        <div class="result success">
                            <h3>✅ Success!</h3>
                            <p><strong>Status:</strong> ${response.status}</p>
                            <p><strong>Success:</strong> ${data.success}</p>
                            <p><strong>Total Revenue:</strong> UGX ${data.summary?.total_revenue?.toLocaleString() || 'N/A'}</p>
                            <p><strong>Total Orders:</strong> ${data.summary?.total_orders || 'N/A'}</p>
                            <p><strong>Avg Order Value:</strong> UGX ${data.summary?.avg_order_value?.toLocaleString() || 'N/A'}</p>
                            <details>
                                <summary>Raw Response</summary>
                                <pre>${JSON.stringify(data, null, 2)}</pre>
                            </details>
                        </div>
                    `;

                } catch (error) {
                    console.error('Error:', error);
                    resultsDiv.innerHTML = `
                        <div class="result error">
                            <h3>❌ Error</h3>
                            <p><strong>Message:</strong> ${error.message}</p>
                            <p><strong>Stack:</strong> ${error.stack}</p>
                        </div>
                    `;
                }
            }

            // Auto-test on page load
            window.addEventListener('load', () => {
                setTimeout(testSalesAPI, 500);
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@reports_routes.get("/test-chart", response_class=HTMLResponse)
async def test_chart_page(request: Request):
    """Test page for ApexCharts debugging"""
    try:
        with open("apexcharts_test.html", "r") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>ApexCharts test file not found</h1>", status_code=404)


@reports_routes.get("/inventory", response_class=HTMLResponse)
async def inventory_report(request: Request):
    """Inventory reports page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return templates.TemplateResponse(
        "reports/inventory.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Inventory Reports"
        }
    )


@reports_routes.get("/customers", response_class=HTMLResponse)
async def customers_report(request: Request):
    """Customer reports page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return templates.TemplateResponse(
        "reports/customers.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Customer Reports"
        }
    )


@reports_routes.get("/api/sales-data")
async def get_sales_data(
    request: Request,
    from_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    to_date: str = Query(..., description="End date in YYYY-MM-DD format")
):
    """Get sales data for the specified date range"""
    # TODO: Fix authentication issue - temporarily disabled for functionality
    # current_user = await get_current_user_from_cookie(request)
    # if not current_user:
    #     raise HTTPException(status_code=401, detail="Authentication required")

    try:
        db = await get_database()

        print(f"🔍 Sales API Debug - from_date: {from_date}, to_date: {to_date}")

        # Parse dates and convert to datetime objects
        start_date = datetime.strptime(from_date, "%Y-%m-%d")
        end_date = datetime.strptime(to_date, "%Y-%m-%d")
        # Set end_date to end of day
        end_date = end_date.replace(hour=23, minute=59, second=59)

        print(f"🔍 Sales API Debug - parsed dates: {start_date} to {end_date}")

        # Convert to UTC for database query
        start_date_utc = kampala_to_utc(start_date)
        end_date_utc = kampala_to_utc(end_date)

        print(f"🔍 Sales API Debug - UTC dates: {start_date_utc} to {end_date_utc}")

        # Get sales summary
        summary_pipeline = [
            {"$match": {
                "created_at": {"$gte": start_date_utc, "$lte": end_date_utc},
                "status": "completed"
            }},
            {"$group": {
                "_id": None,
                "total_revenue": {"$sum": "$total"},
                "total_orders": {"$sum": 1},
                "avg_order_value": {"$avg": "$total"}
            }}
        ]

        summary_result = await db.orders.aggregate(summary_pipeline).to_list(length=1)
        summary = summary_result[0] if summary_result else {
            "total_revenue": 0,
            "total_orders": 0,
            "avg_order_value": 0
        }

        # Calculate growth rate by comparing with previous period
        period_duration = (end_date - start_date).days + 1  # +1 to include both start and end dates
        previous_start_date = start_date - timedelta(days=period_duration)
        previous_end_date = start_date - timedelta(days=1)  # Day before current period starts

        # Convert previous period dates to UTC
        previous_start_date_utc = kampala_to_utc(previous_start_date)
        previous_end_date_utc = kampala_to_utc(previous_end_date.replace(hour=23, minute=59, second=59))

        print(f"🔍 Growth calculation - Current period: {start_date} to {end_date} ({period_duration} days)")
        print(f"🔍 Growth calculation - Previous period: {previous_start_date} to {previous_end_date} ({period_duration} days)")

        # Get previous period summary
        previous_summary_pipeline = [
            {"$match": {
                "created_at": {"$gte": previous_start_date_utc, "$lte": previous_end_date_utc},
                "status": "completed"
            }},
            {"$group": {
                "_id": None,
                "total_revenue": {"$sum": "$total"},
                "total_orders": {"$sum": 1}
            }}
        ]

        previous_summary_result = await db.orders.aggregate(previous_summary_pipeline).to_list(length=1)
        previous_summary = previous_summary_result[0] if previous_summary_result else {
            "total_revenue": 0,
            "total_orders": 0
        }

        # Calculate growth rate
        current_revenue = summary["total_revenue"]
        previous_revenue = previous_summary["total_revenue"]

        if previous_revenue > 0:
            growth_rate = ((current_revenue - previous_revenue) / previous_revenue) * 100
        else:
            # If no previous revenue, show 100% growth if current revenue > 0, else 0%
            growth_rate = 100 if current_revenue > 0 else 0

        print(f"🔍 Growth calculation - Current revenue: {current_revenue}, Previous revenue: {previous_revenue}, Growth rate: {growth_rate:.1f}%")

        # Get daily sales trend
        daily_pipeline = [
            {"$match": {
                "created_at": {"$gte": start_date_utc, "$lte": end_date_utc},
                "status": "completed"
            }},
            {"$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$created_at"
                    }
                },
                "daily_revenue": {"$sum": "$total"},
                "daily_orders": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]

        daily_data = await db.orders.aggregate(daily_pipeline).to_list(length=None)

        # Get top products
        top_products_pipeline = [
            {"$match": {
                "created_at": {"$gte": start_date_utc, "$lte": end_date_utc},
                "status": "completed"
            }},
            {"$unwind": "$items"},
            {"$group": {
                "_id": "$items.name",
                "total_quantity": {"$sum": "$items.quantity"},
                "total_revenue": {"$sum": "$items.total"}
            }},
            {"$sort": {"total_revenue": -1}},
            {"$limit": 10}
        ]

        top_products = await db.orders.aggregate(top_products_pipeline).to_list(length=10)

        # Get detailed sales data
        sales_data = await db.orders.find({
            "created_at": {"$gte": start_date_utc, "$lte": end_date_utc},
            "status": "completed"
        }).sort("created_at", -1).limit(100).to_list(length=100)

        # Format sales data for frontend
        formatted_sales = []
        for order in sales_data:
            formatted_sales.append({
                "date": order["created_at"].strftime("%Y-%m-%d %H:%M"),
                "order_id": order["order_number"],
                "customer": order.get("client_name", "Walk-in Client"),
                "items_count": len(order.get("items", [])),
                "amount": order["total"],
                "status": order["status"].title()
            })

        # Format daily trend data for chart
        chart_labels = []
        chart_revenue = []
        chart_orders = []

        for day in daily_data:
            chart_labels.append(day["_id"])
            chart_revenue.append(day["daily_revenue"])
            chart_orders.append(day["daily_orders"])

        # Format top products for chart
        product_names = []
        product_revenues = []
        product_quantities = []

        for product in top_products:
            product_names.append(product["_id"][:20] + "..." if len(product["_id"]) > 20 else product["_id"])
            product_revenues.append(product["total_revenue"])
            product_quantities.append(product["total_quantity"])

        result = {
            "success": True,
            "summary": {
                "total_revenue": summary["total_revenue"],
                "total_orders": summary["total_orders"],
                "avg_order_value": summary["avg_order_value"],
                "growth_rate": round(growth_rate, 1)  # Round to 1 decimal place
            },
            "daily_trend": daily_data,
            "top_products": top_products,
            "sales_data": formatted_sales,
            "chart_data": {
                "sales_trend": {
                    "labels": chart_labels,
                    "revenue": chart_revenue,
                    "orders": chart_orders
                },
                "top_products": {
                    "labels": product_names,
                    "revenue": product_revenues,
                    "quantities": product_quantities
                }
            }
        }

        print(f"🔍 Sales API Debug - returning data: summary={summary}, daily_data_count={len(daily_data)}, top_products_count={len(top_products)}, sales_data_count={len(formatted_sales)}")

        return result

    except Exception as e:
        print(f"❌ Error in sales data API: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get sales data: {str(e)}")


@reports_routes.get("/financial", response_class=HTMLResponse)
async def financial_report(request: Request):
    """Financial reports page"""
    current_user = await get_current_user_from_cookie(request)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return templates.TemplateResponse(
        "reports/financial.html",
        {
            "request": request,
            "user": current_user,
            "page_title": "Financial Reports"
        }
    )


@reports_routes.get("/test-chart", response_class=HTMLResponse)
async def test_chart(request: Request):
    """Test chart page for debugging"""
    return templates.TemplateResponse("test_chart.html", {"request": request})


@reports_routes.get("/api/inventory-data")
async def get_inventory_data(request: Request):
    """Get inventory data for reports"""
    try:
        db = await get_database()

        # Get inventory overview statistics
        inventory_pipeline = [
            {"$group": {
                "_id": None,
                "total_products": {"$sum": 1},
                "active_products": {"$sum": {"$cond": [{"$eq": ["$is_active", True]}, 1, 0]}},
                "low_stock_products": {"$sum": {"$cond": [
                    {"$and": [
                        {"$eq": ["$is_active", True]},
                        {"$lte": ["$stock_quantity", {"$ifNull": ["$min_stock_level", 10]}]},
                        {"$gt": ["$stock_quantity", 0]}
                    ]}, 1, 0
                ]}},
                "out_of_stock_products": {"$sum": {"$cond": [
                    {"$and": [
                        {"$eq": ["$is_active", True]},
                        {"$eq": ["$stock_quantity", 0]}
                    ]}, 1, 0
                ]}},
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

        # Get low stock products details
        low_stock_products = await db.products.find({
            "is_active": True,
            "$expr": {
                "$and": [
                    {"$lte": ["$stock_quantity", {"$ifNull": ["$min_stock_level", 10]}]},
                    {"$gt": ["$stock_quantity", 0]}
                ]
            }
        }).sort("stock_quantity", 1).limit(20).to_list(length=20)

        # Get out of stock products
        out_of_stock_products = await db.products.find({
            "is_active": True,
            "stock_quantity": 0
        }).sort("name", 1).limit(20).to_list(length=20)

        # Get stock levels by category for chart
        category_pipeline = [
            {"$match": {"is_active": True}},
            {"$group": {
                "_id": "$category_id",
                "category_name": {"$first": "$category_name"},
                "total_products": {"$sum": 1},
                "total_stock": {"$sum": "$stock_quantity"},
                "total_value": {"$sum": {"$multiply": ["$stock_quantity", "$price"]}}
            }},
            {"$sort": {"total_value": -1}}
        ]

        category_cursor = db.products.aggregate(category_pipeline)
        category_data = await category_cursor.to_list(length=None)

        # Format low stock products for frontend
        formatted_low_stock = []
        for product in low_stock_products:
            formatted_low_stock.append({
                "id": str(product["_id"]),
                "name": product.get("name", "Unknown Product"),
                "sku": product.get("sku", "N/A"),
                "current_stock": product.get("stock_quantity", 0),
                "min_stock_level": product.get("min_stock_level", 10),
                "price": product.get("price", 0),
                "category": product.get("category_name", "Uncategorized"),
                "supplier": product.get("supplier", "N/A")
            })

        # Format out of stock products
        formatted_out_of_stock = []
        for product in out_of_stock_products:
            formatted_out_of_stock.append({
                "id": str(product["_id"]),
                "name": product.get("name", "Unknown Product"),
                "sku": product.get("sku", "N/A"),
                "price": product.get("price", 0),
                "category": product.get("category_name", "Uncategorized"),
                "supplier": product.get("supplier", "N/A")
            })

        # Format category data for chart
        formatted_categories = []
        for cat in category_data:
            formatted_categories.append({
                "category": cat.get("category_name", "Uncategorized"),
                "total_products": cat["total_products"],
                "total_stock": cat["total_stock"],
                "total_value": cat["total_value"]
            })

        return {
            "inventory_overview": inventory_overview,
            "low_stock_products": formatted_low_stock,
            "out_of_stock_products": formatted_out_of_stock,
            "category_breakdown": formatted_categories
        }

    except Exception as e:
        print(f"Error getting inventory data: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving inventory data: {str(e)}")


@reports_routes.get("/api/stock-movement")
async def get_stock_movement_data(
    request: Request,
    days: int = Query(30, description="Number of days to look back", ge=1, le=365)
):
    """Get stock movement data for the specified period"""
    try:
        db = await get_database()

        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Get restock movements (stock increases)
        restock_pipeline = [
            {"$match": {
                "restocked_at": {"$gte": start_date, "$lte": end_date}
            }},
            {"$sort": {"restocked_at": -1}},
            {"$limit": 100}  # Limit to recent 100 records
        ]

        restock_cursor = db.restock_history.aggregate(restock_pipeline)
        restock_movements = await restock_cursor.to_list(length=None)

        # Get sales movements (stock decreases) from orders
        sales_pipeline = [
            {"$match": {
                "created_at": {"$gte": start_date, "$lte": end_date},
                "status": "completed"
            }},
            {"$unwind": "$items"},
            {"$project": {
                "product_id": "$items.product_id",
                "product_name": "$items.name",
                "sku": "$items.sku",
                "quantity_sold": "$items.quantity",
                "unit_price": "$items.price",
                "total_value": "$items.total",
                "order_date": "$created_at",
                "order_number": "$order_number",
                "customer_name": "$client_name"
            }},
            {"$sort": {"order_date": -1}},
            {"$limit": 100}  # Limit to recent 100 records
        ]

        sales_cursor = db.orders.aggregate(sales_pipeline)
        sales_movements = await sales_cursor.to_list(length=None)

        # Format restock movements
        formatted_restocks = []
        for movement in restock_movements:
            formatted_restocks.append({
                "id": str(movement["_id"]),
                "type": "restock",
                "product_id": str(movement.get("product_id", "")),
                "product_name": movement.get("product_name", "Unknown Product"),
                "sku": movement.get("product_sku", "N/A"),
                "quantity": movement.get("quantity_added", 0),
                "previous_stock": movement.get("previous_stock", 0),
                "new_stock": movement.get("new_stock", 0),
                "reason": movement.get("reason", "Restock"),
                "user": movement.get("restocked_by_username", "System"),
                "date": movement.get("restocked_at"),
                "reference": f"Restock by {movement.get('restocked_by_username', 'System')}"
            })

        # Format sales movements
        formatted_sales = []
        for movement in sales_movements:
            formatted_sales.append({
                "id": str(movement["_id"]),
                "type": "sale",
                "product_id": str(movement.get("product_id", "")),
                "product_name": movement.get("product_name", "Unknown Product"),
                "sku": movement.get("sku", "N/A"),
                "quantity": -movement.get("quantity_sold", 0),  # Negative for stock decrease
                "unit_price": movement.get("unit_price", 0),
                "total_value": movement.get("total_value", 0),
                "reason": "Sale",
                "user": "POS System",
                "date": movement.get("order_date"),
                "reference": f"Order #{movement.get('order_number', 'N/A')} - {movement.get('customer_name', 'Walk-in Customer')}"
            })

        # Combine and sort all movements by date
        all_movements = formatted_restocks + formatted_sales
        all_movements.sort(key=lambda x: x["date"] if x["date"] else datetime.min, reverse=True)

        # Get movement summary statistics
        total_restocks = len(formatted_restocks)
        total_sales = len(formatted_sales)
        total_restock_quantity = sum(m["quantity"] for m in formatted_restocks)
        total_sales_quantity = abs(sum(m["quantity"] for m in formatted_sales))

        # Get top moving products
        product_movements = {}
        for movement in all_movements:
            product_key = movement["product_name"]
            if product_key not in product_movements:
                product_movements[product_key] = {
                    "product_name": movement["product_name"],
                    "sku": movement["sku"],
                    "total_movements": 0,
                    "restock_quantity": 0,
                    "sales_quantity": 0
                }

            product_movements[product_key]["total_movements"] += 1
            if movement["type"] == "restock":
                product_movements[product_key]["restock_quantity"] += movement["quantity"]
            else:
                product_movements[product_key]["sales_quantity"] += abs(movement["quantity"])

        # Sort by total movement activity
        top_moving_products = sorted(
            product_movements.values(),
            key=lambda x: x["total_movements"],
            reverse=True
        )[:10]

        # Daily movement summary for chart
        daily_summary = {}
        for movement in all_movements:
            if movement["date"]:
                date_key = movement["date"].strftime("%Y-%m-%d")
                if date_key not in daily_summary:
                    daily_summary[date_key] = {
                        "date": date_key,
                        "restocks": 0,
                        "sales": 0,
                        "restock_quantity": 0,
                        "sales_quantity": 0
                    }

                if movement["type"] == "restock":
                    daily_summary[date_key]["restocks"] += 1
                    daily_summary[date_key]["restock_quantity"] += movement["quantity"]
                else:
                    daily_summary[date_key]["sales"] += 1
                    daily_summary[date_key]["sales_quantity"] += abs(movement["quantity"])

        # Convert to list and sort by date
        daily_chart_data = sorted(daily_summary.values(), key=lambda x: x["date"])

        return {
            "summary": {
                "period_days": days,
                "total_movements": len(all_movements),
                "total_restocks": total_restocks,
                "total_sales": total_sales,
                "total_restock_quantity": total_restock_quantity,
                "total_sales_quantity": total_sales_quantity,
                "net_stock_change": total_restock_quantity - total_sales_quantity
            },
            "movements": all_movements[:50],  # Return latest 50 movements
            "top_moving_products": top_moving_products,
            "daily_chart_data": daily_chart_data
        }

    except Exception as e:
        print(f"Error getting stock movement data: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving stock movement data: {str(e)}")
