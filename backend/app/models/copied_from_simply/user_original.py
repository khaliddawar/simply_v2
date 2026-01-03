from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    """User role enum for authorization"""
    ADMIN = "admin"
    USER = "user"
    EDITOR = "editor"
    VIEWER = "viewer"

class UserCreate(BaseModel):
    """Schema for user registration"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[UserRole] = UserRole.USER
    company: Optional[str] = None
    
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
    role: Optional[UserRole] = UserRole.USER
    company: Optional[str] = None
    created_at: Optional[datetime] = None
    last_sign_in_at: Optional[datetime] = None
    requires_verification: Optional[bool] = False
    
    class Config:
        orm_mode = True
        
class TokenResponse(BaseModel):
    """Schema for authentication tokens"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    
class ResetPassword(BaseModel):
    """Schema for password reset request"""
    email: EmailStr
    
class ChangePassword(BaseModel):
    """Schema for changing password"""
    current_password: str
    new_password: str = Field(..., min_length=8)
    
class UpdateUser(BaseModel):
    """Schema for updating user profile"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    
class UpdateUserRole(BaseModel):
    """Schema for updating user role (admin only)"""
    role: UserRole 