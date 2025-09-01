from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# Decant Schemas
class DecantCreate(BaseModel):
    """Schema for creating decant information"""
    is_decantable: bool = Field(default=False)
    decant_size_ml: Optional[float] = Field(None, gt=0)
    decant_price: Optional[float] = Field(None, gt=0)
    opened_bottle_ml_left: Optional[float] = Field(None, ge=0)

    class Config:
        json_schema_extra = {
            "example": {
                "is_decantable": True,
                "decant_size_ml": 10.0,
                "decant_price": 30000.0,
                "opened_bottle_ml_left": 0.0
            }
        }


class DecantUpdate(BaseModel):
    """Schema for updating decant information"""
    is_decantable: Optional[bool] = None
    decant_size_ml: Optional[float] = Field(None, gt=0)
    decant_price: Optional[float] = Field(None, gt=0)
    opened_bottle_ml_left: Optional[float] = Field(None, ge=0)


class DecantResponse(BaseModel):
    """Schema for decant response"""
    is_decantable: bool
    decant_size_ml: Optional[float] = None
    decant_price: Optional[float] = None
    opened_bottle_ml_left: Optional[float] = None


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
    barcode: Optional[str] = Field(None, max_length=50)
    category_id: Optional[str] = None
    price: float = Field(..., gt=0)
    cost_price: Optional[float] = Field(None, ge=0)
    stock_quantity: int = Field(..., ge=0)
    min_stock_level: int = Field(default=4, ge=0)
    unit: str = Field(default="pcs", max_length=20)
    supplier: Optional[str] = Field(None, max_length=200)
    brand: Optional[str] = Field(None, max_length=200)
    payment_method: Optional[str] = Field(None, max_length=50, description="Payment method for expense")

    # Image fields
    image_public_id: Optional[str] = Field(None, description="Cloudinary public ID for product image")
    image_url: Optional[str] = Field(None, description="URL of the product image")

    # Perfume-specific fields
    bottle_size_ml: Optional[float] = Field(None, gt=0, description="Size of each bottle in ml")
    decant: Optional[DecantCreate] = Field(None, description="Decant information for perfume products")
    scent_ids: Optional[List[str]] = Field(None, description="List of scent IDs associated with this product")
    
    # Watch settings fields
    material_id: Optional[str] = Field(None, description="Material ID for watch products")
    movement_type_id: Optional[str] = Field(None, description="Movement type ID for watch products")
    gender_id: Optional[str] = Field(None, description="Gender ID for watch products")
    color_id: Optional[str] = Field(None, description="Color ID for watch products")
    
    force: Optional[bool] = Field(False, description="Force create product even if name exists")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "iPhone 15 Pro",
                "description": "Latest iPhone model with advanced features",
                "barcode": "1234567890123",
                "price": 999.99,
                "cost_price": 750.00,
                "stock_quantity": 50,
                "min_stock_level": 4,
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
    unit: Optional[str] = Field(None, max_length=20)
    supplier: Optional[str] = Field(None, max_length=200)
    brand: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None

    # Image fields
    image_public_id: Optional[str] = Field(None, description="Cloudinary public ID for product image")
    image_url: Optional[str] = Field(None, description="URL of the product image")

    # Perfume-specific fields
    bottle_size_ml: Optional[float] = Field(None, gt=0)
    scent_ids: Optional[List[str]] = Field(None, description="List of scent IDs associated with this product")
    decant: Optional[DecantUpdate] = None

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
    barcode: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    price: float
    cost_price: Optional[float] = None
    stock_quantity: int
    min_stock_level: int
    unit: str
    supplier: Optional[str] = None
    brand: Optional[str] = None
    is_active: bool
    is_low_stock: bool
    profit_margin: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Perfume-specific fields
    bottle_size_ml: Optional[float] = None
    decant: Optional[DecantResponse] = None

    # Computed fields for perfume products
    is_perfume_with_decants: Optional[bool] = None
    total_ml_available: Optional[float] = None
    available_decants: Optional[int] = None
    stock_display: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "iPhone 15 Pro",
                "description": "Latest iPhone model with advanced features",
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
                        "barcode": "1234567890123",
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
    unit_cost: Optional[float] = Field(None, gt=0, description="Cost per unit for restocking (creates automatic expense)")
    supplier_name: Optional[str] = Field(None, max_length=200, description="Supplier name for expense tracking")
    payment_method: Optional[str] = Field(None, max_length=50, description="Payment method for expense")

    class Config:
        json_schema_extra = {
            "example": {
                "quantity": 25,
                "reason": "New stock received from supplier",
                "unit_cost": 15000.0,
                "supplier_name": "ABC Suppliers Ltd",
                "payment_method": "bank_transfer"
            }
        }