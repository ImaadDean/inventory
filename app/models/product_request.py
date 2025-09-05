from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum
from .user import PyObjectId
from ..utils.timezone import now_kampala, kampala_to_utc

class ProductRequestStatus(str, Enum):
    PENDING = "pending"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"

class ProductRequest(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    product_name: str = Field(..., min_length=2, max_length=200)
    customer_name: str = Field(..., min_length=2, max_length=100)
    customer_contact: Optional[str] = Field(None, max_length=100)
    quantity: int = Field(default=1, gt=0)
    status: ProductRequestStatus = ProductRequestStatus.PENDING
    notes: Optional[str] = Field(None, max_length=1000)
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {PyObjectId: str}
        json_schema_extra = {
            "example": {
                "product_name": "iPhone 15 Pro",
                "customer_name": "John Doe",
                "customer_contact": "+256700000000",
                "quantity": 1,
                "status": "pending",
                "notes": "Wants the black color"
            }
        }
