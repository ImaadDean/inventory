from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId


class ProductSupplierPriceCreate(BaseModel):
    """Model for creating a new product supplier price record"""
    product_id: str = Field(..., description="Product ID")
    supplier_id: str = Field(..., description="Supplier ID")
    unit_cost: float = Field(..., gt=0, description="Cost per unit")
    quantity_restocked: int = Field(..., gt=0, description="Quantity restocked")
    total_cost: float = Field(..., gt=0, description="Total cost (unit_cost * quantity)")
    restock_date: datetime = Field(default_factory=datetime.utcnow, description="Restock date")
    expense_id: Optional[str] = Field(None, description="Related expense ID")
    notes: Optional[str] = Field(None, description="Optional notes")


class ProductSupplierPriceUpdate(BaseModel):
    """Model for updating a product supplier price record"""
    unit_cost: Optional[float] = Field(None, gt=0, description="Cost per unit")
    quantity_restocked: Optional[int] = Field(None, gt=0, description="Quantity restocked")
    total_cost: Optional[float] = Field(None, gt=0, description="Total cost")
    notes: Optional[str] = Field(None, description="Optional notes")


class ProductSupplierPriceResponse(BaseModel):
    """Model for product supplier price response"""
    id: str = Field(..., description="Price record ID")
    product_id: str = Field(..., description="Product ID")
    supplier_id: str = Field(..., description="Supplier ID")
    supplier_name: Optional[str] = Field(None, description="Supplier name (populated)")
    unit_cost: float = Field(..., description="Cost per unit")
    quantity_restocked: int = Field(..., description="Quantity restocked")
    total_cost: float = Field(..., description="Total cost")
    restock_date: datetime = Field(..., description="Restock date")
    expense_id: Optional[str] = Field(None, description="Related expense ID")
    notes: Optional[str] = Field(None, description="Optional notes")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            ObjectId: str
        }


class SupplierPricingSummary(BaseModel):
    """Model for supplier pricing summary in product modal"""
    supplier_id: str = Field(..., description="Supplier ID")
    supplier_name: str = Field(..., description="Supplier name")
    is_current: bool = Field(..., description="Is current supplier")
    latest_price: float = Field(..., description="Latest unit cost")
    latest_restock_date: datetime = Field(..., description="Latest restock date")
    average_price: Optional[float] = Field(None, description="Average price")
    total_restocks: int = Field(..., description="Total number of restocks")
    total_quantity: int = Field(..., description="Total quantity restocked")
    price_history: list[dict] = Field(default_factory=list, description="Recent price history")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ProductPricingHistory(BaseModel):
    """Model for product pricing history"""
    product_id: str = Field(..., description="Product ID")
    product_name: str = Field(..., description="Product name")
    current_supplier_id: Optional[str] = Field(None, description="Current supplier ID")
    current_cost_price: float = Field(..., description="Current cost price")
    suppliers: list[SupplierPricingSummary] = Field(..., description="Supplier pricing data")
    total_suppliers: int = Field(..., description="Total number of suppliers")
    price_range: dict = Field(..., description="Price range (min, max)")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
