from pydantic import BaseModel
from typing import Optional

class PaymentUpdate(BaseModel):
    amount: float
    method: Optional[str] = None
    payment_type: Optional[str] = None # "full" or "partial"
