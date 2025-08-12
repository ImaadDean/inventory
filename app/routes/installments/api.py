from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from typing import Optional, List
from datetime import datetime, timedelta
import datetime as dt
from bson import ObjectId
from ...config.database import get_database
from ...schemas.installment import (
    InstallmentCreate, InstallmentResponse, InstallmentUpdate,
    InstallmentPaymentRecordCreate, InstallmentPaymentRecordResponse,
    InstallmentListResponse, InstallmentSummary, POSInstallmentCreate,
    InstallmentPaymentResponse
)
from ...models import User, Installment, InstallmentPayment, InstallmentPaymentRecord, InstallmentStatus, PaymentStatus
from ...utils.auth import get_current_user, require_admin_or_manager, verify_token, get_user_by_username
from ...utils.timezone import now_kampala, kampala_to_utc
import uuid

router = APIRouter(prefix="/api/installments", tags=["Installments API"])


async def get_current_user_from_cookie(request: Request):
    """Get current user from cookie for POS routes"""
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
    if not user or not user.is_active:
        return None

    return user


def calculate_payment_schedule(
    remaining_amount: float,
    number_of_payments: int,
    payment_frequency: str,
    first_payment_date: datetime
) -> List[InstallmentPayment]:
    """Calculate payment schedule based on parameters"""
    payments = []
    payment_amount = remaining_amount / number_of_payments
    
    # Calculate frequency in days
    frequency_days = {
        "weekly": 7,
        "bi-weekly": 14,
        "monthly": 30
    }
    
    days_between = frequency_days.get(payment_frequency, 30)
    
    for i in range(number_of_payments):
        due_date = first_payment_date + timedelta(days=i * days_between)
        payment = InstallmentPayment(
            payment_number=i + 1,
            due_date=due_date,
            amount_due=payment_amount
        )
        payments.append(payment)
    
    return payments


@router.post("/", response_model=InstallmentResponse)
async def create_installment(
    installment_data: InstallmentCreate,
    current_user: User = Depends(require_admin_or_manager)
):
    """Create a new installment plan (Admin/Manager only)"""
    try:
        db = await get_database()
        
        # Generate installment number
        installment_count = await db.installments.count_documents({})
        installment_number = f"INST-{installment_count + 1:06d}"
        
        # Calculate remaining amount
        remaining_amount = installment_data.total_amount - installment_data.down_payment
        
        if remaining_amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Remaining amount must be greater than 0"
            )
        
        # Calculate payment schedule
        payments = calculate_payment_schedule(
            remaining_amount,
            installment_data.number_of_payments,
            installment_data.payment_frequency,
            installment_data.first_payment_date
        )
        
        # Create installment document
        installment_doc = {
            "installment_number": installment_number,
            "customer_id": ObjectId(installment_data.customer_id) if installment_data.customer_id else None,
            "customer_name": installment_data.customer_name,
            "customer_phone": installment_data.customer_phone,
            "customer_email": installment_data.customer_email,
            "items": [item.dict() for item in installment_data.items],
            "total_amount": installment_data.total_amount,
            "down_payment": installment_data.down_payment,
            "remaining_amount": remaining_amount,
            "number_of_payments": installment_data.number_of_payments,
            "payment_frequency": installment_data.payment_frequency,
            "payments": [
                {
                    "payment_number": payment.payment_number,
                    "due_date": payment.due_date,
                    "amount_due": payment.amount_due,
                    "amount_paid": payment.amount_paid,
                    "payment_date": payment.payment_date,
                    "status": payment.status,
                    "notes": payment.notes
                }
                for payment in payments
            ],
            "status": InstallmentStatus.ACTIVE,
            "created_by": current_user.id,
            "created_at": kampala_to_utc(now_kampala()),
            "notes": installment_data.notes,
            "terms_and_conditions": installment_data.terms_and_conditions
        }
        
        # Insert installment
        result = await db.installments.insert_one(installment_doc)
        
        # Get created installment
        created_installment = await db.installments.find_one({"_id": result.inserted_id})
        
        # Convert to response format
        return await format_installment_response(created_installment, db)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create installment: {str(e)}"
        )


@router.get("/", response_model=InstallmentListResponse)
async def get_installments(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[InstallmentStatus] = None,
    customer_name: Optional[str] = None,
    overdue_only: bool = False
):
    """Get installments with pagination and filtering (Admin/Manager only)"""
    try:
        # Get current user from cookie
        current_user = await get_current_user_from_cookie(request)
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )

        # Check if user has admin or manager role
        if current_user.role not in ['admin', 'inventory_manager']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. Admin or Manager role required."
            )

        db = await get_database()
        
        # Build filter query
        filter_query = {}
        
        if status:
            filter_query["status"] = status
            
        if customer_name:
            filter_query["customer_name"] = {"$regex": customer_name, "$options": "i"}
        
        if overdue_only:
            # Find installments with overdue payments
            current_date = kampala_to_utc(now_kampala())
            filter_query["payments"] = {
                "$elemMatch": {
                    "due_date": {"$lt": current_date},
                    "status": {"$in": [PaymentStatus.PENDING, PaymentStatus.PARTIAL]}
                }
            }
        
        # Get total count
        total = await db.installments.count_documents(filter_query)
        
        # Get installments with pagination
        skip = (page - 1) * size
        cursor = db.installments.find(filter_query).skip(skip).limit(size).sort("created_at", -1)
        installments_data = await cursor.to_list(length=size)
        
        # Format response
        installments = []
        for installment in installments_data:
            formatted = await format_installment_response(installment, db)
            installments.append(formatted)
        
        total_pages = (total + size - 1) // size
        
        return InstallmentListResponse(
            installments=installments,
            total=total,
            page=page,
            size=size,
            total_pages=total_pages
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get installments: {str(e)}"
        )


@router.get("/summary", response_model=InstallmentSummary)
async def get_installments_summary(request: Request):
    """Get installments summary statistics (Admin/Manager only)"""
    try:
        # Get current user from cookie
        current_user = await get_current_user_from_cookie(request)
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )

        # Check if user has admin or manager role
        if current_user.role not in ['admin', 'inventory_manager']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. Admin or Manager role required."
            )

        db = await get_database()
        
        # Get counts by status
        total_installments = await db.installments.count_documents({})
        active_installments = await db.installments.count_documents({"status": InstallmentStatus.ACTIVE})
        completed_installments = await db.installments.count_documents({"status": InstallmentStatus.COMPLETED})
        
        # Get overdue installments
        current_date = kampala_to_utc(now_kampala())
        overdue_installments = await db.installments.count_documents({
            "status": InstallmentStatus.ACTIVE,
            "payments": {
                "$elemMatch": {
                    "due_date": {"$lt": current_date},
                    "status": {"$in": [PaymentStatus.PENDING, PaymentStatus.PARTIAL]}
                }
            }
        })
        
        # Calculate financial totals
        pipeline = [
            {"$match": {"status": {"$in": [InstallmentStatus.ACTIVE, InstallmentStatus.COMPLETED]}}},
            {"$group": {
                "_id": None,
                "total_amount_outstanding": {"$sum": "$remaining_amount"},
                "total_amount_collected": {"$sum": "$down_payment"}
            }}
        ]
        
        financial_data = await db.installments.aggregate(pipeline).to_list(length=1)
        
        if financial_data:
            total_amount_outstanding = financial_data[0].get("total_amount_outstanding", 0)
            total_amount_collected = financial_data[0].get("total_amount_collected", 0)
        else:
            total_amount_outstanding = 0
            total_amount_collected = 0
        
        # Calculate overdue amount (simplified - would need more complex aggregation for exact amount)
        overdue_amount = 0  # TODO: Implement proper overdue amount calculation
        
        return InstallmentSummary(
            total_installments=total_installments,
            active_installments=active_installments,
            completed_installments=completed_installments,
            overdue_installments=overdue_installments,
            total_amount_outstanding=total_amount_outstanding,
            total_amount_collected=total_amount_collected,
            overdue_amount=overdue_amount
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get installments summary: {str(e)}"
        )


async def format_installment_response(installment_doc: dict, db) -> InstallmentResponse:
    """Helper function to format installment document to response"""
    # Format payments
    payments = []
    for payment_data in installment_doc.get("payments", []):
        # Ensure due_date is timezone-aware for comparison
        due_date = payment_data["due_date"]
        if due_date.tzinfo is None:
            # If naive datetime, assume it's UTC
            due_date = due_date.replace(tzinfo=dt.timezone.utc)

        payment = InstallmentPaymentResponse(
            payment_number=payment_data["payment_number"],
            due_date=due_date,
            amount_due=payment_data["amount_due"],
            amount_paid=payment_data.get("amount_paid", 0),
            payment_date=payment_data.get("payment_date"),
            status=payment_data.get("status", PaymentStatus.PENDING),
            remaining_amount=payment_data["amount_due"] - payment_data.get("amount_paid", 0),
            is_overdue=due_date < kampala_to_utc(now_kampala()) and payment_data.get("status") != PaymentStatus.PAID,
            notes=payment_data.get("notes")
        )
        payments.append(payment)
    
    # Calculate totals
    total_paid = installment_doc.get("down_payment", 0) + sum(p.amount_paid for p in payments)
    total_remaining = max(0, installment_doc["total_amount"] - total_paid)
    completion_percentage = (total_paid / installment_doc["total_amount"]) * 100 if installment_doc["total_amount"] > 0 else 0
    
    # Find next payment due
    next_payment_due = None
    for payment in payments:
        if payment.status in [PaymentStatus.PENDING, PaymentStatus.PARTIAL, PaymentStatus.OVERDUE]:
            next_payment_due = payment
            break
    
    # Find overdue payments
    overdue_payments = [p for p in payments if p.is_overdue and p.status != PaymentStatus.PAID]
    
    return InstallmentResponse(
        id=str(installment_doc["_id"]),
        installment_number=installment_doc["installment_number"],
        customer_id=str(installment_doc["customer_id"]) if installment_doc.get("customer_id") else None,
        customer_name=installment_doc["customer_name"],
        customer_phone=installment_doc.get("customer_phone"),
        customer_email=installment_doc.get("customer_email"),
        order_id=str(installment_doc["order_id"]) if installment_doc.get("order_id") else None,
        items=installment_doc["items"],
        total_amount=installment_doc["total_amount"],
        down_payment=installment_doc.get("down_payment", 0),
        remaining_amount=installment_doc["remaining_amount"],
        number_of_payments=installment_doc["number_of_payments"],
        payment_frequency=installment_doc["payment_frequency"],
        payments=payments,
        status=installment_doc["status"],
        created_by=str(installment_doc["created_by"]),
        approved_by=str(installment_doc["approved_by"]) if installment_doc.get("approved_by") else None,
        created_at=installment_doc["created_at"],
        updated_at=installment_doc.get("updated_at"),
        completed_at=installment_doc.get("completed_at"),
        notes=installment_doc.get("notes"),
        terms_and_conditions=installment_doc.get("terms_and_conditions"),
        total_paid=total_paid,
        total_remaining=total_remaining,
        completion_percentage=completion_percentage,
        next_payment_due=next_payment_due,
        overdue_payments=overdue_payments
    )


@router.get("/{installment_id}", response_model=InstallmentResponse)
async def get_installment(
    installment_id: str,
    request: Request
):
    """Get a specific installment by ID (Admin/Manager only)"""
    try:
        # Get current user from cookie
        current_user = await get_current_user_from_cookie(request)
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )

        # Check if user has admin or manager role
        if current_user.role not in ['admin', 'inventory_manager']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. Admin or Manager role required."
            )

        db = await get_database()

        if not ObjectId.is_valid(installment_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid installment ID"
            )

        installment = await db.installments.find_one({"_id": ObjectId(installment_id)})

        if not installment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Installment not found"
            )

        return await format_installment_response(installment, db)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get installment: {str(e)}"
        )


@router.put("/{installment_id}", response_model=InstallmentResponse)
async def update_installment(
    installment_id: str,
    installment_data: InstallmentUpdate,
    current_user: User = Depends(require_admin_or_manager)
):
    """Update an installment (Admin/Manager only)"""
    try:
        db = await get_database()

        if not ObjectId.is_valid(installment_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid installment ID"
            )

        # Check if installment exists
        existing_installment = await db.installments.find_one({"_id": ObjectId(installment_id)})
        if not existing_installment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Installment not found"
            )

        # Build update document
        update_doc = {"updated_at": kampala_to_utc(now_kampala())}

        if installment_data.customer_phone is not None:
            update_doc["customer_phone"] = installment_data.customer_phone
        if installment_data.customer_email is not None:
            update_doc["customer_email"] = installment_data.customer_email
        if installment_data.status is not None:
            update_doc["status"] = installment_data.status
            if installment_data.status == InstallmentStatus.COMPLETED:
                update_doc["completed_at"] = kampala_to_utc(now_kampala())
        if installment_data.notes is not None:
            update_doc["notes"] = installment_data.notes
        if installment_data.terms_and_conditions is not None:
            update_doc["terms_and_conditions"] = installment_data.terms_and_conditions

        # Update installment
        await db.installments.update_one(
            {"_id": ObjectId(installment_id)},
            {"$set": update_doc}
        )

        # Get updated installment
        updated_installment = await db.installments.find_one({"_id": ObjectId(installment_id)})

        return await format_installment_response(updated_installment, db)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update installment: {str(e)}"
        )


@router.post("/{installment_id}/payments", response_model=InstallmentPaymentRecordResponse)
async def record_payment(
    installment_id: str,
    payment_data: InstallmentPaymentRecordCreate,
    request: Request
):
    """Record a payment for an installment (Admin/Manager only)"""
    try:
        # Get current user from cookie
        current_user = await get_current_user_from_cookie(request)
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )

        # Check if user has admin or manager role
        if current_user.role not in ['admin', 'inventory_manager']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin or Manager role required."
            )

        db = await get_database()

        if not ObjectId.is_valid(installment_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid installment ID"
            )

        # Get installment
        installment = await db.installments.find_one({"_id": ObjectId(installment_id)})
        if not installment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Installment not found"
            )

        # Find the payment to update
        payments = installment.get("payments", [])
        payment_to_update = None
        payment_index = None

        for i, payment in enumerate(payments):
            if payment["payment_number"] == payment_data.payment_number:
                payment_to_update = payment
                payment_index = i
                break

        if not payment_to_update:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment number {payment_data.payment_number} not found"
            )

        # Update payment
        new_amount_paid = payment_to_update.get("amount_paid", 0) + payment_data.amount
        payment_to_update["amount_paid"] = new_amount_paid
        payment_to_update["payment_date"] = kampala_to_utc(now_kampala())

        # Update payment status
        if new_amount_paid >= payment_to_update["amount_due"]:
            payment_to_update["status"] = PaymentStatus.PAID
        elif new_amount_paid > 0:
            payment_to_update["status"] = PaymentStatus.PARTIAL

        # Update installment
        await db.installments.update_one(
            {"_id": ObjectId(installment_id)},
            {
                "$set": {
                    f"payments.{payment_index}": payment_to_update,
                    "updated_at": kampala_to_utc(now_kampala())
                }
            }
        )

        # Generate receipt number
        receipt_count = await db.installment_payments.count_documents({})
        receipt_number = f"INST-PAY-{receipt_count + 1:06d}"

        # Create payment record
        payment_record = {
            "installment_id": ObjectId(installment_id),
            "payment_number": payment_data.payment_number,
            "amount": payment_data.amount,
            "payment_method": payment_data.payment_method,
            "payment_date": kampala_to_utc(now_kampala()),
            "received_by": current_user.id,
            "receipt_number": receipt_number,
            "notes": payment_data.notes
        }

        result = await db.installment_payments.insert_one(payment_record)

        # Check if installment is completed
        updated_installment = await db.installments.find_one({"_id": ObjectId(installment_id)})
        all_payments_completed = all(
            p.get("status") == PaymentStatus.PAID
            for p in updated_installment.get("payments", [])
        )

        if all_payments_completed:
            await db.installments.update_one(
                {"_id": ObjectId(installment_id)},
                {
                    "$set": {
                        "status": InstallmentStatus.COMPLETED,
                        "completed_at": kampala_to_utc(now_kampala())
                    }
                }
            )

        # Return payment record
        return InstallmentPaymentRecordResponse(
            id=str(result.inserted_id),
            installment_id=installment_id,
            payment_number=payment_data.payment_number,
            amount=payment_data.amount,
            payment_method=payment_data.payment_method,
            payment_date=payment_record["payment_date"],
            received_by=str(current_user.id),
            receipt_number=receipt_number,
            notes=payment_data.notes
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record payment: {str(e)}"
        )


@router.post("/pos", response_model=InstallmentResponse)
async def create_installment_from_pos(
    request: Request,
    installment_data: POSInstallmentCreate
):
    """Create installment from POS system (Admin/Manager only)"""
    try:
        # Get current user from cookie
        current_user = await get_current_user_from_cookie(request)
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )

        # Check if user has admin or manager role
        if current_user.role not in ['admin', 'inventory_manager']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. Admin or Manager role required."
            )

        db = await get_database()

        # Generate installment number
        installment_count = await db.installments.count_documents({})
        installment_number = f"INST-{installment_count + 1:06d}"

        # Calculate remaining amount
        remaining_amount = installment_data.total_amount - installment_data.down_payment

        if remaining_amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Remaining amount must be greater than 0"
            )

        # Calculate first payment date (default to next month)
        first_payment_date = kampala_to_utc(now_kampala()) + timedelta(days=30)

        # Calculate payment schedule
        payments = calculate_payment_schedule(
            remaining_amount,
            installment_data.number_of_payments,
            installment_data.payment_frequency,
            first_payment_date
        )

        # Convert POS items to installment items format
        items = []
        for item in installment_data.items:
            items.append({
                "product_id": item.get("product_id", ""),
                "product_name": item.get("name", ""),
                "quantity": item.get("quantity", 1),
                "unit_price": item.get("price", 0),
                "total_price": item.get("total", item.get("price", 0) * item.get("quantity", 1))
            })

        # Create installment document
        installment_doc = {
            "installment_number": installment_number,
            "customer_id": ObjectId(installment_data.customer_id) if installment_data.customer_id else None,
            "customer_name": installment_data.customer_name,
            "customer_phone": installment_data.customer_phone,
            "items": items,
            "total_amount": installment_data.total_amount,
            "down_payment": installment_data.down_payment,
            "remaining_amount": remaining_amount,
            "number_of_payments": installment_data.number_of_payments,
            "payment_frequency": installment_data.payment_frequency,
            "payments": [
                {
                    "payment_number": payment.payment_number,
                    "due_date": payment.due_date,
                    "amount_due": payment.amount_due,
                    "amount_paid": payment.amount_paid,
                    "payment_date": payment.payment_date,
                    "status": payment.status,
                    "notes": payment.notes
                }
                for payment in payments
            ],
            "status": InstallmentStatus.ACTIVE,
            "created_by": current_user.id,
            "created_at": kampala_to_utc(now_kampala()),
            "notes": installment_data.notes,
            "terms_and_conditions": "Standard installment terms apply. Payments must be made on time."
        }

        # Insert installment
        result = await db.installments.insert_one(installment_doc)

        # Get created installment
        created_installment = await db.installments.find_one({"_id": result.inserted_id})

        # Convert to response format
        return await format_installment_response(created_installment, db)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create installment from POS: {str(e)}"
        )


@router.delete("/{installment_id}")
async def cancel_installment(
    installment_id: str,
    current_user: User = Depends(require_admin_or_manager)
):
    """Cancel an installment (Admin/Manager only)"""
    try:
        db = await get_database()

        if not ObjectId.is_valid(installment_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid installment ID"
            )

        # Check if installment exists
        installment = await db.installments.find_one({"_id": ObjectId(installment_id)})
        if not installment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Installment not found"
            )

        # Check if installment can be cancelled
        if installment["status"] == InstallmentStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot cancel a completed installment"
            )

        # Update installment status to cancelled
        await db.installments.update_one(
            {"_id": ObjectId(installment_id)},
            {
                "$set": {
                    "status": InstallmentStatus.CANCELLED,
                    "updated_at": kampala_to_utc(now_kampala())
                }
            }
        )

        return {"message": "Installment cancelled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel installment: {str(e)}"
        )
