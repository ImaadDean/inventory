from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from bson import ObjectId
from .user import PyObjectId
from ..utils.timezone import now_kampala, kampala_to_utc


class SalaryType(str, Enum):
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"
    HOURLY = "hourly"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


class BonusType(str, Enum):
    PERFORMANCE = "performance"
    HOLIDAY = "holiday"
    OVERTIME = "overtime"
    COMMISSION = "commission"
    OTHER = "other"


class ReductionType(str, Enum):
    DEDUCTION = "deduction"
    FINE = "fine"
    TAX = "tax"
    LOAN = "loan"
    ADVANCE = "advance"
    OTHER = "other"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class Salary(BaseModel):
    """Salary record model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    worker_id: PyObjectId = Field(..., description="Reference to User ID")
    amount: float = Field(..., gt=0, description="Base salary amount")
    salary_type: SalaryType = SalaryType.MONTHLY
    pay_period: str = Field(..., description="Pay period (e.g., '2024-01' for monthly)")
    bonus_amount: float = Field(default=0.0, ge=0, description="Additional bonus amount")
    reduction_amount: float = Field(default=0.0, ge=0, description="Total reductions")
    net_amount: float = Field(..., description="Final amount after bonuses and reductions")
    status: PaymentStatus = PaymentStatus.PENDING
    payment_method: Optional[str] = Field(None, description="Payment method used")
    payment_date: Optional[datetime] = Field(None, description="Date when payment was made")
    notes: Optional[str] = Field(None, description="Additional notes")
    created_by: PyObjectId = Field(..., description="User who created this record")
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class Bonus(BaseModel):
    """Bonus record model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    worker_id: PyObjectId = Field(..., description="Reference to User ID")
    amount: float = Field(..., gt=0, description="Bonus amount")
    bonus_type: BonusType = BonusType.PERFORMANCE
    reason: str = Field(..., description="Reason for the bonus")
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[PyObjectId] = Field(None, description="User who approved this bonus")
    approved_at: Optional[datetime] = Field(None, description="Date when bonus was approved")
    applied_to_salary_id: Optional[PyObjectId] = Field(None, description="Salary record this was applied to")
    notes: Optional[str] = Field(None, description="Additional notes")
    created_by: PyObjectId = Field(..., description="User who created this record")
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class Reduction(BaseModel):
    """Reduction/Deduction record model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    worker_id: PyObjectId = Field(..., description="Reference to User ID")
    amount: float = Field(..., gt=0, description="Reduction amount")
    reduction_type: ReductionType = ReductionType.DEDUCTION
    reason: str = Field(..., description="Reason for the reduction")
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[PyObjectId] = Field(None, description="User who approved this reduction")
    approved_at: Optional[datetime] = Field(None, description="Date when reduction was approved")
    applied_to_salary_id: Optional[PyObjectId] = Field(None, description="Salary record this was applied to")
    notes: Optional[str] = Field(None, description="Additional notes")
    created_by: PyObjectId = Field(..., description="User who created this record")
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "worker_id": "507f1f77bcf86cd799439011",
                "amount": 25000.0,
                "reduction_type": "fine",
                "reason": "Late arrival penalty",
                "status": "pending",
                "notes": "3 days late in January 2024"
            }
        }


class WorkerStats(BaseModel):
    """Worker statistics model"""
    worker_id: PyObjectId
    total_salaries_paid: float = 0.0
    total_bonuses_received: float = 0.0
    total_reductions_applied: float = 0.0
    average_monthly_salary: float = 0.0
    last_salary_date: Optional[datetime] = None
    pending_bonuses: int = 0
    pending_reductions: int = 0
    months_worked: int = 0

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
