from fastapi import APIRouter, HTTPException, status as fastapi_status, Depends, Query, Request
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
from ...models import User, Installment, InstallmentPayment, InstallmentPaymentRecord, InstallmentStatus, PaymentStatus, OrderPaymentStatus
from ...utils.auth import get_current_user, get_current_user_hybrid_dependency, require_admin_or_manager, verify_token, get_user_by_username
from ...utils.timezone import now_kampala, kampala_to_utc
import uuid

router = APIRouter(prefix="/api/installments", tags=["Installments API"])


def calculate_payment_schedule(remaining_amount: float, number_of_payments: int, payment_frequency: str, first_payment_date: datetime) -> List[InstallmentPayment]:
    """Calculate payment schedule for installment plan"""
    payments = []
    payment_amount = remaining_amount / number_of_payments

    # Calculate frequency in days
    frequency_days = {
        "weekly": 7,
        "bi-weekly": 14,
        "monthly": 30
    }

    days_between_payments = frequency_days.get(payment_frequency, 30)

    for i in range(number_of_payments):
        payment_number = i + 1
        due_date = first_payment_date + timedelta(days=i * days_between_payments)

        # For the last payment, adjust amount to handle rounding differences
        if payment_number == number_of_payments:
            # Calculate what's been allocated so far
            allocated_so_far = payment_amount * (number_of_payments - 1)
            final_payment_amount = remaining_amount - allocated_so_far
        else:
            final_payment_amount = payment_amount

        payment = InstallmentPayment(
            payment_number=payment_number,
            due_date=due_date,
            amount_due=final_payment_amount,
            amount_paid=0.0,
            payment_date=None,
            status=PaymentStatus.PENDING,
            notes=None
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
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
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
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create installment: {str(e)}"
        )


@router.get("/", response_model=InstallmentListResponse)
async def get_installments(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[InstallmentStatus] = None,
    customer_name: Optional[str] = None,
    overdue_only: bool = False,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get installments with pagination and filtering (Admin/Manager only)"""
    try:
        # Check if user has admin or manager role
        if current_user.role not in ['admin', 'inventory_manager']:
            raise HTTPException(
                status_code=fastapi_status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. Admin or Manager role required."
            )

        db = await get_database()
        
        # Build filter query
        filter_query = {"total_amount": {"$gt": 0}}
        
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
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get installments: {str(e)}"
        )


@router.get("/summary", response_model=InstallmentSummary)
async def get_installments_summary(current_user: User = Depends(get_current_user_hybrid_dependency())):
    """Get installments summary statistics (Admin/Manager only)"""
    try:
        # Check if user has admin or manager role
        if current_user.role not in ['admin', 'inventory_manager']:
            raise HTTPException(
                status_code=fastapi_status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. Admin or Manager role required."
            )

        db = await get_database()
        
        valid_installments_filter = {"total_amount": {"$gt": 0}}

        # Get counts by status
        total_installments = await db.installments.count_documents(valid_installments_filter)
        active_installments = await db.installments.count_documents({**valid_installments_filter, "status": InstallmentStatus.ACTIVE})
        completed_installments = await db.installments.count_documents({**valid_installments_filter, "status": InstallmentStatus.COMPLETED})
        
        # Get overdue installments
        current_date = kampala_to_utc(now_kampala())
        overdue_installments = await db.installments.count_documents({
            **valid_installments_filter,
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
            {"$match": {**valid_installments_filter, "status": {"$in": [InstallmentStatus.ACTIVE, InstallmentStatus.COMPLETED]}}},
            {"$addFields": {
                "total_paid": {
                    "$add": ["$down_payment", {"$sum": "$payments.amount_paid"}]
                }
            }},
            {"$addFields": {
                "current_remaining": {
                    "$subtract": ["$total_amount", "$total_paid"]
                }
            }},
            {"$group": {
                "_id": None,
                "total_amount_outstanding": {"$sum": "$current_remaining"},
                "total_amount_collected": {"$sum": "$total_paid"}
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
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get installments summary: {str(e)}"
        )


async def format_installment_response(installment_doc: dict, db) -> InstallmentResponse:
    """Helper function to format installment document to response"""
    # Format payments
    payments = []
    for payment_data in installment_doc.get("payments", []):
        due_date = payment_data.get("due_date")
        if due_date and due_date.tzinfo is None:
            # If naive datetime, assume it's UTC
            due_date = due_date.replace(tzinfo=dt.timezone.utc)

        amount_due = payment_data.get("amount_due", 0)
        amount_paid = payment_data.get("amount_paid", 0)
        status = payment_data.get("status", PaymentStatus.PENDING)

        payment = InstallmentPaymentResponse(
            payment_number=payment_data.get("payment_number"),
            due_date=due_date,
            amount_due=amount_due,
            amount_paid=amount_paid,
            payment_date=payment_data.get("payment_date"),
            status=status,
            remaining_amount=amount_due - amount_paid,
            is_overdue=due_date < kampala_to_utc(now_kampala()) and status != PaymentStatus.PAID if due_date else False,
            notes=payment_data.get("notes")
        )
        payments.append(payment)
    
    total_amount = installment_doc.get("total_amount", 0)
    # Calculate totals
    total_paid = installment_doc.get("down_payment", 0) + sum(p.amount_paid for p in payments)
    total_remaining = max(0, total_amount - total_paid)
    completion_percentage = (total_paid / total_amount) * 100 if total_amount > 0 else 0
    
    # Find next payment due
    next_payment_due = None
    for payment in payments:
        if payment.status in [PaymentStatus.PENDING, PaymentStatus.PARTIAL, PaymentStatus.OVERDUE]:
            next_payment_due = payment
            break
    
    # Find overdue payments
    overdue_payments = [p for p in payments if p.is_overdue]
    
    return InstallmentResponse(
        id=str(installment_doc["_id"]),
        installment_number=installment_doc.get("installment_number", ""),
        order_number=installment_doc.get("order_number"),
        customer_id=str(installment_doc["customer_id"]) if installment_doc.get("customer_id") else None,
        customer_name=installment_doc.get("customer_name", "N/A"),
        customer_phone=installment_doc.get("customer_phone"),
        customer_email=installment_doc.get("customer_email"),
        order_id=str(installment_doc["order_id"]) if installment_doc.get("order_id") else None,
        items=installment_doc.get("items", []),
        total_amount=total_amount,
        down_payment=installment_doc.get("down_payment", 0),
        remaining_amount=installment_doc.get("remaining_amount", 0),
        number_of_payments=installment_doc.get("number_of_payments", 0),
        payment_frequency=installment_doc.get("payment_frequency", "monthly"),
        payments=payments,
        status=installment_doc.get("status", InstallmentStatus.ACTIVE),
        created_by=str(installment_doc.get("created_by")) if installment_doc.get("created_by") else None,
        approved_by=str(installment_doc.get("approved_by")) if installment_doc.get("approved_by") else None,
        created_at=installment_doc.get("created_at", kampala_to_utc(now_kampala())),
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
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get a specific installment by ID (Admin/Manager only)"""
    try:
        # Check if user has admin or manager role
        if current_user.role not in ['admin', 'inventory_manager']:
            raise HTTPException(
                status_code=fastapi_status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. Admin or Manager role required."
            )

        db = await get_database()

        if not ObjectId.is_valid(installment_id):
            raise HTTPException(
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
                detail="Invalid installment ID"
            )

        installment = await db.installments.find_one({"_id": ObjectId(installment_id)})

        if not installment:
            raise HTTPException(
                status_code=fastapi_status.HTTP_404_NOT_FOUND,
                detail="Installment not found"
            )

        return await format_installment_response(installment, db)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
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
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
                detail="Invalid installment ID"
            )

        # Check if installment exists
        existing_installment = await db.installments.find_one({"_id": ObjectId(installment_id)})
        if not existing_installment:
            raise HTTPException(
                status_code=fastapi_status.HTTP_404_NOT_FOUND,
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
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update installment: {str(e)}"
        )


@router.post("/{installment_id}/payments", response_model=InstallmentPaymentRecordResponse)
async def record_payment(
    installment_id: str,
    payment_data: InstallmentPaymentRecordCreate,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Record a payment for an installment (Admin/Manager only)"""
    try:
        # Check if user has admin or manager role
        if current_user.role not in ['admin', 'inventory_manager']:
            raise HTTPException(
                status_code=fastapi_status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin or Manager role required."
            )

        db = await get_database()

        if not ObjectId.is_valid(installment_id):
            raise HTTPException(
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
                detail="Invalid installment ID"
            )

        # Get installment
        installment = await db.installments.find_one({"_id": ObjectId(installment_id)})
        if not installment:
            raise HTTPException(
                status_code=fastapi_status.HTTP_404_NOT_FOUND,
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
                status_code=fastapi_status.HTTP_404_NOT_FOUND,
                detail=f"Payment number {payment_data.payment_number} not found"
            )

        # Handle payment allocation with overpayment logic
        remaining_payment_amount = payment_data.amount
        payments_to_update = []

        # Work with a copy of the payments to avoid reference issues
        payments_list = installment["payments"].copy()

        # Start with the current payment
        current_payment_index = payment_index

        while remaining_payment_amount > 0 and current_payment_index < len(payments_list):
            current_payment = payments_list[current_payment_index]

            # Calculate how much this payment still needs
            current_amount_paid = current_payment.get("amount_paid", 0)
            current_amount_due = current_payment["amount_due"]
            current_remaining = max(0, current_amount_due - current_amount_paid)

            if current_remaining > 0:
                # Apply payment to this installment
                amount_to_apply = min(remaining_payment_amount, current_remaining)
                new_amount_paid = current_amount_paid + amount_to_apply

                # Create updated payment object
                updated_payment = current_payment.copy()
                updated_payment["amount_paid"] = new_amount_paid
                updated_payment["payment_date"] = kampala_to_utc(now_kampala())

                # Update payment status
                if new_amount_paid >= current_amount_due:
                    updated_payment["status"] = PaymentStatus.PAID
                elif new_amount_paid > 0:
                    updated_payment["status"] = PaymentStatus.PARTIAL

                # Track this payment for database update
                payments_to_update.append({
                    "index": current_payment_index,
                    "payment": updated_payment,
                    "amount_applied": amount_to_apply
                })

                # Reduce remaining payment amount
                remaining_payment_amount -= amount_to_apply

            # Move to next payment
            current_payment_index += 1

        # Update all affected payments in the database
        update_operations = {}
        for payment_update in payments_to_update:
            update_operations[f"payments.{payment_update['index']}"] = payment_update["payment"]

        update_operations["updated_at"] = kampala_to_utc(now_kampala())

        # Update installment with all payment changes
        await db.installments.update_one(
            {"_id": ObjectId(installment_id)},
            {"$set": update_operations}
        )

        # Generate receipt number
        receipt_count = await db.installment_payments.count_documents({})
        receipt_number = f"INST-PAY-{receipt_count + 1:06d}"

        # Create detailed notes about payment allocation
        allocation_notes = []
        if len(payments_to_update) > 1:
            allocation_notes.append(f"Payment of UGX {payment_data.amount:,.0f} allocated across {len(payments_to_update)} installments:")
            for payment_update in payments_to_update:
                payment_num = payment_update["payment"]["payment_number"]
                amount_applied = payment_update["amount_applied"]
                allocation_notes.append(f"- Payment #{payment_num}: UGX {amount_applied:,.0f}")

        # Combine original notes with allocation details
        combined_notes = payment_data.notes or ""
        if allocation_notes:
            if combined_notes:
                combined_notes += "\n\n"
            combined_notes += "\n".join(allocation_notes)

        # Create payment record
        payment_record = {
            "installment_id": ObjectId(installment_id),
            "payment_number": payment_data.payment_number,
            "amount": payment_data.amount,
            "payment_method": payment_data.payment_method,
            "payment_date": kampala_to_utc(now_kampala()),
            "received_by": current_user.id,
            "receipt_number": receipt_number,
            "notes": combined_notes
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

            # Update corresponding order status to fully paid
            await db.orders.update_one(
                {"installment_id": ObjectId(installment_id)},
                {
                    "$set": {
                        "payment_status": OrderPaymentStatus.PAID,
                        "status": "completed",
                        "updated_at": kampala_to_utc(now_kampala())
                    }
                }
            )

            # Update customer total purchases with remaining amount
            if updated_installment.get("customer_id"):
                remaining_paid = sum(p.get("amount_paid", 0) for p in updated_installment.get("payments", []))
                await db.customers.update_one(
                    {"_id": updated_installment["customer_id"]},
                    {
                        "$inc": {
                            "total_purchases": remaining_paid
                        },
                        "$set": {
                            "last_purchase_date": kampala_to_utc(now_kampala()),
                            "updated_at": kampala_to_utc(now_kampala())
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
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record payment: {str(e)}"
        )


@router.post("/pos", response_model=InstallmentResponse)
async def create_installment_from_pos(
    installment_data: POSInstallmentCreate,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create installment from POS system (Admin/Manager only)"""
    try:
        # Check if user has admin or manager role
        if current_user.role not in ['admin', 'inventory_manager']:
            raise HTTPException(
                status_code=fastapi_status.HTTP_403_FORBIDDEN,
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
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
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
                "discount_amount": item.get("discount_amount", 0),
                "total_price": item.get("total", item.get("price", 0) * item.get("quantity", 1))
            })

        # Create installment document
        installment_doc = {
            "installment_number": installment_number,
            "customer_id": ObjectId(installment_data.customer_id) if installment_data.customer_id else None,
            "customer_name": installment_data.customer_name,
            "customer_phone": installment_data.customer_phone,
            "order_id": ObjectId(installment_data.order_id) if getattr(installment_data, 'order_id', None) else None,
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

        # Create corresponding order record
        order_count = await db.orders.count_documents({})
        order_number = f"ORD-{order_count + 1:06d}"

        # Prepare order items
        order_items = []
        for item in items:
            order_items.append({
                "product_id": item.get("product_id", ""),
                "product_name": item.get("product_name", ""),
                "quantity": item.get("quantity", 1),
                "unit_price": item.get("unit_price", 0),
                "total_price": item.get("total_price", 0),
                "discount_amount": item.get("discount_amount", 0)
            })

        # Create order document for installment
        order_doc = {
            "order_number": order_number,
            "client_id": ObjectId(installment_data.customer_id) if installment_data.customer_id else None,
            "client_name": installment_data.customer_name,
            "client_email": "",
            "client_phone": installment_data.customer_phone or "",
            "items": order_items,
            "subtotal": installment_data.total_amount,
            "tax": 0,
            "discount": sum(item.get("discount_amount", 0) for item in items),
            "total": installment_data.total_amount,
            "status": "active",  # Order is active since it's an installment
            "payment_method": "installment",
            "payment_status": OrderPaymentStatus.PARTIALLY_PAID,  # Down payment received, remaining in installments
            "notes": f"Installment order - Down payment: UGX {installment_data.down_payment:,.0f}, Remaining: UGX {remaining_amount:,.0f}",
            "installment_id": result.inserted_id,  # Link to installment plan
            "installment_number": installment_number,
            "created_by": current_user.id,
            "created_at": kampala_to_utc(now_kampala()),
            "updated_at": kampala_to_utc(now_kampala())
        }

        # Insert order
        await db.orders.insert_one(order_doc)

        # Update installment with order reference
        await db.installments.update_one(
            {"_id": result.inserted_id},
            {"$set": {"order_number": order_number}}
        )

        # Update customer statistics if customer is provided
        if installment_data.customer_id:
            await db.customers.update_one(
                {"_id": ObjectId(installment_data.customer_id)},
                {
                    "$inc": {
                        "total_purchases": installment_data.down_payment,  # Only count down payment for now
                        "total_orders": 1
                    },
                    "$set": {
                        "last_purchase_date": kampala_to_utc(now_kampala()),
                        "updated_at": kampala_to_utc(now_kampala())
                    }
                }
            )

        # Get created installment
        created_installment = await db.installments.find_one({"_id": result.inserted_id})

        # Convert to response format
        return await format_installment_response(created_installment, db)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create installment from POS: {str(e)}"
        )


@router.get("/{installment_id}/receipt")
async def get_installment_receipt(
    installment_id: str,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get installment receipt data for printing"""
    try:
        # Check if user has admin or manager role
        if current_user.role not in ['admin', 'inventory_manager']:
            raise HTTPException(
                status_code=fastapi_status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. Admin or Manager role required."
            )

        db = await get_database()

        if not ObjectId.is_valid(installment_id):
            raise HTTPException(
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
                detail="Invalid installment ID"
            )

        # Get installment
        installment = await db.installments.find_one({"_id": ObjectId(installment_id)})
        if not installment:
            raise HTTPException(
                status_code=fastapi_status.HTTP_404_NOT_FOUND,
                detail="Installment not found"
            )

        # Get user who created the installment
        created_by_name = "System"
        if installment.get("created_by"):
            try:
                user = await db.users.find_one({"_id": installment["created_by"]})
                if user:
                    created_by_name = user.get("full_name", "Staff Member")
            except:
                created_by_name = "Staff Member"

        # Calculate totals and discounts
        items_subtotal = 0
        total_item_discounts = 0
        
        for item in installment.get("items", []):
            unit_price = item.get("unit_price", item.get("price", 0))
            quantity = item.get("quantity", 1)
            item_discount = item.get("discount_amount", 0)
            
            items_subtotal += unit_price * quantity
            total_item_discounts += item_discount

        # Calculate payment schedule summary
        next_payment = None
        total_paid = installment.get("down_payment", 0)
        
        for payment in installment.get("payments", []):
            total_paid += payment.get("amount_paid", 0)
            if not next_payment and payment.get("status") in ["pending", "partial"]:
                next_payment = {
                    "payment_number": payment.get("payment_number"),
                    "due_date": payment.get("due_date"),
                    "amount_due": payment.get("amount_due", 0)
                }

        # Prepare receipt data
        receipt_data = {
            "installment_number": installment.get("installment_number", ""),
            "order_number": installment.get("order_number", ""),
            "customer_name": installment.get("customer_name", "Walk-in Client"),
            "customer_phone": installment.get("customer_phone", ""),
            "items": installment.get("items", []),
            "subtotal": items_subtotal,
            "total_discounts": total_item_discounts,
            "total_amount": installment.get("total_amount", 0),
            "down_payment": installment.get("down_payment", 0),
            "remaining_amount": installment.get("remaining_amount", 0),
            "number_of_payments": installment.get("number_of_payments", 0),
            "payment_frequency": installment.get("payment_frequency", "monthly"),
            "per_payment_amount": installment.get("remaining_amount", 0) / max(installment.get("number_of_payments", 1), 1),
            "next_payment": next_payment,
            "total_paid": total_paid,
            "status": installment.get("status", ""),
            "created_at": installment.get("created_at"),
            "created_by_name": created_by_name,
            "notes": installment.get("notes", "")
        }

        return receipt_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate installment receipt: {str(e)}"
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
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
                detail="Invalid installment ID"
            )

        # Check if installment exists
        installment = await db.installments.find_one({"_id": ObjectId(installment_id)})
        if not installment:
            raise HTTPException(
                status_code=fastapi_status.HTTP_404_NOT_FOUND,
                detail="Installment not found"
            )

        # Check if installment can be cancelled
        if installment["status"] == InstallmentStatus.COMPLETED:
            raise HTTPException(
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
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
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel installment: {str(e)}"
        )


@router.get("/{installment_id}/discount-details")
async def get_installment_discount_details(
    installment_id: str,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get detailed discount information for an installment including POS sale data"""
    try:
        # Check if user has admin or manager role
        if current_user.role not in ['admin', 'inventory_manager']:
            raise HTTPException(
                status_code=fastapi_status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions. Admin or Manager role required."
            )

        db = await get_database()

        if not ObjectId.is_valid(installment_id):
            raise HTTPException(
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
                detail="Invalid installment ID"
            )

        # Get installment
        installment = await db.installments.find_one({"_id": ObjectId(installment_id)})
        if not installment:
            raise HTTPException(
                status_code=fastapi_status.HTTP_404_NOT_FOUND,
                detail="Installment not found"
            )

        discount_details = {
            "installment_id": installment_id,
            "installment_items": installment.get("items", []),
            "pos_sale_data": None,
            "total_discounts": 0,
            "item_discounts": 0,
            "order_discount": 0
        }

        # Calculate discounts from installment items
        item_discounts = 0
        items_subtotal = 0

        for item in installment.get("items", []):
            item_discount = item.get("discount_amount", 0)
            item_discounts += item_discount

            # Calculate item subtotal
            unit_price = item.get("unit_price", item.get("price", 0))
            quantity = item.get("quantity", 1)
            items_subtotal += unit_price * quantity

        # If no explicit item discounts but there's a difference between subtotal and total, 
        # treat it as an implied discount
        if item_discounts == 0 and items_subtotal > installment.get("total_amount", 0):
            implied_discount = items_subtotal - installment.get("total_amount", 0)
            item_discounts = implied_discount

            # Update items with proportional discounts
            updated_items = []
            for item in installment.get("items", []):
                updated_item = item.copy()
                if items_subtotal > 0:
                    unit_price = item.get("unit_price", item.get("price", 0))
                    quantity = item.get("quantity", 1)
                    item_subtotal = unit_price * quantity
                    proportional_discount = (item_subtotal / items_subtotal) * implied_discount
                    updated_item["discount_amount"] = proportional_discount
                updated_items.append(updated_item)
            discount_details["installment_items"] = updated_items

        discount_details["item_discounts"] = item_discounts

        # If installment is linked to a POS order, get the original sale data
        if installment.get("order_id"):
            try:
                # Try to find the original POS sale/order
                pos_sale = await db.sales.find_one({"_id": ObjectId(installment["order_id"])})
                if pos_sale:
                    discount_details["pos_sale_data"] = {
                        "sale_number": pos_sale.get("sale_number"),
                        "subtotal": pos_sale.get("subtotal", 0),
                        "discount_amount": pos_sale.get("discount_amount", 0),
                        "total_amount": pos_sale.get("total_amount", 0),
                        "items": pos_sale.get("items", [])
                    }

                    # Calculate POS-level discounts
                    pos_item_discounts = sum(item.get("discount_amount", 0) for item in pos_sale.get("items", []))
                    pos_order_discount = pos_sale.get("discount_amount", 0) - pos_item_discounts

                    discount_details["order_discount"] = max(0, pos_order_discount)

                    # Use POS item discounts if installment doesn't have them
                    if item_discounts == 0 and pos_item_discounts > 0:
                        discount_details["item_discounts"] = pos_item_discounts

                        # Update installment items with POS discount information
                        updated_items = []
                        for i, installment_item in enumerate(installment.get("items", [])):
                            updated_item = installment_item.copy()
                            if i < len(pos_sale.get("items", [])):
                                pos_item = pos_sale["items"][i]
                                updated_item["discount_amount"] = pos_item.get("discount_amount", 0)
                            updated_items.append(updated_item)
                        discount_details["installment_items"] = updated_items

            except Exception as e:
                print(f"Error fetching POS sale data: {e}")
                # Continue without POS data if there's an error

        discount_details["total_discounts"] = discount_details["item_discounts"] + discount_details["order_discount"]

        return discount_details

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get discount details: {str(e)}"
        )