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
    """Schema for Google OAuth callback (code exchange)"""
    code: str
    redirect_uri: Optional[str] = None


class GoogleUserDataRequest(BaseModel):
    """Body for POST /api/auth/google/extension (dashboard and extension).

    access_token is the Google OAuth access token. The server checks it with
    Google, and the account id and email come only from Google's answer.
    It is optional here only so that old extension builds, which do not send
    it, get a readable 401 from the route instead of a 422 validation error;
    the route refuses every request without it.

    google_id and email are still accepted from older clients, but they are
    never trusted: if present, they must match what Google says, or the
    request is refused.
    """
    access_token: Optional[str] = None
    google_id: Optional[str] = None
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None


class PasswordResetRequest(BaseModel):
    """Schema for password reset request"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Schema for password reset confirmation"""
    token: str
    new_password: str = Field(..., min_length=8)
