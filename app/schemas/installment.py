from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from ..models.installment import InstallmentStatus, PaymentStatus


class InstallmentItemCreate(BaseModel):
    product_id: str
    product_name: str
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., gt=0)
    total_price: float = Field(..., gt=0)


class InstallmentPaymentCreate(BaseModel):
    due_date: datetime
    amount_due: float = Field(..., gt=0)


class InstallmentCreate(BaseModel):
    # Customer information
    customer_id: Optional[str] = None
    customer_name: str = Field(..., min_length=2, max_length=100)
    customer_phone: Optional[str] = Field(None, max_length=20)
    customer_email: Optional[str] = Field(None, max_length=100)
    
    # Items
    items: List[InstallmentItemCreate] = Field(..., min_items=1)
    
    # Financial details
    total_amount: float = Field(..., gt=0)
    down_payment: float = Field(default=0.0, ge=0)
    
    # Installment plan
    number_of_payments: int = Field(..., ge=1, le=24)
    payment_frequency: str = Field(default="monthly")
    first_payment_date: datetime
    
    # Additional info
    notes: Optional[str] = Field(None, max_length=1000)
    terms_and_conditions: Optional[str] = Field(None, max_length=2000)
    
    @validator('down_payment')
    def validate_down_payment(cls, v, values):
        if 'total_amount' in values and v >= values['total_amount']:
            raise ValueError('Down payment cannot be greater than or equal to total amount')
        return v
    
    @validator('payment_frequency')
    def validate_payment_frequency(cls, v):
        allowed_frequencies = ['weekly', 'bi-weekly', 'monthly']
        if v not in allowed_frequencies:
            raise ValueError(f'Payment frequency must be one of: {", ".join(allowed_frequencies)}')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "customer_name": "Jane Doe",
                "customer_phone": "+256700000000",
                "items": [
                    {
                        "product_id": "507f1f77bcf86cd799439011",
                        "product_name": "Dior Sauvage 100ml",
                        "quantity": 1,
                        "unit_price": 200000,
                        "total_price": 200000
                    }
                ],
                "total_amount": 200000,
                "down_payment": 50000,
                "number_of_payments": 3,
                "payment_frequency": "monthly",
                "first_payment_date": "2024-02-01T00:00:00Z",
                "notes": "Customer prefers monthly payments"
            }
        }


class InstallmentPaymentResponse(BaseModel):
    payment_number: int
    due_date: datetime
    amount_due: float
    amount_paid: float
    payment_date: Optional[datetime]
    status: PaymentStatus
    remaining_amount: float
    is_overdue: bool
    notes: Optional[str]


class InstallmentResponse(BaseModel):
    id: str
    installment_number: str
    customer_id: Optional[str]
    customer_name: str
    customer_phone: Optional[str]
    customer_email: Optional[str]
    order_id: Optional[str]
    items: List[dict]
    total_amount: float
    down_payment: float
    remaining_amount: float
    number_of_payments: int
    payment_frequency: str
    payments: List[InstallmentPaymentResponse]
    status: InstallmentStatus
    created_by: str
    approved_by: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    completed_at: Optional[datetime]
    notes: Optional[str]
    terms_and_conditions: Optional[str]
    
    # Calculated fields
    total_paid: float
    total_remaining: float
    completion_percentage: float
    next_payment_due: Optional[InstallmentPaymentResponse]
    overdue_payments: List[InstallmentPaymentResponse]


class InstallmentUpdate(BaseModel):
    customer_phone: Optional[str] = Field(None, max_length=20)
    customer_email: Optional[str] = Field(None, max_length=100)
    status: Optional[InstallmentStatus] = None
    notes: Optional[str] = Field(None, max_length=1000)
    terms_and_conditions: Optional[str] = Field(None, max_length=2000)


class InstallmentPaymentRecordCreate(BaseModel):
    installment_id: str
    payment_number: int = Field(..., ge=1)
    amount: float = Field(..., gt=0)
    payment_method: str = Field(..., max_length=50)
    notes: Optional[str] = Field(None, max_length=500)

    class Config:
        json_schema_extra = {
            "example": {
                "installment_id": "507f1f77bcf86cd799439011",
                "payment_number": 1,
                "amount": 50000,
                "payment_method": "cash",
                "notes": "First installment payment"
            }
        }


class InstallmentPaymentRecordResponse(BaseModel):
    id: str
    installment_id: str
    payment_number: int
    amount: float
    payment_method: str
    payment_date: datetime
    received_by: str
    receipt_number: Optional[str]
    notes: Optional[str]


class InstallmentListResponse(BaseModel):
    installments: List[InstallmentResponse]
    total: int
    page: int
    size: int
    total_pages: int


class InstallmentSummary(BaseModel):
    """Summary statistics for installments dashboard"""
    total_installments: int
    active_installments: int
    completed_installments: int
    overdue_installments: int
    total_amount_outstanding: float
    total_amount_collected: float
    overdue_amount: float


class POSInstallmentCreate(BaseModel):
    """Simplified schema for creating installments from POS"""
    customer_id: Optional[str] = None
    customer_name: str = Field(..., min_length=2, max_length=100)
    customer_phone: Optional[str] = Field(None, max_length=20)
    items: List[dict]  # Cart items from POS
    total_amount: float = Field(..., gt=0)
    down_payment: float = Field(default=0.0, ge=0)
    number_of_payments: int = Field(..., ge=1, le=12)  # Limit to 12 for POS
    payment_frequency: str = Field(default="monthly")
    notes: Optional[str] = Field(None, max_length=500)

    class Config:
        json_schema_extra = {
            "example": {
                "customer_name": "John Doe",
                "customer_phone": "+256700000000",
                "items": [
                    {
                        "product_id": "507f1f77bcf86cd799439011",
                        "name": "Chanel No. 5",
                        "quantity": 1,
                        "price": 150000,
                        "total": 150000
                    }
                ],
                "total_amount": 150000,
                "down_payment": 30000,
                "number_of_payments": 4,
                "payment_frequency": "monthly"
            }
        }
