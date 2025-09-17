from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from bson import ObjectId
from .user import PyObjectId
from ..utils.timezone import now_kampala, kampala_to_utc


class PerOrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class PerOrderPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class PerOrderPaymentStatus(str, Enum):
    PENDING = "pending"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    REFUNDED = "refunded"
    FAILED = "failed"


class PerOrderItem(BaseModel):
    """Individual item within a per order"""
    product_id: str
    product_name: str
    product_sku: Optional[str] = None
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    total_price: float = Field(..., ge=0)
    discount_amount: float = Field(default=0.0, ge=0)
    tax_amount: float = Field(default=0.0, ge=0)
    notes: Optional[str] = Field(None, max_length=500)


class PerOrderShipping(BaseModel):
    """Shipping information for per order"""
    method: str = Field(..., max_length=100)  # e.g., "standard", "express", "pickup"
    cost: float = Field(default=0.0, ge=0)
    tracking_number: Optional[str] = Field(None, max_length=100)
    estimated_delivery: Optional[datetime] = None
    actual_delivery: Optional[datetime] = None
    carrier: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)


class PerOrderPayment(BaseModel):
    """Payment information for per order"""
    method: str = Field(..., max_length=50)  # e.g., "cash", "card", "mobile_money", "bank_transfer"
    reference: Optional[str] = Field(None, max_length=100)
    amount: float = Field(..., ge=0)
    currency: str = Field(default="UGX", max_length=3)
    status: PerOrderPaymentStatus = PerOrderPaymentStatus.PENDING
    processed_at: Optional[datetime] = None
    processor: Optional[str] = Field(None, max_length=100)  # Payment processor name
    transaction_fee: float = Field(default=0.0, ge=0)


class PerOrderStatusHistory(BaseModel):
    """Status change history for per order"""
    status: PerOrderStatus
    changed_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    changed_by: PyObjectId
    notes: Optional[str] = Field(None, max_length=500)
    reason: Optional[str] = Field(None, max_length=200)


class PerOrder(BaseModel):
    """Per Order model for detailed order management and tracking"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    order_number: str = Field(..., min_length=5, max_length=50)  # Unique order identifier
    
    # Reference to original order if this is based on an existing order
    original_order_id: Optional[PyObjectId] = None
    
    # Customer information
    customer_id: Optional[PyObjectId] = None
    customer_name: str = Field(..., min_length=1, max_length=100)
    customer_email: Optional[str] = Field(None, max_length=100)
    customer_phone: Optional[str] = Field(None, max_length=20)
    
    # Order items
    items: List[PerOrderItem] = Field(..., min_items=1)
    
    # Financial details
    subtotal: float = Field(..., ge=0)
    tax_total: float = Field(default=0.0, ge=0)
    discount_total: float = Field(default=0.0, ge=0)
    shipping_cost: float = Field(default=0.0, ge=0)
    total_amount: float = Field(..., gt=0)
    
    # Payment information
    payments: List[PerOrderPayment] = Field(default_factory=list)
    payment_status: PerOrderPaymentStatus = PerOrderPaymentStatus.PENDING
    
    # Order status and priority
    status: PerOrderStatus = PerOrderStatus.PENDING
    priority: PerOrderPriority = PerOrderPriority.NORMAL
    status_history: List[PerOrderStatusHistory] = Field(default_factory=list)
    
    # Shipping information
    shipping: Optional[PerOrderShipping] = None
    
    # Dates and timing
    order_date: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    expected_completion_date: Optional[datetime] = None
    actual_completion_date: Optional[datetime] = None
    
    # Staff assignments
    assigned_to: Optional[PyObjectId] = None  # Staff member assigned to handle this order
    created_by: PyObjectId
    last_updated_by: Optional[PyObjectId] = None
    
    # Additional information
    notes: Optional[str] = Field(None, max_length=2000)
    internal_notes: Optional[str] = Field(None, max_length=2000)  # Staff-only notes
    tags: List[str] = Field(default_factory=list)  # For categorization and filtering
    
    # Tracking
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: Optional[datetime] = None
    
    # Metadata
    source: str = Field(default="manual", max_length=50)  # e.g., "pos", "online", "phone", "manual"
    channel: Optional[str] = Field(None, max_length=50)  # Sales channel
    
    @property
    def total_paid(self) -> float:
        """Calculate total amount paid"""
        return sum(payment.amount for payment in self.payments if payment.status == PerOrderPaymentStatus.PAID)
    
    @property
    def balance_due(self) -> float:
        """Calculate remaining balance"""
        return max(0, self.total_amount - self.total_paid)
    
    @property
    def is_fully_paid(self) -> bool:
        """Check if order is fully paid"""
        return self.balance_due <= 0
    
    @property
    def total_items(self) -> int:
        """Get total number of items"""
        return len(self.items)
    
    @property
    def total_quantity(self) -> int:
        """Get total quantity of all items"""
        return sum(item.quantity for item in self.items)
    
    @property
    def current_status_info(self) -> Optional[PerOrderStatusHistory]:
        """Get the most recent status change"""
        if self.status_history:
            return max(self.status_history, key=lambda x: x.changed_at)
        return None
    
    def add_status_change(self, new_status: PerOrderStatus, changed_by: PyObjectId, 
                         notes: Optional[str] = None, reason: Optional[str] = None):
        """Add a new status change to history"""
        status_change = PerOrderStatusHistory(
            status=new_status,
            changed_by=changed_by,
            notes=notes,
            reason=reason
        )
        self.status_history.append(status_change)
        self.status = new_status
        self.updated_at = kampala_to_utc(now_kampala())
    
    def add_payment(self, payment: PerOrderPayment):
        """Add a payment and update payment status"""
        self.payments.append(payment)
        
        # Update payment status based on total paid
        total_paid = self.total_paid
        if total_paid >= self.total_amount:
            self.payment_status = PerOrderPaymentStatus.PAID
        elif total_paid > 0:
            self.payment_status = PerOrderPaymentStatus.PARTIALLY_PAID
        else:
            self.payment_status = PerOrderPaymentStatus.PENDING
        
        self.updated_at = kampala_to_utc(now_kampala())
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "order_number": "PO-000001",
                "customer_name": "John Doe",
                "customer_email": "john@example.com",
                "customer_phone": "+256700000000",
                "items": [
                    {
                        "product_id": "507f1f77bcf86cd799439011",
                        "product_name": "Sample Product",
                        "quantity": 2,
                        "unit_price": 50000,
                        "total_price": 100000,
                        "discount_amount": 5000
                    }
                ],
                "subtotal": 100000,
                "tax_total": 0,
                "discount_total": 5000,
                "shipping_cost": 10000,
                "total_amount": 105000,
                "status": "pending",
                "priority": "normal",
                "payment_status": "pending",
                "source": "manual",
                "notes": "Special handling required"
            }
        }


class PerOrderCreate(BaseModel):
    """Schema for creating a new per order"""
    order_number: str = Field(..., min_length=5, max_length=50)
    original_order_id: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: str = Field(..., min_length=1, max_length=100)
    customer_email: Optional[str] = Field(None, max_length=100)
    customer_phone: Optional[str] = Field(None, max_length=20)
    items: List[PerOrderItem] = Field(..., min_items=1)
    shipping_cost: float = Field(default=0.0, ge=0)
    priority: PerOrderPriority = PerOrderPriority.NORMAL
    expected_completion_date: Optional[datetime] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)
    tags: List[str] = Field(default_factory=list)
    source: str = Field(default="manual", max_length=50)
    channel: Optional[str] = Field(None, max_length=50)


class PerOrderUpdate(BaseModel):
    """Schema for updating a per order"""
    customer_name: Optional[str] = Field(None, min_length=1, max_length=100)
    customer_email: Optional[str] = Field(None, max_length=100)
    customer_phone: Optional[str] = Field(None, max_length=20)
    items: Optional[List[PerOrderItem]] = None
    shipping_cost: Optional[float] = Field(None, ge=0)
    priority: Optional[PerOrderPriority] = None
    status: Optional[PerOrderStatus] = None
    expected_completion_date: Optional[datetime] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)
    internal_notes: Optional[str] = Field(None, max_length=2000)
    tags: Optional[List[str]] = None
