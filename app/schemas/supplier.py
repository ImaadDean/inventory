from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime

class SupplierBase(BaseModel):
    """Base supplier schema"""
    name: str = Field(..., min_length=1, max_length=200, description="Company name")
    contact_person: Optional[str] = Field(None, max_length=100, description="Contact person name")
    phone: Optional[str] = Field(None, max_length=20, description="Phone number")
    email: Optional[str] = Field(None, max_length=100, description="Email address")
    address: Optional[str] = Field(None, max_length=500, description="Full address")
    notes: Optional[str] = Field(None, max_length=1000, description="Additional notes")
    is_active: bool = Field(default=True, description="Whether supplier is active")

class SupplierCreate(SupplierBase):
    """Schema for creating a supplier"""
    pass

class SupplierUpdate(BaseModel):
    """Schema for updating a supplier"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    contact_person: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None

class SupplierResponse(SupplierBase):
    """Schema for supplier response"""
    id: str = Field(..., description="Supplier ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    created_by: Optional[str] = Field(None, description="Created by user")
    updated_by: Optional[str] = Field(None, description="Last updated by user")
    
    class Config:
        from_attributes = True

class SupplierPayment(BaseModel):
    """Schema for making a payment to a supplier"""
    amount: float = Field(..., gt=0, description="Payment amount")
    payment_method: str = Field(..., description="Payment method")
