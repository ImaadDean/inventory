from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from bson import ObjectId
from .user import PyObjectId
from ..utils.timezone import now_kampala, kampala_to_utc


class Category(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "name": "Electronics",
                "description": "Electronic devices and accessories"
            }
        }


class Product(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    sku: str = Field(..., min_length=3, max_length=50)  # Stock Keeping Unit
    barcode: Optional[str] = Field(None, max_length=50)
    category_id: Optional[PyObjectId] = None
    price: float = Field(..., gt=0)
    cost_price: Optional[float] = Field(None, ge=0)
    stock_quantity: int = Field(..., ge=0)
    min_stock_level: int = Field(default=10, ge=0)  # For restock alerts
    max_stock_level: Optional[int] = Field(None, ge=0)
    unit: str = Field(default="pcs", max_length=20)  # pieces, kg, liters, etc.
    supplier: Optional[str] = Field(None, max_length=200)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: Optional[datetime] = None

    @property
    def is_low_stock(self) -> bool:
        return self.stock_quantity <= self.min_stock_level

    @property
    def profit_margin(self) -> Optional[float]:
        if self.cost_price and self.cost_price > 0:
            return ((self.price - self.cost_price) / self.cost_price) * 100
        return None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
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