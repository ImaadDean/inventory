from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from bson import ObjectId
from .user import PyObjectId
from ..utils.timezone import now_kampala, kampala_to_utc


class PaymentMethod(str, Enum):
    CASH = "cash"
    CARD = "card"
    MOBILE_MONEY = "mobile_money"
    DIGITAL_WALLET = "digital_wallet"
    BANK_TRANSFER = "bank_transfer"
    NOT_PAID = "not_paid"


class SaleStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class SaleItem(BaseModel):
    product_id: PyObjectId
    product_name: str
    sku: str
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., gt=0)
    cost_price: float = Field(..., gt=0)
    total_price: float = Field(..., gt=0)
    discount_amount: float = Field(default=0.0, ge=0)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class Sale(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    sale_number: str = Field(..., min_length=5, max_length=50)  # Unique sale identifier
    customer_id: Optional[PyObjectId] = None
    customer_name: Optional[str] = None
    cashier_id: PyObjectId
    cashier_name: str
    items: List[SaleItem] = Field(..., min_items=1)
    subtotal: float = Field(..., gt=0)
    tax_amount: float = Field(default=0.0, ge=0)
    discount_amount: float = Field(default=0.0, ge=0)
    total_amount: float = Field(..., gt=0)
    payment_method: PaymentMethod
    payment_received: float = Field(..., ge=0)
    change_given: float = Field(default=0.0, ge=0)
    status: SaleStatus = SaleStatus.COMPLETED
    notes: Optional[str] = Field(None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: Optional[datetime] = None

    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.items)

    @property
    def profit(self) -> float:
        # This would need product cost data to calculate actual profit
        return self.total_amount - self.discount_amount

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "sale_number": "SALE-2024-001",
                "customer_name": "John Doe",
                "cashier_name": "Jane Smith",
                "items": [
                    {
                        "product_name": "iPhone 15",
                        "sku": "IPH15001",
                        "quantity": 1,
                        "unit_price": 999.99,
                        "total_price": 999.99
                    }
                ],
                "subtotal": 999.99,
                "tax_amount": 80.00,
                "total_amount": 1079.99,
                "payment_method": "card",
                "payment_received": 1079.99
            }
        }