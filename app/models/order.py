from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from bson import ObjectId
from .user import PyObjectId
from ..utils.timezone import now_kampala, kampala_to_utc


class OrderStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class OrderPaymentStatus(str, Enum):
    PENDING = "pending"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    REFUNDED = "refunded"


class OrderItem(BaseModel):
    """Individual item within an order"""
    product_id: str
    product_name: str
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    total_price: float = Field(..., ge=0)
    discount_amount: float = Field(default=0.0, ge=0)


class Order(BaseModel):
    """Order model for tracking sales and installment orders"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    order_number: str = Field(..., min_length=5, max_length=50)  # Unique order identifier
    
    # Customer information
    client_id: Optional[PyObjectId] = None
    client_name: str = Field(..., min_length=1, max_length=100)
    client_email: Optional[str] = Field(None, max_length=100)
    client_phone: Optional[str] = Field(None, max_length=20)
    
    # Order items
    items: List[OrderItem] = Field(..., min_items=1)
    
    # Financial details
    subtotal: float = Field(..., ge=0)
    tax: float = Field(default=0.0, ge=0)
    discount: float = Field(default=0.0, ge=0)
    total: float = Field(..., gt=0)
    
    # Status and payment
    status: OrderStatus = OrderStatus.PENDING
    payment_method: str = Field(..., max_length=50)
    payment_status: OrderPaymentStatus = OrderPaymentStatus.PENDING
    
    # Installment information (if applicable)
    installment_id: Optional[PyObjectId] = None
    installment_number: Optional[str] = Field(None, max_length=50)

    # Sale information (if created from POS sale)
    sale_id: Optional[PyObjectId] = None
    
    # Additional information
    notes: Optional[str] = Field(None, max_length=1000)
    
    # Tracking
    created_by: PyObjectId
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: Optional[datetime] = None
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "order_number": "ORD-000001",
                "client_name": "John Doe",
                "client_phone": "+256700000000",
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
                "tax": 0,
                "discount": 5000,
                "total": 95000,
                "status": "active",
                "payment_method": "installment",
                "payment_status": "partially_paid",
                "notes": "Installment order with down payment"
            }
        }
