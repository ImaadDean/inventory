from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date

class RestockItem(BaseModel):
    product_id: str
    name: str
    quantity: int
    cost_price: float

class RestockCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    category: str = Field(..., min_length=1, max_length=50)
    amount: float = Field(..., gt=0)
    expense_date: date = Field(...)
    payment_method: str = Field(default="pending payment", min_length=1, max_length=50)
    vendor: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=1000)
    products: List[RestockItem]
