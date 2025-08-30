from fastapi import APIRouter, HTTPException, status, Query, Request, Depends
from typing import Optional
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from ...config.database import get_database
from ...schemas.customer import (
    CustomerCreate, CustomerUpdate, CustomerResponse, CustomerList,
    PurchaseHistory, CustomerPurchaseHistory
)
from ...models import Customer, User
from ...utils.auth import get_current_user, get_current_user_hybrid, get_current_user_hybrid_dependency, verify_token, get_user_by_username
from ...utils.timezone import now_kampala, kampala_to_utc
from fastapi.responses import StreamingResponse, JSONResponse, Response
import io
import csv
import vobject # Added for VCF export

router = APIRouter(prefix="/api/customers", tags=["Customer Management API"])


@router.get("/export/google-csv")
async def export_clients_to_csv(
    user: User = Depends(get_current_user_hybrid_dependency()),
    export_type: str = Query("new", enum=["new", "all", "range"]),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None)
):
    """
    Export active clients to a CSV file compatible with Google Contacts.
    Supports exporting all, new since last export, or clients within a date range.
    """
    db = await get_database()
    query = {"is_active": True}
    update_timestamp = False

    if export_type == "new":
        user_doc = await db.users.find_one({"_id": user.id})
        last_export_time = user_doc.get("last_client_export") if user_doc else None
        if last_export_time:
            query["created_at"] = {"$gt": last_export_time}
        update_timestamp = True
    
    elif export_type == "range":
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="Start date and end date are required for range export.")
        try:
            s_date = kampala_to_utc(datetime.fromisoformat(start_date).replace(hour=0, minute=0, second=0))
            e_date = kampala_to_utc(datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59))
            query["created_at"] = {"$gte": s_date, "$lte": e_date}
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Please use YYYY-MM-DD.")

    customers = await db.customers.find(query).sort("created_at", -1).to_list(length=None)

    if not customers:
        return JSONResponse(content={"message": "No clients found for the selected criteria."}, status_code=200)

    string_io = io.StringIO()
    headers = ["Name", "Phone 1 - Value"]
    writer = csv.writer(string_io)
    writer.writerow(headers)

    for customer in customers:
        if customer.get("name") and customer.get("phone"):
            writer.writerow([
                customer.get("name"),
                customer.get("phone")
            ])
            
    string_io.seek(0)

    if update_timestamp:
        await db.users.update_one(
            {"_id": user.id},
            {"$set": {"last_client_export": kampala_to_utc(now_kampala())}}
        )

    filename = f"clients-{export_type}-{datetime.now().strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        iter([string_io.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )




@router.get("/debug/test-connection")
async def test_database_connection():
    """Test database connection and return basic info"""
    try:
        db = await get_database()

        # Test basic database operations
        customers_count = await db.customers.count_documents({})
        orders_count = await db.orders.count_documents({})

        # Get a sample customer if any exist
        sample_customer = await db.customers.find_one({})

        return {
            "status": "success",
            "database_connected": True,
            "customers_count": customers_count,
            "orders_count": orders_count,
            "sample_customer_id": str(sample_customer["_id"]) if sample_customer else None,
            "sample_customer_name": sample_customer.get("name") if sample_customer else None
        }
    except Exception as e:
        return {
            "status": "error",
            "database_connected": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


@router.get("/debug/test-simple/{customer_id}")
async def test_simple_customer_endpoint(customer_id: str):
    """Simple test endpoint to check if routing works"""
    return {
        "message": "Simple endpoint works",
        "customer_id": customer_id,
        "endpoint": "test-simple"
    }


@router.get("/test-customer/{customer_id}")
async def test_get_customer_no_auth(customer_id: str):
    """Test endpoint without any authentication or complex logic"""
    try:
        db = await get_database()

        # Simple validation
        if not ObjectId.is_valid(customer_id):
            return {"error": "Invalid customer ID format", "customer_id": customer_id}

        # Simple database query
        customer = await db.customers.find_one({"_id": ObjectId(customer_id)})

        if not customer:
            return {"error": "Customer not found", "customer_id": customer_id}

        # Return basic customer info
        return {
            "success": True,
            "customer_id": str(customer["_id"]),
            "name": customer.get("name", "Unknown"),
            "phone": customer.get("phone", "No phone"),
            "is_active": customer.get("is_active", True)
        }

    except Exception as e:
        return {
            "error": f"Exception occurred: {str(e)}",
            "customer_id": customer_id,
            "error_type": type(e).__name__
        }


@router.get("/auth-test")
async def test_authentication(request: Request):
    """Test endpoint to verify authentication is working"""
    try:
        user = await get_current_user_hybrid(request)
        return {
            "authenticated": True,
            "user": {
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active
            },
            "message": "Authentication successful!",
            "auth_method": "hybrid"
        }
    except HTTPException as e:
        return {
            "authenticated": False,
            "message": "Authentication failed",
            "error_detail": e.detail,
            "cookies": list(request.cookies.keys()),
            "has_auth_header": bool(request.headers.get("Authorization"))
        }
    except Exception as e:
        return {
            "authenticated": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


@router.get("/debug-auth")
async def debug_authentication(request: Request):
    """Detailed debugging endpoint for authentication issues"""
    debug_info = {
        "cookies": dict(request.cookies),
        "auth_header": request.headers.get("Authorization"),
        "cookie_token_present": "access_token" in request.cookies,
        "cookie_token_value": None,
        "token_after_prefix_removal": None,
        "token_verification": None,
        "payload": None,
        "username_from_payload": None,
        "user_lookup": None,
        "user_active": None
    }

    # Check cookie token
    access_token = request.cookies.get("access_token")
    if access_token:
        debug_info["cookie_token_value"] = access_token[:50] + "..." if len(access_token) > 50 else access_token

        # Remove Bearer prefix if present
        if access_token.startswith("Bearer "):
            token = access_token[7:]
            debug_info["token_after_prefix_removal"] = token[:50] + "..." if len(token) > 50 else token
        else:
            token = access_token
            debug_info["token_after_prefix_removal"] = "No Bearer prefix found"

        # Try to verify token
        try:
            payload = verify_token(token)
            debug_info["token_verification"] = "SUCCESS" if payload else "FAILED"
            debug_info["payload"] = payload

            if payload:
                username = payload.get("sub")
                debug_info["username_from_payload"] = username

                if username:
                    try:
                        user = await get_user_by_username(username)
                        debug_info["user_lookup"] = "FOUND" if user else "NOT_FOUND"
                        if user:
                            debug_info["user_active"] = user.is_active
                            debug_info["user_details"] = {
                                "username": user.username,
                                "email": user.email,
                                "role": user.role,
                                "is_active": user.is_active
                            }
                    except Exception as e:
                        debug_info["user_lookup"] = f"ERROR: {str(e)}"
        except Exception as e:
            debug_info["token_verification"] = f"ERROR: {str(e)}"

    return debug_info


@router.get("/simple-test")
async def simple_test():
    """Ultra simple test endpoint"""
    return {"message": "Simple test works", "status": "success"}


@router.get("/simple-customer-test/{customer_id}")
async def simple_customer_test(customer_id: str):
    """Ultra simple customer test endpoint"""
    return {
        "message": "Simple customer test works",
        "customer_id": customer_id,
        "status": "success"
    }


@router.get("/data/{customer_id}")
async def get_customer_data(customer_id: str):
    """Alternative endpoint to get customer data without authentication"""
    try:
        db = await get_database()

        # Validate ObjectId format
        if not ObjectId.is_valid(customer_id):
            return {
                "error": "Invalid customer ID format",
                "customer_id": customer_id,
                "success": False
            }

        customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
        if not customer:
            return {
                "error": "Customer not found",
                "customer_id": customer_id,
                "success": False
            }

        # Calculate order statistics from orders collection
        order_stats = await db.orders.aggregate([
            {"$match": {"client_id": customer["_id"]}},
            {"$group": {
                "_id": None,
                "total_orders": {"$sum": 1},
                "total_spent": {"$sum": "$total"},
                "last_order_date": {"$max": "$created_at"}
            }}
        ]).to_list(length=1)

        if order_stats:
            stats = order_stats[0]
            total_orders = stats["total_orders"]
            total_purchases = stats["total_spent"]
            last_purchase_date = stats["last_order_date"]
        else:
            total_orders = 0
            total_purchases = 0.0
            last_purchase_date = None

        return {
            "success": True,
            "id": str(customer["_id"]),
            "name": customer["name"],
            "phone": customer.get("phone"),
            "address": customer.get("address"),
            "city": customer.get("city"),
            "country": customer.get("country"),
            "date_of_birth": customer.get("date_of_birth"),
            "is_active": customer["is_active"],
            "total_purchases": total_purchases,
            "total_orders": total_orders,
            "created_at": customer["created_at"],
            "updated_at": customer.get("updated_at"),
            "last_purchase_date": last_purchase_date,
            "notes": customer.get("notes")
        }
    except Exception as e:
        return {
            "error": f"Exception occurred: {str(e)}",
            "customer_id": customer_id,
            "success": False,
            "error_type": type(e).__name__
        }





# All specific routes should come before parameterized routes
@router.get("/", response_model=dict)
async def get_customers(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get all customers with pagination and filtering"""
    db = await get_database()

    # Build filter query
    filter_query = {}
    if search:
        filter_query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}}
        ]
    if is_active is not None:
        filter_query["is_active"] = is_active

    # Get total count
    total = await db.customers.count_documents(filter_query)

    # Get customers with pagination
    skip = (page - 1) * size
    cursor = db.customers.find(filter_query).skip(skip).limit(size).sort("created_at", -1)
    customers_data = await cursor.to_list(length=size)

    customers = []
    for customer in customers_data:
        customer_id = str(customer["_id"])

        # Calculate order statistics from orders collection
        order_stats = await db.orders.aggregate([
            {"$match": {"client_id": customer["_id"]}},
            {"$group": {
                "_id": None,
                "total_orders": {"$sum": 1},
                "total_spent": {"$sum": "$total"},
                "last_order_date": {"$max": "$created_at"}
            }}
        ]).to_list(length=1)

        if order_stats:
            stats = order_stats[0]
            total_orders = stats["total_orders"]
            total_purchases = stats["total_spent"]
            last_purchase_date = stats["last_order_date"]
        else:
            total_orders = 0
            total_purchases = 0
            last_purchase_date = None

        customers.append({
            "id": customer_id,
            "name": customer["name"],
            "phone": customer.get("phone", ""),
            "address": customer.get("address", ""),
            "city": customer.get("city", ""),
            "country": customer.get("country", ""),
            "date_of_birth": customer.get("date_of_birth"),
            "is_active": customer["is_active"],
            "total_purchases": total_purchases,
            "total_orders": total_orders,
            "created_at": customer["created_at"].isoformat(),
            "updated_at": customer.get("updated_at", customer["created_at"]).isoformat(),
            "last_purchase_date": last_purchase_date.isoformat() if last_purchase_date else None,
            "notes": customer.get("notes", "")
        })

    return {
        "customers": customers,
        "total": total,
        "page": page,
        "size": size,
        "total_pages": (total + size - 1) // size
    }


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create a new customer"""
    db = await get_database()



    # Create customer document
    customer_doc = {
        "name": customer_data.name,
        "phone": customer_data.phone,
        "address": customer_data.address,
        "city": customer_data.city,
        "country": customer_data.country,
        "date_of_birth": customer_data.date_of_birth,
        "is_active": True,
        "total_purchases": 0.0,
        "total_orders": 0,
        "created_at": kampala_to_utc(now_kampala()),
        "updated_at": kampala_to_utc(now_kampala()),
        "last_purchase_date": None,
        "notes": customer_data.notes
    }

    # Insert customer
    result = await db.customers.insert_one(customer_doc)

    # Get the created customer
    created_customer = await db.customers.find_one({"_id": result.inserted_id})

    return CustomerResponse(
        id=str(created_customer["_id"]),
        name=created_customer["name"],
        phone=created_customer.get("phone"),
        address=created_customer.get("address"),
        city=created_customer.get("city"),
        country=created_customer.get("country"),
        date_of_birth=created_customer.get("date_of_birth"),
        is_active=created_customer["is_active"],
        total_purchases=created_customer["total_purchases"],
        total_orders=created_customer["total_orders"],
        created_at=created_customer["created_at"],
        updated_at=created_customer.get("updated_at"),
        last_purchase_date=created_customer.get("last_purchase_date"),
        notes=created_customer.get("notes")
    )

@router.get("/table", response_model=dict)
async def get_customers_for_table(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get customers for table display with pagination"""
    try:
        db = await get_database()

        # Build filter query
        filter_query = {}
        if search:
            filter_query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"phone": {"$regex": search, "$options": "i"}}
            ]
        if is_active is not None:
            filter_query["is_active"] = is_active

        # Get total count
        total = await db.customers.count_documents(filter_query)

        # Get customers with pagination
        skip = (page - 1) * size
        cursor = db.customers.find(filter_query).skip(skip).limit(size).sort("created_at", -1)
        customers_data = await cursor.to_list(length=size)

        # Convert ObjectId to string and format data for table
        customers = []
        for customer in customers_data:
            customer_dict = {
                "id": str(customer["_id"]),
                "name": customer.get("name", ""),
                "phone": customer.get("phone"),
                "total_orders": customer.get("total_orders", 0),
                "total_purchases": customer.get("total_purchases", 0.0),
                "is_active": customer.get("is_active", True),
                "notes": customer.get("notes"),
                "created_at": customer.get("created_at"),
                "last_purchase_date": customer.get("last_purchase_date")
            }
            customers.append(customer_dict)

        return {
            "customers": customers,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size,
            "has_next": page * size < total,
            "has_prev": page > 1
        }

    except Exception as e:
        print(f"Error fetching customers for table: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching customers for table"
        )


@router.get("/stats", response_model=dict)
async def get_customer_stats(
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get customer statistics without fetching all customer data"""
    try:
        db = await get_database()

        # Get total customers count
        total_customers = await db.customers.count_documents({})

        # Get active customers count
        active_customers = await db.customers.count_documents({"is_active": True})

        # Get aggregated statistics using MongoDB aggregation pipeline
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total_orders": {"$sum": "$total_orders"},
                    "total_revenue": {"$sum": "$total_purchases"}
                }
            }
        ]

        aggregation_result = await db.customers.aggregate(pipeline).to_list(length=1)

        if aggregation_result:
            total_orders = aggregation_result[0]["total_orders"]
            total_revenue = aggregation_result[0]["total_revenue"]
        else:
            total_orders = 0
            total_revenue = 0.0

        return {
            "total_customers": total_customers,
            "active_customers": active_customers,
            "total_orders": total_orders,
            "total_revenue": total_revenue
        }

    except Exception as e:
        print(f"Error fetching customer stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching customer statistics"
        )




@router.get("/{customer_id}")
async def get_customer(
    customer_id: str,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get a specific customer by ID"""
    db = await get_database()

    try:
        # Validate ObjectId format
        if not ObjectId.is_valid(customer_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid customer ID format"
            )

        customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )

        # Calculate order statistics from orders collection (same as in get_customers)
        order_stats = await db.orders.aggregate([
            {"$match": {"client_id": customer["_id"]}},
            {"$group": {
                "_id": None,
                "total_orders": {"$sum": 1},
                "total_spent": {"$sum": "$total"},
                "last_order_date": {"$max": "$created_at"}
            }}
        ]).to_list(length=1)

        if order_stats:
            stats = order_stats[0]
            total_orders = stats["total_orders"]
            total_purchases = stats["total_spent"]
            last_purchase_date = stats["last_order_date"]
        else:
            total_orders = 0
            total_purchases = 0.0
            last_purchase_date = None

        return {
            "id": str(customer["_id"]),
            "name": customer["name"],
            "phone": customer.get("phone"),
            "address": customer.get("address"),
            "city": customer.get("city"),
            "country": customer.get("country"),
            "date_of_birth": customer.get("date_of_birth"),
            "is_active": customer["is_active"],
            "total_purchases": total_purchases,
            "total_orders": total_orders,
            "created_at": customer["created_at"],
            "updated_at": customer.get("updated_at"),
            "last_purchase_date": last_purchase_date,
            "notes": customer.get("notes")
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching customer {customer_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while fetching customer details"
        )


@router.get("/{customer_id}/orders", response_model=dict)
async def get_customer_orders(
    customer_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get orders for a specific customer with pagination"""
    db = await get_database()

    try:
        # Validate ObjectId format
        if not ObjectId.is_valid(customer_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid customer ID format"
            )

        # Verify customer exists
        customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )

        # Build filter query for orders
        filter_query = {"client_id": ObjectId(customer_id)}

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
                    created_by_id = order["created_by"]
                    if isinstance(created_by_id, str) and created_by_id:
                        created_by_id = ObjectId(created_by_id)
                    elif isinstance(created_by_id, ObjectId):
                        pass  # Already an ObjectId
                    else:
                        created_by_id = None

                    if created_by_id:
                        user_doc = await db.users.find_one({"_id": created_by_id})
                        if user_doc:
                            created_by_name = user_doc.get("full_name", "Staff Member")
                except:
                    created_by_name = "Staff Member"

            orders.append({
                "id": str(order["_id"]),
                "order_number": order["order_number"],
                "client_id": str(order.get("client_id", "")),
                "client_name": order.get("client_name", "Walk-in Client"),
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
            "success": True,
            "orders": orders,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size,
            "has_next": page * size < total,
            "has_prev": page > 1
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch customer orders: {str(e)}"
        )


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: str,
    request: Request,
    customer_data: CustomerUpdate,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Update a customer"""
    db = await get_database()

    try:
        # Check if customer exists
        existing_customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
        if not existing_customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )



        # Build update document
        update_doc = {"updated_at": kampala_to_utc(now_kampala())}

        # Only update fields that are provided
        if customer_data.name is not None:
            update_doc["name"] = customer_data.name
        if customer_data.phone is not None:
            update_doc["phone"] = customer_data.phone
        if customer_data.address is not None:
            update_doc["address"] = customer_data.address
        if customer_data.city is not None:
            update_doc["city"] = customer_data.city
        if customer_data.country is not None:
            update_doc["country"] = customer_data.country
        if customer_data.date_of_birth is not None:
            update_doc["date_of_birth"] = customer_data.date_of_birth
        if customer_data.is_active is not None:
            update_doc["is_active"] = customer_data.is_active
        if customer_data.notes is not None:
            update_doc["notes"] = customer_data.notes

        # Update customer
        await db.customers.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": update_doc}
        )

        # Get updated customer
        updated_customer = await db.customers.find_one({"_id": ObjectId(customer_id)})

        return CustomerResponse(
            id=str(updated_customer["_id"]),
            name=updated_customer["name"],
            phone=updated_customer.get("phone"),
            address=updated_customer.get("address"),
            city=updated_customer.get("city"),
            country=updated_customer.get("country"),
            date_of_birth=updated_customer.get("date_of_birth"),
            is_active=updated_customer["is_active"],
            total_purchases=updated_customer["total_purchases"],
            total_orders=updated_customer["total_orders"],
            created_at=updated_customer["created_at"],
            updated_at=updated_customer.get("updated_at"),
            last_purchase_date=updated_customer.get("last_purchase_date"),
            notes=updated_customer.get("notes")
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid customer ID"
        )


@router.get("/export-vcf", response_class=StreamingResponse)
async def export_customers_vcf(
    current_user: User = Depends(get_current_user_hybrid_dependency()),
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Export all customers as a VCF file"""
    customers = await db.customers.find({}).to_list(length=None)

    def generate_vcf():
        for customer in customers:
            card = vobject.vCard()
            
            # Name (FN - Formatted Name, N - Name)
            if customer.get("name"):
                card.add("fn")
                card.fn.value = customer["name"]
                
                # Attempt to parse name into components for N field
                name_parts = customer["name"].split(" ", 1)
                card.add("n")
                if len(name_parts) > 1:
                    card.n.value = vobject.vcard.Name(family=name_parts[1], given=name_parts[0])
                else:
                    card.n.value = vobject.vcard.Name(given=name_parts[0])

            # Phone
            if customer.get("phone"):
                tel = card.add("tel")
                tel.value = customer["phone"]
                tel.type_param = "CELL" # Assuming mobile phone

            # Address
            # VCF 3.0 ADR field: PO Box; Extended Address; Street; City; Region; Postal Code; Country
            # We have address, city, country. Mapping them to Street, City, Country
            if customer.get("address") or customer.get("city") or customer.get("country"):
                adr = card.add("adr")
                adr.type_param = "WORK" # Assuming work address or general address
                adr.value = vobject.vcard.Address(
                    street=customer.get("address", ""),
                    city=customer.get("city", ""),
                    country=customer.get("country", "")
                )
            
            # Notes/Description
            if customer.get("notes"):
                card.add("note")
                card.note.value = customer["notes"]

            yield card.serialize().encode('utf-8') # Encode to bytes for StreamingResponse

    headers = {
        "Content-Disposition": "attachment; filename=\"customers.vcf\"",

        "Content-Type": "text/vcard; charset=utf-8"
    }
    return StreamingResponse(generate_vcf(), headers=headers)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: str,
    request: Request,
    user: User = Depends(get_current_user_hybrid_dependency())
):
    """Delete a customer (soft delete by setting is_active to False)"""
    db = await get_database()

    try:
        # Check if customer exists
        customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )

        # Soft delete by setting is_active to False
        await db.customers.update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": {"is_active": False, "updated_at": kampala_to_utc(now_kampala())}}
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid customer ID"
        )