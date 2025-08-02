from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date
from bson import ObjectId

class Expense(BaseModel):
    """Expense model"""
    id: Optional[str] = Field(None, alias="_id")
    description: str = Field(..., min_length=1, max_length=500)
    category: str = Field(..., min_length=1, max_length=50)
    amount: float = Field(..., gt=0)
    expense_date: date = Field(...)
    payment_method: str = Field(..., min_length=1, max_length=50)
    vendor: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=1000)
    status: str = Field(default="pending")  # pending, paid, overdue
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    class Config:
        populate_by_name = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat()
        }
