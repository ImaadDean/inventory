from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from ..models.product_request import ProductRequestStatus

class ProductRequestCreate(BaseModel):
    product_name: str
    customer_name: Optional[str] = None
    customer_contact: Optional[str] = None
    notes: Optional[str] = None

class ProductRequestUpdate(BaseModel):
    product_name: Optional[str] = None
    customer_name: Optional[str] = None
    customer_contact: Optional[str] = None
    status: Optional[ProductRequestStatus] = None
    notes: Optional[str] = None

class ProductRequestResponse(BaseModel):
    id: str
    product_name: str
    customer_name: Optional[str] = None
    customer_contact: Optional[str] = None
    status: ProductRequestStatus
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: str
    created_by_username: Optional[str] = None

    class Config:
        from_attributes = True

class ProductRequestListResponse(BaseModel):
    total: int
    pages: int
    items: List[ProductRequestResponse]