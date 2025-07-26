from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional
from datetime import datetime
from bson import ObjectId
from ...config.database import get_database
from ...schemas.customer import (
    CustomerCreate, CustomerUpdate, CustomerResponse, CustomerList,
    PurchaseHistory, CustomerPurchaseHistory
)
from ...models import Customer, User
from ...utils.auth import get_current_user

router = APIRouter(prefix="/api/customers", tags=["Customer Management API"])


@router.get("/", response_model=CustomerList)
async def get_customers(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """Get all customers with pagination and filtering"""
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

    customers = [
        CustomerResponse(
            id=str(customer["_id"]),
            name=customer["name"],
            email=customer.get("email"),
            phone=customer.get("phone"),
            address=customer.get("address"),
            city=customer.get("city"),
            postal_code=customer.get("postal_code"),
            country=customer.get("country"),
            date_of_birth=customer.get("date_of_birth"),
            is_active=customer["is_active"],
            total_purchases=customer["total_purchases"],
            total_orders=customer["total_orders"],
            created_at=customer["created_at"],
            updated_at=customer.get("updated_at"),
            last_purchase_date=customer.get("last_purchase_date"),
            notes=customer.get("notes")
        )
        for customer in customers_data
    ]

    return CustomerList(
        customers=customers,
        total=total,
        page=page,
        size=size
    )


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new customer"""
    db = await get_database()

    # Check if customer with same email already exists
    if customer_data.email:
        existing_customer = await db.customers.find_one({"email": customer_data.email})
        if existing_customer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer with this email already exists"
            )

    # Create customer document
    customer_doc = {
        "name": customer_data.name,
        "email": customer_data.email,
        "phone": customer_data.phone,
        "address": customer_data.address,
        "city": customer_data.city,
        "postal_code": customer_data.postal_code,
        "country": customer_data.country,
        "date_of_birth": customer_data.date_of_birth,
        "is_active": True,
        "total_purchases": 0.0,
        "total_orders": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
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
        email=created_customer.get("email"),
        phone=created_customer.get("phone"),
        address=created_customer.get("address"),
        city=created_customer.get("city"),
        postal_code=created_customer.get("postal_code"),
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


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific customer by ID"""
    db = await get_database()

    try:
        customer = await db.customers.find_one({"_id": ObjectId(customer_id)})
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )

        return CustomerResponse(
            id=str(customer["_id"]),
            name=customer["name"],
            email=customer.get("email"),
            phone=customer.get("phone"),
            address=customer.get("address"),
            city=customer.get("city"),
            postal_code=customer.get("postal_code"),
            country=customer.get("country"),
            date_of_birth=customer.get("date_of_birth"),
            is_active=customer["is_active"],
            total_purchases=customer["total_purchases"],
            total_orders=customer["total_orders"],
            created_at=customer["created_at"],
            updated_at=customer.get("updated_at"),
            last_purchase_date=customer.get("last_purchase_date"),
            notes=customer.get("notes")
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid customer ID"
        )


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: str,
    customer_data: CustomerUpdate,
    current_user: User = Depends(get_current_user)
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

        # Check if email is being changed and if new email already exists
        if customer_data.email and customer_data.email != existing_customer.get("email"):
            email_exists = await db.customers.find_one({
                "email": customer_data.email,
                "_id": {"$ne": ObjectId(customer_id)}
            })
            if email_exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Customer with this email already exists"
                )

        # Build update document
        update_doc = {"updated_at": datetime.utcnow()}

        # Only update fields that are provided
        if customer_data.name is not None:
            update_doc["name"] = customer_data.name
        if customer_data.email is not None:
            update_doc["email"] = customer_data.email
        if customer_data.phone is not None:
            update_doc["phone"] = customer_data.phone
        if customer_data.address is not None:
            update_doc["address"] = customer_data.address
        if customer_data.city is not None:
            update_doc["city"] = customer_data.city
        if customer_data.postal_code is not None:
            update_doc["postal_code"] = customer_data.postal_code
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
            email=updated_customer.get("email"),
            phone=updated_customer.get("phone"),
            address=updated_customer.get("address"),
            city=updated_customer.get("city"),
            postal_code=updated_customer.get("postal_code"),
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


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: str,
    current_user: User = Depends(get_current_user)
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
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid customer ID"
        )