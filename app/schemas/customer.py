from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=1, max_length=20)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    date_of_birth: Optional[datetime] = None
    notes: Optional[str] = Field(None, max_length=1000)

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Jane Smith",
                "phone": "+1234567890",
                "address": "123 Main St",
                "city": "New York",
                "country": "USA",
                "notes": "VIP customer"
            }
        }


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    date_of_birth: Optional[datetime] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=1000)

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Jane Doe",
                "phone": "+1234567891",
                "is_active": True
            }
        }


class CustomerResponse(BaseModel):
    id: str
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    is_active: bool
    total_purchases: float
    total_orders: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_purchase_date: Optional[datetime] = None
    notes: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "Jane Smith",
                "phone": "+1234567890",
                "address": "123 Main St",
                "city": "New York",
                "country": "USA",
                "is_active": True,
                "total_purchases": 2500.50,
                "total_orders": 15,
                "created_at": "2024-01-15T10:30:00Z",
                "last_purchase_date": "2024-01-20T14:30:00Z"
            }
        }


class CustomerList(BaseModel):
    customers: List[CustomerResponse]
    total: int
    page: int
    size: int

    class Config:
        json_schema_extra = {
            "example": {
                "customers": [
                    {
                        "id": "507f1f77bcf86cd799439011",
                        "name": "Jane Smith",
                        "phone": "+1234567890",
                        "total_purchases": 2500.50,
                        "total_orders": 15,
                        "is_active": True
                    }
                ],
                "total": 1,
                "page": 1,
                "size": 10
            }
        }


class PurchaseHistory(BaseModel):
    sale_id: str
    sale_number: str
    total_amount: float
    items_count: int
    purchase_date: datetime

    class Config:
        schema_extra = {
            "example": {
                "sale_id": "507f1f77bcf86cd799439012",
                "sale_number": "SALE-2024-001",
                "total_amount": 199.99,
                "items_count": 3,
                "purchase_date": "2024-01-20T14:30:00Z"
            }
        }


class CustomerPurchaseHistory(BaseModel):
    customer: CustomerResponse
    purchases: List[PurchaseHistory]
    total_purchases_amount: float
    total_purchases_count: int

    class Config:
        json_schema_extra = {
            "example": {
                "customer": {
                    "id": "507f1f77bcf86cd799439011",
                    "name": "Jane Smith",
                    "phone": "+1234567890"
                },
                "purchases": [
                    {
                        "sale_id": "507f1f77bcf86cd799439012",
                        "sale_number": "SALE-2024-001",
                        "total_amount": 199.99,
                        "items_count": 3,
                        "purchase_date": "2024-01-20T14:30:00Z"
                    }
                ],
                "total_purchases_amount": 2500.50,
                "total_purchases_count": 15
            }
        }