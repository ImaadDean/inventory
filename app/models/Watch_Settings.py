from pydantic import BaseModel, Field
from typing import Optional
from bson import ObjectId
from ..models.user import PyObjectId

class WatchAttribute(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., min_length=2, max_length=100)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class Material(WatchAttribute):
    pass

class MovementType(WatchAttribute):
    pass

class Gender(WatchAttribute):
    pass

class Color(WatchAttribute):
    pass
