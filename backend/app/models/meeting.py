"""
Meeting Transcript Models for Fireflies and Zoom Webhooks
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class MeetingSource(str, Enum):
    """Source of the meeting transcript"""
    FIREFLIES = "fireflies"
    ZOOM = "zoom"
    MANUAL = "manual"


# ============== Fireflies Webhook Models ==============

class FirefliesAttendee(BaseModel):
    """Attendee in a Fireflies meeting"""
    displayName: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None


class FirefliesSentence(BaseModel):
    """Individual sentence in Fireflies transcript"""
    text: str
    raw_text: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    speaker_id: Optional[int] = None
    speaker_name: Optional[str] = None


class FirefliesWebhookData(BaseModel):
    """Fireflies webhook payload structure

    Based on Fireflies API documentation:
    https://docs.fireflies.ai/integrations/webhooks
    """
    meeting_id: str = Field(..., alias="meetingId")
    transcript_id: Optional[str] = Field(None, alias="transcriptId")
    title: Optional[str] = None
    organizer_email: Optional[str] = Field(None, alias="organizerEmail")
    date: Optional[str] = None  # ISO date string
    duration: Optional[float] = None  # Duration in minutes
    attendees: Optional[List[FirefliesAttendee]] = []
    transcript: Optional[str] = None  # Plain text transcript
    sentences: Optional[List[FirefliesSentence]] = []
    summary: Optional[str] = None
    action_items: Optional[List[str]] = Field(default=[], alias="actionItems")
    meeting_link: Optional[str] = Field(None, alias="meetingLink")
    audio_url: Optional[str] = Field(None, alias="audioUrl")
    video_url: Optional[str] = Field(None, alias="videoUrl")

    class Config:
        populate_by_name = True


class FirefliesWebhookPayload(BaseModel):
    """Full Fireflies webhook payload"""
    event: str  # e.g., "Transcription completed"
    meeting: Optional[FirefliesWebhookData] = None
    data: Optional[FirefliesWebhookData] = None  # Some events use 'data' instead of 'meeting'

    def get_meeting_data(self) -> Optional[FirefliesWebhookData]:
        """Get meeting data from either 'meeting' or 'data' field"""
        return self.meeting or self.data


# ============== Zoom Webhook Models ==============

class ZoomParticipant(BaseModel):
    """Participant in a Zoom meeting"""
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    email: Optional[str] = None


class ZoomRecordingFile(BaseModel):
    """Zoom recording file details"""
    id: Optional[str] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    download_url: Optional[str] = None
    play_url: Optional[str] = None
    recording_start: Optional[str] = None
    recording_end: Optional[str] = None


class ZoomMeetingPayload(BaseModel):
    """Zoom meeting details in webhook"""
    id: Optional[str] = None
    uuid: Optional[str] = None
    host_id: Optional[str] = None
    host_email: Optional[str] = None
    topic: Optional[str] = None
    start_time: Optional[str] = None
    duration: Optional[int] = None  # Duration in minutes
    timezone: Optional[str] = None
    participants: Optional[List[ZoomParticipant]] = []
    recording_files: Optional[List[ZoomRecordingFile]] = []


class ZoomTranscriptContent(BaseModel):
    """Zoom transcript content structure"""
    text: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    speaker: Optional[str] = None


class ZoomWebhookPayload(BaseModel):
    """Zoom webhook payload structure

    Based on Zoom Webhook documentation:
    https://developers.zoom.us/docs/api/rest/webhook-reference/
    """
    event: str  # e.g., "recording.transcript_completed"
    event_ts: Optional[int] = None  # Unix timestamp
    payload: Optional[Dict[str, Any]] = None

    def get_meeting_id(self) -> Optional[str]:
        """Extract meeting ID from payload"""
        if self.payload and "object" in self.payload:
            return self.payload["object"].get("id") or self.payload["object"].get("uuid")
        return None

    def get_topic(self) -> Optional[str]:
        """Extract meeting topic/subject from payload"""
        if self.payload and "object" in self.payload:
            return self.payload["object"].get("topic")
        return None

    def get_start_time(self) -> Optional[str]:
        """Extract meeting start time from payload"""
        if self.payload and "object" in self.payload:
            return self.payload["object"].get("start_time")
        return None

    def get_duration(self) -> Optional[int]:
        """Extract meeting duration from payload"""
        if self.payload and "object" in self.payload:
            return self.payload["object"].get("duration")
        return None

    def get_host_email(self) -> Optional[str]:
        """Extract host email from payload"""
        if self.payload and "object" in self.payload:
            return self.payload["object"].get("host_email")
        return None


# ============== Meeting Transcript Database Models ==============

class MeetingCreate(BaseModel):
    """Schema for creating a meeting transcript manually"""
    title: str = Field(..., max_length=500)
    subject: Optional[str] = Field(None, max_length=500)
    transcript: str
    meeting_date: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    participants: Optional[List[str]] = []
    source: MeetingSource = MeetingSource.MANUAL
    group_id: Optional[str] = None


class MeetingResponse(BaseModel):
    """Schema for meeting transcript response"""
    id: str
    external_id: Optional[str] = None
    source: str
    title: str
    subject: Optional[str] = None
    organizer_email: Optional[str] = None
    meeting_date: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    participants: Optional[List[str]] = []
    transcript_length: Optional[int] = None
    pinecone_file_id: Optional[str] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    # Summary cache status
    has_summary: bool = False
    summary_generated_at: Optional[datetime] = None
    # Source-specific metadata
    source_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MeetingWithTranscript(MeetingResponse):
    """Meeting response including transcript content"""
    transcript: Optional[str] = None


class MeetingListResponse(BaseModel):
    """Schema for paginated meeting list"""
    meetings: List[MeetingResponse]
    total: int
    page: int
    per_page: int
    has_more: bool


class MeetingSummaryResponse(BaseModel):
    """Summary response for meeting transcript"""
    success: bool
    meeting_id: Optional[str] = None
    meeting_title: str
    meeting_subject: Optional[str] = None
    meeting_date: Optional[str] = None
    participants: Optional[List[str]] = []
    executive_summary: str
    key_takeaways: List[str] = []
    action_items: List[str] = []
    decisions_made: List[str] = []
    topics_discussed: List[str] = []
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    cached: bool = False
    cached_at: Optional[str] = None


# ============== Webhook Response Models ==============

class WebhookResponse(BaseModel):
    """Standard webhook response"""
    success: bool
    message: str
    meeting_id: Optional[str] = None
    error: Optional[str] = None
