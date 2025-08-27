from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from ..models import UserRole


class UserLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "password": "securepassword123"
            }
        }


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    role: UserRole = UserRole.CASHIER

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "email": "john@example.com",
                "full_name": "John Doe",
                "password": "securepassword123",
                "role": "cashier"
            }
        }


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: str
    role: UserRole
    is_active: bool

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "username": "john_doe",
                "email": "john@example.com",
                "full_name": "John Doe",
                "role": "cashier",
                "is_active": True
            }
        }


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 1800,
                "user": {
                    "id": "507f1f77bcf86cd799439011",
                    "username": "john_doe",
                    "email": "john@example.com",
                    "full_name": "John Doe",
                    "role": "cashier",
                    "is_active": True
                }
            }
        }


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=6, max_length=100)
    new_password: str = Field(..., min_length=6, max_length=100)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com"
            }
        }


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=32, max_length=32)
    new_password: str = Field(..., min_length=6, max_length=100)
    confirm_password: str = Field(..., min_length=6, max_length=100)

    class Config:
        json_schema_extra = {
            "example": {
                "token": "abc123def456ghi789jkl012mno345pq",
                "new_password": "newpassword123",
                "confirm_password": "newpassword123"
            }
        }

    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "oldpassword123",
                "new_password": "newpassword456"
            }
        }