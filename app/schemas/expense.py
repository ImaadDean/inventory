from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date

class ExpenseBase(BaseModel):
    """Base expense schema"""
    description: str = Field(..., min_length=1, max_length=500, description="Expense description")
    category: str = Field(..., min_length=1, max_length=50, description="Expense category")
    amount: float = Field(..., gt=0, description="Expense amount")
    expense_date: date = Field(..., description="Date of expense")
    payment_method: str = Field(..., min_length=1, max_length=50, description="Payment method")
    vendor: Optional[str] = Field(None, max_length=200, description="Vendor or supplier")
    notes: Optional[str] = Field(None, max_length=1000, description="Additional notes")
    status: str = Field(default="pending", description="Payment status")

class ExpenseCreate(ExpenseBase):
    """Schema for creating an expense"""
    pass

class ExpenseUpdate(BaseModel):
    """Schema for updating an expense"""
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[str] = Field(None, min_length=1, max_length=50)
    amount: Optional[float] = Field(None, gt=0)
    expense_date: Optional[date] = None
    payment_method: Optional[str] = Field(None, min_length=1, max_length=50)
    vendor: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=1000)
    status: Optional[str] = None

class ExpenseResponse(ExpenseBase):
    """Schema for expense response"""
    id: str = Field(..., description="Expense ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    created_by: Optional[str] = Field(None, description="Created by user")
    updated_by: Optional[str] = Field(None, description="Last updated by user")
    
    class Config:
        from_attributes = True
