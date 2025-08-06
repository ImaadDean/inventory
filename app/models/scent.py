from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from .user import PyObjectId
from ..utils.timezone import now_kampala, kampala_to_utc


class Scent(BaseModel):
    """Model for perfume scents"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=2, max_length=100, description="Name of the scent")
    description: Optional[str] = Field(None, max_length=500, description="Description of the scent")
    scent_family: Optional[str] = Field(None, max_length=50, description="Scent family (e.g., Floral, Woody, Fresh)")
    top_notes: Optional[str] = Field(None, max_length=200, description="Top notes of the scent")
    middle_notes: Optional[str] = Field(None, max_length=200, description="Middle/heart notes of the scent")
    base_notes: Optional[str] = Field(None, max_length=200, description="Base notes of the scent")
    longevity: Optional[str] = Field(None, max_length=20, description="How long the scent lasts (e.g., 6-8 hours)")
    sillage: Optional[str] = Field(None, max_length=20, description="Projection strength (e.g., Moderate, Strong)")
    season: Optional[str] = Field(None, max_length=50, description="Best season for this scent")
    occasion: Optional[str] = Field(None, max_length=50, description="Best occasion for this scent")
    gender: Optional[str] = Field(None, max_length=20, description="Target gender (Unisex, Men, Women)")
    is_active: bool = Field(default=True, description="Whether the scent is active")
    created_at: datetime = Field(default_factory=lambda: kampala_to_utc(now_kampala()))
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {PyObjectId: str}
        json_schema_extra = {
            "example": {
                "name": "Fresh Citrus Burst",
                "description": "A vibrant and energizing citrus fragrance perfect for daily wear",
                "scent_family": "Fresh",
                "top_notes": "Lemon, Bergamot, Orange",
                "middle_notes": "Lavender, Mint",
                "base_notes": "Cedar, Musk",
                "longevity": "6-8 hours",
                "sillage": "Moderate",
                "season": "Spring/Summer",
                "occasion": "Casual/Office",
                "gender": "Unisex",
                "is_active": True
            }
        }