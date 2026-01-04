"""
Video Routes
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from app.models.video import (
    VideoCreate, VideoResponse, VideoWithTranscript,
    VideoListResponse, MoveVideoRequest, VideoSummaryResponse,
    EmailSummaryRequest, EmailSummaryResponse
)
from app.services.video_service import get_video_service
from app.services.summarization_service import get_summarization_service
from app.services.email_service import get_email_service
from app.routes.auth import get_current_user_id_optional

router = APIRouter()


@router.post("", response_model=VideoResponse)
async def create_video(
    video_data: VideoCreate,
    user_id: str = Depends(get_current_user_id_optional)
):
    """
    Add a new video with transcript to the library.

    This will:
    1. Upload the transcript to Pinecone Assistant
    2. Store video metadata in the database
    """
    video_service = get_video_service()

    result = await video_service.create_video(
        user_id=user_id,
        youtube_id=video_data.youtube_id,
        title=video_data.title,
        transcript=video_data.transcript,
        channel_name=video_data.channel_name,
        duration_seconds=video_data.duration_seconds,
        thumbnail_url=video_data.thumbnail_url,
        group_id=video_data.group_id
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return VideoResponse(**result["video"])


@router.get("", response_model=VideoListResponse)
async def list_videos(
    user_id: str = Depends(get_current_user_id_optional),
    group_id: Optional[str] = Query(None, description="Filter by group"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort order")
):
    """
    List all videos in the user's library.

    Supports pagination, filtering by group, and sorting.
    """
    video_service = get_video_service()

    result = await video_service.list_videos(
        user_id=user_id,
        group_id=group_id,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_order=sort_order
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return VideoListResponse(
        videos=result["videos"],
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        has_more=result["has_more"]
    )


@router.get("/debug/auth")
async def debug_auth(user_id: str = Depends(get_current_user_id_optional)):
    """
    Debug endpoint to show current user ID and video count.
    Helps diagnose authentication/data mismatches.
    """
    video_service = get_video_service()
    result = await video_service.list_videos(user_id=user_id, page=1, per_page=1)
    return {
        "authenticated_user_id": user_id,
        "video_count": result.get("total", 0),
        "message": "If video_count is 0 but you saved videos, your user_id may differ between extension and dashboard"
    }


@router.get("/{video_id}", response_model=VideoWithTranscript)
async def get_video(
    video_id: str,
    user_id: str = Depends(get_current_user_id_optional),
    include_transcript: bool = Query(False, description="Include transcript content")
):
    """
    Get a specific video by ID.
    """
    video_service = get_video_service()

    result = await video_service.get_video(
        user_id=user_id,
        video_id=video_id,
        include_transcript=include_transcript
    )

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))

    return VideoWithTranscript(**result["video"])


@router.delete("/{video_id}")
async def delete_video(
    video_id: str,
    user_id: str = Depends(get_current_user_id_optional)
):
    """
    Delete a video from the library.

    This removes the video from both the database and Pinecone.
    """
    video_service = get_video_service()

    result = await video_service.delete_video(
        user_id=user_id,
        video_id=video_id
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return {"message": "Video deleted successfully"}


@router.put("/{video_id}/group")
async def move_video(
    video_id: str,
    request: MoveVideoRequest,
    user_id: str = Depends(get_current_user_id_optional)
):
    """
    Move a video to a different group.

    Set group_id to null to remove from any group.
    """
    video_service = get_video_service()

    result = await video_service.move_video_to_group(
        user_id=user_id,
        video_id=video_id,
        group_id=request.group_id
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return {"message": "Video moved successfully"}


@router.get("/{video_id}/summary", response_model=VideoSummaryResponse)
async def get_video_summary(
    video_id: str,
    user_id: str = Depends(get_current_user_id_optional)
):
    """
    Generate a structured summary for a video using Topic Detection + Chain of Density.

    This endpoint:
    1. Detects topic sections in the transcript
    2. Applies Chain of Density summarization to each section
    3. Generates an executive summary with key takeaways

    Note: This is a compute-intensive operation that makes multiple LLM calls.
    """
    video_service = get_video_service()
    summarization_service = get_summarization_service()

    # Check if summarization service is available
    if not summarization_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Summarization service not available - OpenAI API key not configured"
        )

    # Get video with transcript
    result = await video_service.get_video(
        user_id=user_id,
        video_id=video_id,
        include_transcript=True
    )

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))

    video = result["video"]
    transcript = video.get("transcript")

    if not transcript:
        raise HTTPException(
            status_code=400,
            detail="No transcript available for this video"
        )

    # Generate summary
    summary_result = await summarization_service.generate_summary(
        transcript=transcript,
        video_title=video.get("title", "Untitled Video"),
        video_id=video_id
    )

    if not summary_result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=summary_result.get("error", "Failed to generate summary")
        )

    return VideoSummaryResponse(**summary_result)


@router.post("/{video_id}/email-summary", response_model=EmailSummaryResponse)
async def email_video_summary(
    video_id: str,
    request: EmailSummaryRequest,
    user_id: str = Depends(get_current_user_id_optional)
):
    """
    Send a video summary via email.

    This endpoint sends the provided summary HTML to the specified email address
    using the Postmark email service.
    """
    email_service = get_email_service()
    video_service = get_video_service()

    # Check if email service is available
    if not email_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email service not available - Postmark API key not configured"
        )

    # Get video metadata
    result = await video_service.get_video(
        user_id=user_id,
        video_id=video_id,
        include_transcript=False
    )

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))

    video = result["video"]

    # Send email
    email_result = await email_service.send_summary_email(
        recipient_email=request.recipient_email,
        video_title=request.video_title or video.get("title", "Video Summary"),
        summary_html=request.summary_html,
        video_id=video.get("youtube_id"),
        channel_name=request.channel_name or video.get("channel_name"),
        duration_seconds=request.duration_seconds or video.get("duration_seconds"),
        transcript_length=request.transcript_length or video.get("transcript_length")
    )

    if not email_result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=email_result.get("error", "Failed to send email")
        )

    return EmailSummaryResponse(**email_result)
