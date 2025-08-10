from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from ..models.user import PyObjectId


class CategoryBase(BaseModel):
    """Base category schema"""
    name: str = Field(..., min_length=1, max_length=100, description="Category name")
    description: Optional[str] = Field(None, max_length=500, description="Category description")
    is_active: bool = Field(default=True, description="Whether the category is active")


class CategoryCreate(CategoryBase):
    """Schema for creating a new category"""
    pass


class CategoryUpdate(BaseModel):
    """Schema for updating a category"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class CategoryResponse(CategoryBase):
    """Schema for category response"""
    id: PyObjectId = Field(alias="_id")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "Electronics",
                "description": "Electronic devices and accessories",
                "is_active": True,
                "created_at": "2024-01-20T10:00:00Z",
                "updated_at": "2024-01-20T10:00:00Z"
            }
        }


class CategoryStats(BaseModel):
    """Schema for category statistics"""
    total_categories: int = Field(description="Total number of categories")
    active_categories: int = Field(description="Number of active categories")
    inactive_categories: int = Field(description="Number of inactive categories")
    categories_with_products: int = Field(description="Number of categories that have products")
