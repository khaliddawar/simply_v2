"""
User Models
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class PlanType(str, Enum):
    """User plan types"""
    FREE = "free"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class UserCreate(BaseModel):
    """Schema for user registration"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Schema for user data returned from API"""
    id: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    plan_type: PlanType = PlanType.FREE
    plan_limits: Dict[str, Any] = {}
    pinecone_namespace: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """Schema for authentication tokens"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class User(BaseModel):
    """Full user model for database operations"""
    id: str
    email: EmailStr
    password_hash: Optional[str] = None  # None for OAuth users
    google_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    plan_type: PlanType = PlanType.FREE
    plan_limits: Dict[str, Any] = {}
    pinecone_namespace: str  # user_{id}
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GoogleOAuthRequest(BaseModel):
    """Schema for Google OAuth callback"""
    code: str
    redirect_uri: Optional[str] = None


class PasswordResetRequest(BaseModel):
    """Schema for password reset request"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Schema for password reset confirmation"""
    token: str
    new_password: str = Field(..., min_length=8)
