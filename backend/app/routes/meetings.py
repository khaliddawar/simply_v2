"""
Meeting Routes - API endpoints for meeting transcript management
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query

from app.routes.auth import get_current_user_id
from app.services.meeting_service import get_meeting_service
from app.services.database_service import get_database_service
from app.models.meeting import (
    MeetingCreate,
    MeetingResponse,
    MeetingWithTranscript,
    MeetingListResponse,
    MeetingSource
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=MeetingResponse)
async def create_meeting(
    meeting_data: MeetingCreate,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create a new meeting transcript manually.

    This endpoint is for manually adding meeting transcripts.
    For automated ingestion, use the webhook endpoints.
    """
    meeting_service = get_meeting_service()
    db = await get_database_service()
    meeting_service.set_database(db)

    result = await meeting_service.create_meeting(
        user_id=user_id,
        title=meeting_data.title,
        transcript=meeting_data.transcript,
        source=meeting_data.source.value,
        subject=meeting_data.subject,
        meeting_date=meeting_data.meeting_date,
        duration_minutes=meeting_data.duration_minutes,
        participants=meeting_data.participants,
        group_id=meeting_data.group_id
    )

    if not result.get("success"):
        if result.get("error") == "duplicate":
            raise HTTPException(
                status_code=409,
                detail="Meeting already exists"
            )
        raise HTTPException(
            status_code=500,
            detail=result.get("message", "Failed to create meeting")
        )

    return MeetingResponse(**result["meeting"])


@router.get("", response_model=MeetingListResponse)
async def list_meetings(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    group_id: Optional[str] = None,
    source: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """
    List meeting transcripts for the current user.

    Supports filtering by group and source (fireflies, zoom, manual).
    """
    meeting_service = get_meeting_service()
    db = await get_database_service()
    meeting_service.set_database(db)

    result = await meeting_service.list_meetings(
        user_id=user_id,
        group_id=group_id,
        source=source,
        page=page,
        per_page=per_page
    )

    return MeetingListResponse(
        meetings=[MeetingResponse(**m) for m in result["meetings"]],
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        has_more=result["has_more"]
    )


@router.get("/{meeting_id}", response_model=MeetingWithTranscript)
async def get_meeting(
    meeting_id: str,
    include_transcript: bool = Query(False),
    user_id: str = Depends(get_current_user_id)
):
    """Get a specific meeting by ID"""
    meeting_service = get_meeting_service()
    db = await get_database_service()
    meeting_service.set_database(db)

    meeting = await meeting_service.get_meeting(
        meeting_id=meeting_id,
        user_id=user_id,
        include_transcript=include_transcript
    )

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return MeetingWithTranscript(**meeting)


@router.delete("/{meeting_id}")
async def delete_meeting(
    meeting_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Delete a meeting transcript"""
    meeting_service = get_meeting_service()
    db = await get_database_service()
    meeting_service.set_database(db)

    # Check meeting exists
    meeting = await meeting_service.get_meeting(meeting_id, user_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    await meeting_service.delete_meeting(meeting_id, user_id)

    return {"success": True, "message": "Meeting deleted"}


@router.patch("/{meeting_id}/group")
async def move_meeting_to_group(
    meeting_id: str,
    group_id: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """Move a meeting to a different group (or remove from group if group_id is null)"""
    meeting_service = get_meeting_service()
    db = await get_database_service()
    meeting_service.set_database(db)

    # Check meeting exists
    meeting = await meeting_service.get_meeting(meeting_id, user_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Verify group exists if provided
    if group_id:
        group = await db.get_group(group_id, user_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

    await meeting_service.move_to_group(meeting_id, user_id, group_id)

    return {"success": True, "message": "Meeting moved to group"}


@router.put("/{meeting_id}/transcript")
async def update_meeting_transcript(
    meeting_id: str,
    transcript: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Update a meeting's transcript.

    Useful for:
    - Adding transcript when it becomes available (e.g., Zoom async processing)
    - Correcting/editing transcript content
    """
    meeting_service = get_meeting_service()
    db = await get_database_service()
    meeting_service.set_database(db)

    result = await meeting_service.update_transcript(
        meeting_id=meeting_id,
        user_id=user_id,
        transcript=transcript
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=404 if result.get("error") == "Meeting not found" else 500,
            detail=result.get("error", "Failed to update transcript")
        )

    return {"success": True, "meeting": result["meeting"]}


@router.get("/stats/summary")
async def get_meeting_stats(
    user_id: str = Depends(get_current_user_id)
):
    """Get summary statistics for user's meetings"""
    db = await get_database_service()

    # Get counts by source
    result = await db.list_meetings(user_id=user_id, limit=1000)

    stats = {
        "total_meetings": result["total"],
        "by_source": {},
        "with_summaries": 0
    }

    for meeting in result["meetings"]:
        source = meeting.get("source", "unknown")
        stats["by_source"][source] = stats["by_source"].get(source, 0) + 1
        if meeting.get("has_summary"):
            stats["with_summaries"] += 1

    return stats
