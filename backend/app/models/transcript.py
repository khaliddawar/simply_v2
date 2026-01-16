"""
Unified Transcript Models for the Transcript Library System

This module defines Pydantic models for the unified transcript system that
supports multiple content sources (YouTube, Fireflies, Zoom, manual, PDF, audio).
"""
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime


class SourceType(str, Enum):
    """
    Supported transcript source types.

    Each source type has specific metadata requirements defined in the
    UNIFIED_LIBRARY_PLAN.md document.
    """
    YOUTUBE = "youtube"
    FIREFLIES = "fireflies"
    ZOOM = "zoom"
    MANUAL = "manual"
    PDF = "pdf"       # Future: PDF document extraction
    AUDIO = "audio"   # Future: Audio file transcription


class TranscriptCreate(BaseModel):
    """
    Request model for creating a new transcript.

    The metadata field should contain source-specific information:
    - YouTube: youtube_id, channel_name, duration_seconds, thumbnail_url, published_at
    - Fireflies/Zoom: meeting_id, subject, organizer_email, participants, meeting_date, duration_minutes
    - PDF: filename, page_count, file_size_bytes, author
    - Audio: filename, duration_seconds, file_size_bytes, transcription_service, language
    """
    source_type: SourceType = Field(..., description="Type of content source")
    external_id: Optional[str] = Field(
        None,
        max_length=255,
        description="External identifier (youtube_id, meeting_id, filename, etc.)"
    )
    title: str = Field(..., max_length=500, description="Transcript title")
    transcript_text: str = Field(..., description="Full transcript text content")
    group_id: Optional[str] = Field(
        None,
        description="UUID of the group to add this transcript to"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific metadata (channel_name, participants, etc.)"
    )


class TranscriptResponse(BaseModel):
    """
    Response model for transcript data returned from API.

    Contains all transcript fields except the full transcript text
    for efficient list operations.
    """
    id: str = Field(..., description="Unique transcript UUID")
    user_id: str = Field(..., description="Owner user UUID")
    group_id: Optional[str] = Field(None, description="Group UUID if assigned")
    source_type: SourceType = Field(..., description="Content source type")
    external_id: Optional[str] = Field(
        None,
        description="External identifier from source system"
    )
    title: str = Field(..., description="Transcript title")
    transcript_length: Optional[int] = Field(
        None,
        description="Character count of transcript text"
    )
    has_summary: bool = Field(
        default=False,
        description="True if a cached summary exists"
    )
    summary_generated_at: Optional[datetime] = Field(
        None,
        description="Timestamp when summary was last generated"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific metadata"
    )
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Record last update timestamp")

    class Config:
        from_attributes = True


class TranscriptWithText(TranscriptResponse):
    """
    Extended transcript response including full transcript text.

    Used when the full transcript content is needed (e.g., for display
    or processing).
    """
    transcript_text: Optional[str] = Field(
        None,
        description="Full transcript text content"
    )


class TranscriptListResponse(BaseModel):
    """
    Paginated list response for transcripts.

    Used by the GET /api/transcripts endpoint to return filtered
    and sorted transcript lists.
    """
    transcripts: List[TranscriptResponse] = Field(
        default_factory=list,
        description="List of transcript records"
    )
    total: int = Field(..., description="Total count of matching transcripts")


class TranscriptSummaryResponse(BaseModel):
    """
    Response model for transcript summary data.

    The summary structure matches the existing video/podcast summary format
    for compatibility with the dashboard.
    """
    transcript_id: str = Field(..., description="UUID of the transcript")
    title: str = Field(..., description="Transcript title")
    source_type: SourceType = Field(..., description="Content source type")
    summary: Dict[str, Any] = Field(
        ...,
        description="Structured summary containing executive_summary, key_takeaways, sections, etc."
    )
    generated_at: datetime = Field(..., description="When this summary was generated")
    cached: bool = Field(
        default=False,
        description="True if returned from cache, False if freshly generated"
    )


class TranscriptUpdateGroup(BaseModel):
    """
    Request model for moving a transcript to a different group.

    Set group_id to None to remove from any group (move to "Recent").
    """
    group_id: Optional[str] = Field(
        None,
        description="Target group UUID, or null to move to Recent/ungrouped"
    )


# ============== Summary Sub-Models (for compatibility with existing summary structure) ==============

class SectionSummary(BaseModel):
    """
    Individual section summary from Chain of Density summarization.

    Represents a logical section/topic within the transcript.
    """
    title: str = Field(..., description="Section title/topic")
    timestamp: str = Field(..., description="Approximate timestamp or position")
    description: str = Field(..., description="Brief description of section content")
    summary: str = Field(..., description="Dense summary of section")
    key_points: List[str] = Field(
        default_factory=list,
        description="Key points extracted from this section"
    )
    entities: List[str] = Field(
        default_factory=list,
        description="Named entities mentioned in this section"
    )


class SummaryMetadata(BaseModel):
    """Metadata about the summarization process."""
    model: str = Field(..., description="LLM model used for summarization")
    method: str = Field(..., description="Summarization method (e.g., 'chain_of_density')")
    transcript_length: int = Field(..., description="Original transcript character count")


class FullSummaryResponse(BaseModel):
    """
    Full structured summary response with all summary components.

    This matches the existing VideoSummaryResponse and PodcastSummaryResponse
    format for dashboard compatibility.
    """
    success: bool = Field(..., description="Whether summarization succeeded")
    transcript_id: Optional[str] = Field(None, description="UUID of the transcript")
    title: str = Field(..., description="Transcript title")
    source_type: SourceType = Field(..., description="Content source type")
    executive_summary: str = Field(
        default="",
        description="High-level overview of the entire transcript"
    )
    key_takeaways: List[str] = Field(
        default_factory=list,
        description="Main points and insights from the transcript"
    )
    target_audience: str = Field(
        default="",
        description="Intended audience for this content"
    )
    sections: List[SectionSummary] = Field(
        default_factory=list,
        description="Section-by-section summaries"
    )
    total_sections: int = Field(default=0, description="Number of sections detected")
    metadata: Optional[SummaryMetadata] = Field(
        None,
        description="Summarization process metadata"
    )
    error: Optional[str] = Field(None, description="Error message if summarization failed")
    cached: bool = Field(
        default=False,
        description="True if returned from cache, False if freshly generated"
    )
    cached_at: Optional[str] = Field(
        None,
        description="ISO timestamp when summary was cached"
    )


# ============== Email Summary Models ==============

class EmailSummaryRequest(BaseModel):
    """Request to email a transcript summary."""
    recipient_email: str = Field(
        ...,
        description="Email address to send summary to"
    )
    summary_html: str = Field(
        ...,
        description="HTML formatted summary content"
    )
    title: Optional[str] = Field(None, description="Transcript title for email subject")
    source_type: Optional[SourceType] = Field(
        None,
        description="Source type for email template selection"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata for email template"
    )


class EmailSummaryResponse(BaseModel):
    """Response from email summary endpoint."""
    success: bool = Field(..., description="Whether email was sent successfully")
    message: Optional[str] = Field(None, description="Success message")
    recipient: Optional[str] = Field(None, description="Email address sent to")
    error: Optional[str] = Field(None, description="Error message if sending failed")
