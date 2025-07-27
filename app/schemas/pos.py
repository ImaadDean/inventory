from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from ..models import PaymentMethod, SaleStatus


class SaleItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0)
    discount_amount: float = Field(default=0.0, ge=0)

    class Config:
        schema_extra = {
            "example": {
                "product_id": "507f1f77bcf86cd799439011",
                "quantity": 2,
                "discount_amount": 10.0
            }
        }


class SaleItemResponse(BaseModel):
    product_id: str
    product_name: str
    sku: str
    quantity: int
    unit_price: float
    total_price: float
    discount_amount: float

    class Config:
        schema_extra = {
            "example": {
                "product_id": "507f1f77bcf86cd799439011",
                "product_name": "iPhone 15 Pro",
                "sku": "IPH15PRO001",
                "quantity": 2,
                "unit_price": 999.99,
                "total_price": 1999.98,
                "discount_amount": 100.0
            }
        }


class SaleCreate(BaseModel):
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    items: List[SaleItemCreate] = Field(..., min_items=1)
    tax_rate: float = Field(default=0.0, ge=0, le=1)  # Tax rate as decimal (0.08 for 8%)
    discount_amount: float = Field(default=0.0, ge=0)
    payment_method: PaymentMethod
    payment_received: float = Field(..., ge=0)
    notes: Optional[str] = Field(None, max_length=500)

    class Config:
        schema_extra = {
            "example": {
                "customer_name": "John Doe",
                "items": [
                    {
                        "product_id": "507f1f77bcf86cd799439011",
                        "quantity": 1,
                        "discount_amount": 0
                    }
                ],
                "tax_rate": 0.08,
                "discount_amount": 185000,
                "payment_method": "card",
                "payment_received": 3700000,
                "notes": "Customer paid with credit card"
            }
        }


class SaleResponse(BaseModel):
    id: str
    sale_number: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    cashier_id: str
    cashier_name: str
    items: List[SaleItemResponse]
    subtotal: float
    tax_amount: float
    discount_amount: float
    total_amount: float
    payment_method: PaymentMethod
    payment_received: float
    change_given: float
    status: SaleStatus
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439012",
                "sale_number": "SALE-2024-001",
                "customer_name": "John Doe",
                "cashier_name": "Jane Smith",
                "items": [
                    {
                        "product_name": "iPhone 15 Pro",
                        "sku": "IPH15PRO001",
                        "quantity": 1,
                        "unit_price": 3700000,
                        "total_price": 3700000,
                        "discount_amount": 0
                    }
                ],
                "subtotal": 3700000,
                "tax_amount": 296000,
                "discount_amount": 185000,
                "total_amount": 3811000,
                "payment_method": "card",
                "payment_received": 3811000,
                "change_given": 0,
                "status": "completed",
                "created_at": "2024-01-20T14:30:00Z"
            }
        }


class SaleList(BaseModel):
    sales: List[SaleResponse]
    total: int
    page: int
    size: int

    class Config:
        schema_extra = {
            "example": {
                "sales": [
                    {
                        "id": "507f1f77bcf86cd799439012",
                        "sale_number": "SALE-2024-001",
                        "customer_name": "John Doe",
                        "total_amount": 1029.99,
                        "status": "completed",
                        "created_at": "2024-01-20T14:30:00Z"
                    }
                ],
                "total": 1,
                "page": 1,
                "size": 10
            }
        }


class ProductSearch(BaseModel):
    id: str
    name: str
    sku: str
    barcode: Optional[str] = None
    price: float
    stock_quantity: int
    unit: str

    class Config:
        schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "iPhone 15 Pro",
                "sku": "IPH15PRO001",
                "barcode": "1234567890123",
                "price": 999.99,
                "stock_quantity": 50,
                "unit": "pcs"
            }
        }