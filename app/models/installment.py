from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
from enum import Enum
from .user import PyObjectId
from ..utils.timezone import now_kampala, kampala_to_utc


class InstallmentStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    PARTIAL = "partial"


class InstallmentPayment(BaseModel):
    """Individual payment within an installment plan"""
    payment_number: int = Field(..., ge=1)
    due_date: datetime
    amount_due: float = Field(..., gt=0)
    amount_paid: float = Field(default=0.0, ge=0)
    payment_date: Optional[datetime] = None
    status: PaymentStatus = PaymentStatus.PENDING
    notes: Optional[str] = Field(None, max_length=500)
    
    @property
    def is_overdue(self) -> bool:
        """Check if payment is overdue"""
        if self.status == PaymentStatus.PAID:
            return False
        return kampala_to_utc(now_kampala()) > self.due_date
    
    @property
    def remaining_amount(self) -> float:
        """Calculate remaining amount to be paid"""
        return max(0, self.amount_due - self.amount_paid)


class Installment(BaseModel):
    """Main installment plan model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    installment_number: str = Field(..., min_length=5, max_length=50)  # Unique identifier
    
    # Customer information
    customer_id: Optional[PyObjectId] = None
    customer_name: str = Field(..., min_length=2, max_length=100)
    customer_phone: Optional[str] = Field(None, max_length=20)
    customer_email: Optional[str] = Field(None, max_length=100)
    
    # Product/Order information
    order_id: Optional[PyObjectId] = None  # Link to original order if created from POS
    items: List[dict] = Field(..., min_items=1)  # Products in the installment
    
    # Financial details
    total_amount: float = Field(..., gt=0)
    down_payment: float = Field(default=0.0, ge=0)
    remaining_amount: float = Field(..., gt=0)
    
    # Installment plan details
    number_of_payments: int = Field(..., ge=1, le=24)  # Max 24 payments (2 years)
    payment_frequency: str = Field(default="monthly")  # weekly, monthly, bi-weekly
    
    # Payment schedule
    payments: List[InstallmentPayment] = Field(..., min_items=1)
    
    # Status and tracking
    status: InstallmentStatus = InstallmentStatus.ACTIVE
    created_by: PyObjectId  # User who created the installment
    approved_by: Optional[PyObjectId] = None  # Manager/Admin who approved
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Additional information
    notes: Optional[str] = Field(None, max_length=1000)
    terms_and_conditions: Optional[str] = Field(None, max_length=2000)
    
    @property
    def total_paid(self) -> float:
        """Calculate total amount paid so far"""
        return self.down_payment + sum(payment.amount_paid for payment in self.payments)
    
    @property
    def total_remaining(self) -> float:
        """Calculate total remaining amount"""
        return max(0, self.total_amount - self.total_paid)
    
    @property
    def next_payment_due(self) -> Optional[InstallmentPayment]:
        """Get the next payment that's due"""
        for payment in self.payments:
            if payment.status in [PaymentStatus.PENDING, PaymentStatus.PARTIAL, PaymentStatus.OVERDUE]:
                return payment
        return None
    
    @property
    def overdue_payments(self) -> List[InstallmentPayment]:
        """Get all overdue payments"""
        return [payment for payment in self.payments if payment.is_overdue and payment.status != PaymentStatus.PAID]
    
    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage"""
        if self.total_amount == 0:
            return 0
        return (self.total_paid / self.total_amount) * 100
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "installment_number": "INST-2024-001",
                "customer_name": "John Doe",
                "customer_phone": "+256700000000",
                "items": [
                    {
                        "product_id": "507f1f77bcf86cd799439011",
                        "product_name": "Chanel No. 5",
                        "quantity": 1,
                        "unit_price": 150000,
                        "total_price": 150000
                    }
                ],
                "total_amount": 150000,
                "down_payment": 50000,
                "remaining_amount": 100000,
                "number_of_payments": 4,
                "payment_frequency": "monthly"
            }
        }


class InstallmentPaymentRecord(BaseModel):
    """Record of actual payments made"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    installment_id: PyObjectId
    payment_number: int
    amount: float = Field(..., gt=0)
    payment_method: str = Field(..., max_length=50)  # cash, card, mobile_money, etc.
    payment_date: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    received_by: PyObjectId  # User who received the payment
    receipt_number: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=500)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
