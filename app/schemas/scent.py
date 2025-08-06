from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ScentBase(BaseModel):
    """Base schema for scent"""
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


class ScentCreate(ScentBase):
    """Schema for creating a scent"""
    
    class Config:
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


class ScentUpdate(BaseModel):
    """Schema for updating a scent"""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    scent_family: Optional[str] = Field(None, max_length=50)
    top_notes: Optional[str] = Field(None, max_length=200)
    middle_notes: Optional[str] = Field(None, max_length=200)
    base_notes: Optional[str] = Field(None, max_length=200)
    longevity: Optional[str] = Field(None, max_length=20)
    sillage: Optional[str] = Field(None, max_length=20)
    season: Optional[str] = Field(None, max_length=50)
    occasion: Optional[str] = Field(None, max_length=50)
    gender: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None


class ScentResponse(ScentBase):
    """Schema for scent response"""
    id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
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
                "is_active": True,
                "created_at": "2024-01-20T10:00:00Z",
                "updated_at": "2024-01-20T10:00:00Z"
            }
        }


class ScentList(BaseModel):
    """Schema for scent list response"""
    scents: list[ScentResponse]
    total: int
    page: int
    size: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "scents": [
                    {
                        "id": "507f1f77bcf86cd799439011",
                        "name": "Fresh Citrus Burst",
                        "description": "A vibrant and energizing citrus fragrance",
                        "scent_family": "Fresh",
                        "is_active": True,
                        "created_at": "2024-01-20T10:00:00Z"
                    }
                ],
                "total": 1,
                "page": 1,
                "size": 10
            }
        }
