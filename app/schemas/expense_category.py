from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ExpenseCategoryBase(BaseModel):
    """Base expense category schema"""
    name: str = Field(..., min_length=1, max_length=100, description="Category name")
    icon: str = Field(default="📝", max_length=10, description="Category icon (emoji)")

class ExpenseCategoryCreate(ExpenseCategoryBase):
    """Schema for creating an expense category"""
    pass

class ExpenseCategoryUpdate(BaseModel):
    """Schema for updating an expense category"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    icon: Optional[str] = Field(None, max_length=10)
    is_active: Optional[bool] = None

class ExpenseCategoryResponse(ExpenseCategoryBase):
    """Schema for expense category response"""
    id: str = Field(..., description="Category ID")
    is_default: bool = Field(..., description="Whether this is a default category")
    is_active: bool = Field(..., description="Whether this category is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    created_by: Optional[str] = Field(None, description="Created by user")
    updated_by: Optional[str] = Field(None, description="Last updated by user")
    
    class Config:
        from_attributes = True
