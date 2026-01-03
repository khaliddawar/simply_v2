"""
Group Models
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class GroupCreate(BaseModel):
    """Schema for creating a new group"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    color: str = Field(default="#3B82F6", pattern="^#[0-9A-Fa-f]{6}$")


class GroupUpdate(BaseModel):
    """Schema for updating a group"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")


class GroupResponse(BaseModel):
    """Schema for group data returned from API"""
    id: str
    name: str
    description: Optional[str] = None
    color: str = "#3B82F6"
    video_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Group(BaseModel):
    """Full group model for database operations"""
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    color: str = "#3B82F6"
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GroupListResponse(BaseModel):
    """Schema for group list"""
    groups: List[GroupResponse]
    total: int
