from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class PasswordType(str, Enum):
    TEXT = "text"
    QR = "qr"

class UserBase(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    enabled: bool = True

class UserCreate(UserBase):
    password: str = Field(..., min_length=1)
    password_type: PasswordType

class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=1, max_length=100)
    password: Optional[str] = Field(None, min_length=1)
    password_type: Optional[PasswordType] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None

class UserResponse(UserBase):
    id: int
    password_type: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
