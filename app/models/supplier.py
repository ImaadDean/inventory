from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from bson import ObjectId
from ..utils.timezone import now_kampala, kampala_to_utc

class Supplier(BaseModel):
    """Supplier model"""
    id: Optional[str] = Field(None, alias="_id")
    name: str = Field(..., min_length=1, max_length=200)
    contact_person: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = Field(None, max_length=1000)
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
