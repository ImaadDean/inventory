from pydantic import BaseModel
from typing import Optional

class PaymentUpdate(BaseModel):
    amount: float
    payment_type: str # "full" or "partial"
