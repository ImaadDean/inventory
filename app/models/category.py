from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from .user import PyObjectId


class Category(BaseModel):
    """Category model for product categorization"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    parent_id: Optional[PyObjectId] = None  # For hierarchical categories
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "name": "Electronics",
                "description": "Electronic devices and accessories",
                "parent_id": None,
                "is_active": True
            }
        }
