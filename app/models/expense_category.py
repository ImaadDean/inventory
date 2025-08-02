from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from bson import ObjectId
from ..utils.timezone import now_kampala, kampala_to_utc

class ExpenseCategory(BaseModel):
    """Expense Category model"""
    id: Optional[str] = Field(None, alias="_id")
    name: str = Field(..., min_length=1, max_length=100)
    icon: str = Field(default="📝", max_length=10)
    is_default: bool = Field(default=False)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    class Config:
        populate_by_name = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }
