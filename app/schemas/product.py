from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# Category Schemas
class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Electronics",
                "description": "Electronic devices and accessories"
            }
        }


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Consumer Electronics",
                "description": "Updated description for electronics category"
            }
        }


class CategoryResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "Electronics",
                "description": "Electronic devices and accessories",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": None
            }
        }


# Product Schemas
class ProductCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    sku: str = Field(..., min_length=3, max_length=50)
    barcode: Optional[str] = Field(None, max_length=50)
    category_id: Optional[str] = None
    price: float = Field(..., gt=0)
    cost_price: Optional[float] = Field(None, ge=0)
    stock_quantity: int = Field(..., ge=0)
    min_stock_level: int = Field(default=10, ge=0)
    max_stock_level: Optional[int] = Field(None, ge=0)
    unit: str = Field(default="pcs", max_length=20)
    supplier: Optional[str] = Field(None, max_length=200)

    class Config:
        json_schema_extra = {
            "example": {
                "name": "iPhone 15 Pro",
                "description": "Latest iPhone model with advanced features",
                "sku": "IPH15PRO001",
                "barcode": "1234567890123",
                "price": 999.99,
                "cost_price": 750.00,
                "stock_quantity": 50,
                "min_stock_level": 10,
                "unit": "pcs",
                "supplier": "Apple Inc."
            }
        }


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    barcode: Optional[str] = Field(None, max_length=50)
    category_id: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    cost_price: Optional[float] = Field(None, ge=0)
    stock_quantity: Optional[int] = Field(None, ge=0)
    min_stock_level: Optional[int] = Field(None, ge=0)
    max_stock_level: Optional[int] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=20)
    supplier: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None

    class Config:
        json_schema_extra = {
            "example": {
                "price": 899.99,
                "stock_quantity": 75,
                "min_stock_level": 15,
                "supplier": "Apple Inc. - Updated"
            }
        }


class ProductResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    sku: str
    barcode: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    price: float
    cost_price: Optional[float] = None
    stock_quantity: int
    min_stock_level: int
    max_stock_level: Optional[int] = None
    unit: str
    supplier: Optional[str] = None
    is_active: bool
    is_low_stock: bool
    profit_margin: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "iPhone 15 Pro",
                "description": "Latest iPhone model with advanced features",
                "sku": "IPH15PRO001",
                "barcode": "1234567890123",
                "category_name": "Electronics",
                "price": 999.99,
                "cost_price": 750.00,
                "stock_quantity": 50,
                "min_stock_level": 10,
                "unit": "pcs",
                "supplier": "Apple Inc.",
                "is_active": True,
                "is_low_stock": False,
                "profit_margin": 33.33,
                "created_at": "2024-01-15T10:30:00Z"
            }
        }


class ProductList(BaseModel):
    products: List[ProductResponse]
    total: int
    page: int
    size: int

    class Config:
        json_schema_extra = {
            "example": {
                "products": [
                    {
                        "id": "507f1f77bcf86cd799439011",
                        "name": "iPhone 15 Pro",
                        "sku": "IPH15PRO001",
                        "price": 999.99,
                        "stock_quantity": 50,
                        "is_low_stock": False
                    }
                ],
                "total": 1,
                "page": 1,
                "size": 10
            }
        }


class StockUpdate(BaseModel):
    quantity: int = Field(..., description="Quantity to add (positive) or remove (negative)")
    reason: Optional[str] = Field(None, max_length=200, description="Reason for stock adjustment")

    class Config:
        json_schema_extra = {
            "example": {
                "quantity": 25,
                "reason": "New stock received from supplier"
            }
        }