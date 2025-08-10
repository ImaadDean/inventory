from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from bson import ObjectId
from .user import PyObjectId
from ..utils.timezone import now_kampala, kampala_to_utc


class Decant(BaseModel):
    """Model for perfume decant information"""
    is_decantable: bool = Field(default=False, description="Whether this product can be sold as decants")
    decant_size_ml: Optional[float] = Field(None, gt=0, description="Size of each decant in ml (e.g., 10ml)")
    decant_price: Optional[float] = Field(None, gt=0, description="Price per decant")
    opened_bottle_ml_left: Optional[float] = Field(None, ge=0, description="Remaining ml in currently opened bottle")

    class Config:
        json_schema_extra = {
            "example": {
                "is_decantable": True,
                "decant_size_ml": 10.0,
                "decant_price": 30000.0,
                "opened_bottle_ml_left": 90.0
            }
        }


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
    barcode: Optional[str] = Field(None, max_length=50)
    category_id: Optional[PyObjectId] = None
    price: float = Field(..., gt=0)
    cost_price: Optional[float] = Field(None, ge=0)
    stock_quantity: int = Field(..., ge=0)
    min_stock_level: int = Field(default=4, ge=0)  # For restock alerts
    unit: str = Field(default="pcs", max_length=20)  # pieces, kg, liters, etc.
    supplier: Optional[str] = Field(None, max_length=200)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: Optional[datetime] = None

    # Perfume-specific fields
    bottle_size_ml: Optional[float] = Field(None, gt=0, description="Size of each bottle in ml (e.g., 100ml)")
    decant: Optional[Decant] = Field(None, description="Decant information for perfume products")

    @property
    def is_low_stock(self) -> bool:
        return self.stock_quantity <= self.min_stock_level

    @property
    def profit_margin(self) -> Optional[float]:
        if self.cost_price and self.cost_price > 0:
            return ((self.price - self.cost_price) / self.cost_price) * 100
        return None

    @property
    def is_perfume_with_decants(self) -> bool:
        """Check if this is a perfume product with decant capability"""
        return self.decant is not None and self.decant.is_decantable

    @property
    def total_ml_available(self) -> Optional[float]:
        """Calculate total ml available (unopened bottles + opened bottle)"""
        if not self.bottle_size_ml:
            return None

        unopened_ml = self.stock_quantity * self.bottle_size_ml
        opened_ml = self.decant.opened_bottle_ml_left if (self.decant and self.decant.opened_bottle_ml_left) else 0
        return unopened_ml + opened_ml

    @property
    def available_decants(self) -> Optional[int]:
        """Calculate how many decants can be made from available ml"""
        if not self.is_perfume_with_decants or not self.decant.decant_size_ml:
            return None

        total_ml = self.total_ml_available
        if total_ml is None:
            return None

        return int(total_ml // self.decant.decant_size_ml)

    @property
    def stock_display(self) -> str:
        """Display stock in appropriate format for perfume vs regular products"""
        if self.is_perfume_with_decants:
            opened_ml = self.decant.opened_bottle_ml_left if self.decant.opened_bottle_ml_left else 0
            return f"{self.stock_quantity} pcs & {opened_ml}mls"
        return f"{self.stock_quantity} {self.unit}"

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "examples": [
                {
                    "name": "iPhone 15 Pro",
                    "description": "Latest iPhone model with advanced features",
                    "barcode": "1234567890123",
                    "price": 999.99,
                    "cost_price": 750.00,
                    "stock_quantity": 50,
                    "min_stock_level": 4,
                    "unit": "pcs",
                    "supplier": "Apple Inc."
                },
                {
                    "name": "Chanel No. 5",
                    "description": "Classic luxury perfume",
                    "barcode": "3145891355000",
                    "price": 250000.0,
                    "cost_price": 180000.0,
                    "stock_quantity": 5,
                    "min_stock_level": 2,
                    "unit": "pcs",
                    "supplier": "Chanel",
                    "bottle_size_ml": 100.0,
                    "decant": {
                        "is_decantable": True,
                        "decant_size_ml": 10.0,
                        "decant_price": 30000.0,
                        "opened_bottle_ml_left": 90.0
                    }
                }
            ]
        }