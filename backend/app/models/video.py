"""
Video Models
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Dict, Any, List
from datetime import datetime


class VideoCreate(BaseModel):
    """Schema for creating a new video"""
    youtube_id: str = Field(..., max_length=20)
    title: str = Field(..., max_length=500)
    channel_name: Optional[str] = Field(None, max_length=255)
    duration_seconds: Optional[int] = None
    thumbnail_url: Optional[str] = None
    transcript: str  # The full transcript text
    group_id: Optional[str] = None  # Optional group to add to


class VideoResponse(BaseModel):
    """Schema for video data returned from API"""
    id: str
    youtube_id: str
    title: str
    channel_name: Optional[str] = None
    duration_seconds: Optional[int] = None
    thumbnail_url: Optional[str] = None
    pinecone_file_id: Optional[str] = None
    transcript_length: Optional[int] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VideoWithTranscript(VideoResponse):
    """Video response including transcript content"""
    transcript: Optional[str] = None


class Video(BaseModel):
    """Full video model for database operations"""
    id: str
    user_id: str
    group_id: Optional[str] = None
    youtube_id: str
    title: str
    channel_name: Optional[str] = None
    duration_seconds: Optional[int] = None
    thumbnail_url: Optional[str] = None
    pinecone_file_id: Optional[str] = None
    transcript_length: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VideoListResponse(BaseModel):
    """Schema for paginated video list"""
    videos: List[VideoResponse]
    total: int
    page: int
    per_page: int
    has_more: bool


class MoveVideoRequest(BaseModel):
    """Schema for moving a video to a different group"""
    group_id: Optional[str] = None  # None to remove from group


# Summary Models for Topic Detection + Chain of Density
class SectionSummary(BaseModel):
    """Individual section summary from Chain of Density"""
    title: str
    timestamp: str
    description: str
    summary: str
    key_points: List[str] = []
    entities: List[str] = []


class SummaryMetadata(BaseModel):
    """Metadata about the summarization process"""
    model: str
    method: str
    transcript_length: int


class VideoSummaryResponse(BaseModel):
    """Full structured summary response"""
    success: bool
    video_id: Optional[str] = None
    video_title: str
    executive_summary: str
    key_takeaways: List[str] = []
    target_audience: str = ""
    sections: List[SectionSummary] = []
    total_sections: int = 0
    metadata: Optional[SummaryMetadata] = None
    error: Optional[str] = None


class EmailSummaryRequest(BaseModel):
    """Request to email a video summary"""
    recipient_email: str = Field(..., description="Email address to send summary to")
    summary_html: str = Field(..., description="HTML formatted summary content")
    video_title: Optional[str] = None
    channel_name: Optional[str] = None
    duration_seconds: Optional[int] = None
    transcript_length: Optional[int] = None


class EmailSummaryResponse(BaseModel):
    """Response from email summary endpoint"""
    success: bool
    message: Optional[str] = None
    recipient: Optional[str] = None
    error: Optional[str] = None
