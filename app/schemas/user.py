from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from ..models import UserRole


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    role: UserRole = UserRole.CASHIER

    class Config:
        json_schema_extra = {
            "example": {
                "username": "jane_doe",
                "email": "jane@example.com",
                "full_name": "Jane Doe",
                "password": "securepassword123",
                "role": "inventory_manager"
            }
        }


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=6)

    class Config:
        json_schema_extra = {
            "example": {
                "username": "janesmith",
                "email": "newemail@example.com",
                "full_name": "Jane Smith",
                "role": "admin",
                "is_active": True,
                "password": "newpassword123"
            }
        }


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    last_activity: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "username": "jane_doe",
                "email": "jane@example.com",
                "full_name": "Jane Doe",
                "role": "inventory_manager",
                "is_active": True,
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": None,
                "last_login": "2024-01-15T14:20:00Z"
            }
        }


class UserWithActivity(BaseModel):
    id: str
    username: str
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    activity_status: Dict[str, Any]

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "username": "jane_doe",
                "email": "jane@example.com",
                "full_name": "Jane Doe",
                "role": "inventory_manager",
                "is_active": True,
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": None,
                "last_login": "2024-01-15T14:20:00Z",
                "last_activity": "2024-01-15T14:25:00Z",
                "activity_status": {
                    "status": "online",
                    "display_text": "Online",
                    "is_online": True,
                    "css_class": "text-green-600",
                    "tooltip": "Online now"
                }
            }
        }


class UserList(BaseModel):
    users: List[UserWithActivity]
    total: int
    page: int
    size: int

    class Config:
        json_schema_extra = {
            "example": {
                "users": [
                    {
                        "id": "507f1f77bcf86cd799439011",
                        "username": "jane_doe",
                        "email": "jane@example.com",
                        "full_name": "Jane Doe",
                        "role": "inventory_manager",
                        "is_active": True,
                        "created_at": "2024-01-15T10:30:00Z"
                    }
                ],
                "total": 1,
                "page": 1,
                "size": 10
            }
        }