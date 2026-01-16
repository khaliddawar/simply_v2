"""
Transcript Routes - Unified API for all transcript operations

This module provides API endpoints for the unified transcript system that
supports multiple content sources (YouTube, Fireflies, Zoom, manual, PDF, audio).
It replaces the separate /api/videos and /api/podcasts endpoints for new code paths.

Endpoints:
    POST   /api/transcripts              - Create a new transcript
    GET    /api/transcripts              - List transcripts with filtering/sorting
    GET    /api/transcripts/{id}         - Get a single transcript
    DELETE /api/transcripts/{id}         - Delete a transcript
    PATCH  /api/transcripts/{id}/group   - Move transcript to a group
    GET    /api/transcripts/{id}/summary - Get or generate summary
    POST   /api/transcripts/{id}/email-summary - Email summary to user
    GET    /api/transcripts/{id}/transcript - Get transcript text only
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Body

from app.models.transcript import (
    TranscriptCreate,
    TranscriptResponse,
    TranscriptWithText,
    TranscriptListResponse,
    TranscriptSummaryResponse,
    TranscriptUpdateGroup,
    FullSummaryResponse,
    EmailSummaryRequest,
    EmailSummaryResponse,
    SourceType
)
from app.services.transcript_service import get_transcript_service
from app.services.email_service import get_email_service
from app.services.database_service import get_database_service
from app.routes.auth import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])


# =============================================================================
# Transcript CRUD Endpoints
# =============================================================================

@router.post("", response_model=TranscriptResponse)
async def create_transcript(
    data: TranscriptCreate,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create a new transcript from any source.

    This endpoint:
    1. Validates the request data
    2. Checks for duplicates using (user_id, source_type, external_id)
    3. Creates the transcript in the database
    4. Uploads to Pinecone for RAG search

    Request Body:
        source_type: Type of source ('youtube', 'fireflies', 'zoom', 'manual', 'pdf', 'audio')
        title: Transcript title
        transcript_text: Full transcript text content
        external_id: Optional external identifier (youtube_id, meeting_id, etc.)
        group_id: Optional group UUID to assign the transcript to
        metadata: Source-specific metadata (channel_name, participants, duration, etc.)

    Returns:
        TranscriptResponse with created transcript data

    Raises:
        400: Invalid request data or creation failed
        401: Not authenticated
    """
    transcript_service = get_transcript_service()

    result = await transcript_service.create_transcript(
        user_id=user_id,
        source_type=data.source_type.value,
        title=data.title,
        transcript_text=data.transcript_text,
        external_id=data.external_id,
        group_id=data.group_id,
        metadata=data.metadata
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    transcript = result["transcript"]

    # Build response model
    return TranscriptResponse(
        id=str(transcript["id"]),
        user_id=str(transcript.get("user_id", user_id)),
        group_id=str(transcript["group_id"]) if transcript.get("group_id") else None,
        source_type=SourceType(transcript.get("source_type", data.source_type.value)),
        external_id=transcript.get("external_id"),
        title=transcript["title"],
        transcript_length=transcript.get("transcript_length"),
        has_summary=transcript.get("has_summary", False),
        summary_generated_at=transcript.get("summary_generated_at"),
        metadata=transcript.get("metadata", {}),
        created_at=transcript["created_at"],
        updated_at=transcript["updated_at"]
    )


@router.get("", response_model=TranscriptListResponse)
async def list_transcripts(
    user_id: str = Depends(get_current_user_id),
    group_id: Optional[str] = Query(
        None,
        description="Filter by group UUID"
    ),
    source_type: Optional[str] = Query(
        None,
        description="Filter by source type ('youtube', 'fireflies', 'zoom', 'manual')"
    ),
    ungrouped: bool = Query(
        False,
        description="If true, return only ungrouped transcripts (for 'Recent' section)"
    ),
    sort_by: str = Query(
        "created_at",
        regex="^(created_at|title|source_type)$",
        description="Field to sort by"
    ),
    sort_order: str = Query(
        "desc",
        regex="^(asc|desc)$",
        description="Sort order"
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximum number of transcripts to return"
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of transcripts to skip (for pagination)"
    )
):
    """
    List user's transcripts with filtering and sorting.

    Supports filtering by:
    - group_id: Show only transcripts in a specific group
    - source_type: Show only transcripts from a specific source
    - ungrouped: Show only transcripts not assigned to any group

    Supports sorting by:
    - created_at: Date added (default)
    - title: Alphabetical by title
    - source_type: Grouped by source

    Returns:
        TranscriptListResponse with list of transcripts and total count

    Raises:
        401: Not authenticated
    """
    transcript_service = get_transcript_service()

    result = await transcript_service.list_transcripts(
        user_id=user_id,
        group_id=group_id,
        source_type=source_type,
        ungrouped_only=ungrouped,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    # Build response models for each transcript
    transcripts = []
    for t in result["transcripts"]:
        # Determine source type - handle both string and enum values
        st = t.get("source_type", "manual")
        if isinstance(st, SourceType):
            source_type_enum = st
        else:
            try:
                source_type_enum = SourceType(st)
            except ValueError:
                source_type_enum = SourceType.MANUAL

        transcripts.append(TranscriptResponse(
            id=str(t["id"]),
            user_id=str(t.get("user_id", user_id)),
            group_id=str(t["group_id"]) if t.get("group_id") else None,
            source_type=source_type_enum,
            external_id=t.get("external_id"),
            title=t["title"],
            transcript_length=t.get("transcript_length"),
            has_summary=t.get("has_summary", False),
            summary_generated_at=t.get("summary_generated_at"),
            metadata=t.get("metadata", {}),
            created_at=t["created_at"],
            updated_at=t["updated_at"]
        ))

    return TranscriptListResponse(
        transcripts=transcripts,
        total=result["total"]
    )


@router.get("/{transcript_id}", response_model=TranscriptResponse)
async def get_transcript(
    transcript_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get a specific transcript by ID.

    Args:
        transcript_id: UUID of the transcript

    Returns:
        TranscriptResponse with transcript data

    Raises:
        401: Not authenticated
        404: Transcript not found
    """
    transcript_service = get_transcript_service()

    result = await transcript_service.get_transcript(
        user_id=user_id,
        transcript_id=transcript_id,
        include_transcript=False
    )

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Transcript not found"))

    t = result["transcript"]

    # Determine source type
    st = t.get("source_type", "manual")
    if isinstance(st, SourceType):
        source_type_enum = st
    else:
        try:
            source_type_enum = SourceType(st)
        except ValueError:
            source_type_enum = SourceType.MANUAL

    return TranscriptResponse(
        id=str(t["id"]),
        user_id=str(t.get("user_id", user_id)),
        group_id=str(t["group_id"]) if t.get("group_id") else None,
        source_type=source_type_enum,
        external_id=t.get("external_id"),
        title=t["title"],
        transcript_length=t.get("transcript_length"),
        has_summary=t.get("has_summary", False),
        summary_generated_at=t.get("summary_generated_at"),
        metadata=t.get("metadata", {}),
        created_at=t["created_at"],
        updated_at=t["updated_at"]
    )


@router.delete("/{transcript_id}")
async def delete_transcript(
    transcript_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Delete a transcript.

    This removes the transcript from both the database and Pinecone.

    Args:
        transcript_id: UUID of the transcript to delete

    Returns:
        {"success": true}

    Raises:
        401: Not authenticated
        404: Transcript not found
    """
    transcript_service = get_transcript_service()

    result = await transcript_service.delete_transcript(
        user_id=user_id,
        transcript_id=transcript_id
    )

    if not result.get("success"):
        error = result.get("error", "Failed to delete transcript")
        if "not found" in error.lower():
            raise HTTPException(status_code=404, detail=error)
        raise HTTPException(status_code=400, detail=error)

    return {"success": True}


# =============================================================================
# Group Management Endpoint
# =============================================================================

@router.patch("/{transcript_id}/group", response_model=TranscriptResponse)
async def move_transcript_to_group(
    transcript_id: str,
    data: TranscriptUpdateGroup = Body(...),
    user_id: str = Depends(get_current_user_id)
):
    """
    Move transcript to a group or back to Recent (ungrouped).

    Set group_id to null to remove from any group and move to "Recent" section.

    Args:
        transcript_id: UUID of the transcript to move
        data: Request body containing group_id (string UUID or null)

    Returns:
        TranscriptResponse with updated transcript data

    Raises:
        401: Not authenticated
        404: Transcript or group not found
    """
    transcript_service = get_transcript_service()

    # Move the transcript
    result = await transcript_service.move_to_group(
        user_id=user_id,
        transcript_id=transcript_id,
        group_id=data.group_id
    )

    if not result.get("success"):
        error = result.get("error", "Failed to move transcript")
        if "not found" in error.lower():
            raise HTTPException(status_code=404, detail=error)
        raise HTTPException(status_code=400, detail=error)

    # Get updated transcript to return
    get_result = await transcript_service.get_transcript(
        user_id=user_id,
        transcript_id=transcript_id
    )

    if not get_result.get("success"):
        raise HTTPException(status_code=404, detail="Transcript not found after update")

    t = get_result["transcript"]

    # Determine source type
    st = t.get("source_type", "manual")
    if isinstance(st, SourceType):
        source_type_enum = st
    else:
        try:
            source_type_enum = SourceType(st)
        except ValueError:
            source_type_enum = SourceType.MANUAL

    return TranscriptResponse(
        id=str(t["id"]),
        user_id=str(t.get("user_id", user_id)),
        group_id=str(t["group_id"]) if t.get("group_id") else None,
        source_type=source_type_enum,
        external_id=t.get("external_id"),
        title=t["title"],
        transcript_length=t.get("transcript_length"),
        has_summary=t.get("has_summary", False),
        summary_generated_at=t.get("summary_generated_at"),
        metadata=t.get("metadata", {}),
        created_at=t["created_at"],
        updated_at=t["updated_at"]
    )


# =============================================================================
# Summary Endpoints
# =============================================================================

@router.get("/{transcript_id}/summary", response_model=FullSummaryResponse)
async def get_transcript_summary(
    transcript_id: str,
    force: bool = Query(
        False,
        description="Force regeneration of summary even if cached version exists"
    ),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get or generate summary for a transcript.

    Summary Caching:
    - Summaries are cached after first generation to avoid repeated LLM calls
    - Use force=true to regenerate and update the cached summary
    - Cached summaries are returned instantly without any LLM calls

    Generation Process (when not cached or force=true):
    1. Detects topic sections in the transcript
    2. Applies Chain of Density summarization to each section
    3. Generates an executive summary with key takeaways

    Args:
        transcript_id: UUID of the transcript
        force: If true, regenerate summary even if cached

    Returns:
        FullSummaryResponse with structured summary

    Raises:
        400: No transcript text available
        401: Not authenticated
        404: Transcript not found
        503: Summarization service unavailable
    """
    transcript_service = get_transcript_service()

    # Get transcript first to determine source type
    transcript_result = await transcript_service.get_transcript(
        user_id=user_id,
        transcript_id=transcript_id
    )

    if not transcript_result.get("success"):
        raise HTTPException(status_code=404, detail="Transcript not found")

    transcript = transcript_result["transcript"]

    # Get or generate summary
    result = await transcript_service.get_summary(
        user_id=user_id,
        transcript_id=transcript_id,
        force_regenerate=force
    )

    if not result.get("success"):
        error = result.get("error", "Failed to get summary")
        if "not available" in error.lower() or "no transcript" in error.lower():
            raise HTTPException(status_code=400, detail=error)
        if "not found" in error.lower():
            raise HTTPException(status_code=404, detail=error)
        if "service" in error.lower():
            raise HTTPException(status_code=503, detail=error)
        raise HTTPException(status_code=500, detail=error)

    summary = result.get("summary", {})
    generated_at = result.get("generated_at")
    from_cache = result.get("from_cache", False)

    # Determine source type
    st = transcript.get("source_type", "manual")
    if isinstance(st, SourceType):
        source_type_enum = st
    else:
        try:
            source_type_enum = SourceType(st)
        except ValueError:
            source_type_enum = SourceType.MANUAL

    # Build response - handle both old video/podcast format and new unified format
    return FullSummaryResponse(
        success=True,
        transcript_id=transcript_id,
        title=transcript.get("title", "Untitled"),
        source_type=source_type_enum,
        executive_summary=summary.get("executive_summary", ""),
        key_takeaways=summary.get("key_takeaways", []),
        target_audience=summary.get("target_audience", ""),
        sections=summary.get("sections", []),
        total_sections=summary.get("total_sections", len(summary.get("sections", []))),
        metadata=summary.get("metadata"),
        cached=from_cache,
        cached_at=generated_at.isoformat() if generated_at and from_cache else None
    )


@router.post("/{transcript_id}/email-summary", response_model=EmailSummaryResponse)
async def email_transcript_summary(
    transcript_id: str,
    request: EmailSummaryRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Send a transcript summary via email.

    This endpoint sends the provided summary HTML to the specified email address
    using the Postmark email service.

    Args:
        transcript_id: UUID of the transcript
        request: Email request containing recipient_email, summary_html, and optional metadata

    Returns:
        {"success": true, "message": "..."}

    Raises:
        401: Not authenticated
        404: Transcript not found
        503: Email service unavailable
    """
    email_service = get_email_service()
    transcript_service = get_transcript_service()

    # Check if email service is available
    if not email_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email service not available - Postmark API key not configured"
        )

    # Get transcript metadata
    result = await transcript_service.get_transcript(
        user_id=user_id,
        transcript_id=transcript_id,
        include_transcript=False
    )

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Transcript not found"))

    transcript = result["transcript"]
    metadata = transcript.get("metadata", {})

    # Determine duration based on source type
    duration_seconds = None
    source_type = transcript.get("source_type", "manual")

    if source_type == SourceType.YOUTUBE.value or source_type == SourceType.YOUTUBE:
        duration_seconds = metadata.get("duration_seconds")
    elif source_type in [SourceType.FIREFLIES.value, SourceType.ZOOM.value] or \
         source_type in [SourceType.FIREFLIES, SourceType.ZOOM]:
        # Convert minutes to seconds for meetings
        duration_minutes = metadata.get("duration_minutes")
        if duration_minutes:
            duration_seconds = duration_minutes * 60

    # Send email
    email_result = await email_service.send_summary_email(
        recipient_email=request.recipient_email,
        video_title=request.title or transcript.get("title", "Transcript Summary"),
        summary_html=request.summary_html,
        video_id=transcript.get("external_id") or transcript_id,
        channel_name=metadata.get("channel_name") or metadata.get("subject"),
        duration_seconds=duration_seconds,
        transcript_length=transcript.get("transcript_length")
    )

    if not email_result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=email_result.get("error", "Failed to send email")
        )

    return EmailSummaryResponse(**email_result)


# =============================================================================
# Transcript Text Endpoint
# =============================================================================

@router.get("/{transcript_id}/transcript")
async def get_transcript_text(
    transcript_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get just the transcript text for a transcript.

    This is a lightweight endpoint that returns only the transcript text,
    useful for cases where you don't need the full transcript metadata.

    Args:
        transcript_id: UUID of the transcript

    Returns:
        {"transcript_id": str, "transcript_text": str}

    Raises:
        401: Not authenticated
        404: Transcript not found
    """
    transcript_service = get_transcript_service()

    result = await transcript_service.get_transcript_text(
        user_id=user_id,
        transcript_id=transcript_id
    )

    if not result.get("success"):
        error = result.get("error", "Transcript not found")
        if "not found" in error.lower():
            raise HTTPException(status_code=404, detail=error)
        raise HTTPException(status_code=400, detail=error)

    return {
        "transcript_id": transcript_id,
        "transcript_text": result.get("transcript_text")
    }


# =============================================================================
# Check Duplicate Endpoint (convenience)
# =============================================================================

@router.get("/check/{source_type}/{external_id}")
async def check_transcript_exists(
    source_type: str,
    external_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Check if a transcript already exists for the given source type and external ID.

    This is useful for the extension to check if a video/meeting has already
    been saved before processing the transcript.

    Args:
        source_type: Type of source ('youtube', 'fireflies', 'zoom', etc.)
        external_id: External identifier (youtube_id, meeting_id, etc.)

    Returns:
        {"exists": bool, "transcript_id": str | null}

    Raises:
        401: Not authenticated
    """
    transcript_service = get_transcript_service()

    # Try to get transcript by listing with filters
    result = await transcript_service.list_transcripts(
        user_id=user_id,
        source_type=source_type,
        limit=1
    )

    if result.get("success") and result.get("transcripts"):
        # Filter for matching external_id
        for t in result["transcripts"]:
            if t.get("external_id") == external_id:
                return {
                    "exists": True,
                    "transcript_id": str(t["id"]),
                    "title": t.get("title")
                }

    return {
        "exists": False,
        "transcript_id": None
    }
