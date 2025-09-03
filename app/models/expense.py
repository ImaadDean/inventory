from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from bson import ObjectId
from ..utils.timezone import now_kampala, kampala_to_utc

class RestockedProduct(BaseModel):
    product_id: str = Field(...)
    name: str = Field(...)
    quantity: int = Field(..., gt=0)
    cost_price: float = Field(..., gt=0)

class Expense(BaseModel):
    """Expense model"""
    id: Optional[str] = Field(None, alias="_id")
    description: str = Field(..., min_length=1, max_length=500)
    category: str = Field(..., min_length=1, max_length=50)
    amount: float = Field(..., gt=0)
    amount_paid: float = Field(default=0, description="Amount paid so far")
    expense_date: date = Field(...)
    payment_method: str = Field(default="pending payment", min_length=1, max_length=50)
    vendor: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=1000)
    status: str = Field(default="not_paid")  # paid, not_paid, partially_paid
    products: Optional[List[RestockedProduct]] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    class Config:
        populate_by_name = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat()
        }