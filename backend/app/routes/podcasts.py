"""
Podcast Routes - API endpoints for podcast transcript management
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query

from app.routes.auth import get_current_user_id
from app.services.podcast_service import get_podcast_service
from app.services.database_service import get_database_service
from app.services.summarization_service import get_summarization_service
from app.models.podcast import (
    PodcastCreate,
    PodcastResponse,
    PodcastWithTranscript,
    PodcastListResponse,
    PodcastSource,
    PodcastSummaryResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=PodcastResponse)
async def create_podcast(
    podcast_data: PodcastCreate,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create a new podcast transcript manually.

    This endpoint is for manually adding podcast transcripts.
    For automated ingestion, use the webhook endpoints.
    """
    podcast_service = get_podcast_service()
    db = await get_database_service()
    podcast_service.set_database(db)

    result = await podcast_service.create_podcast(
        user_id=user_id,
        title=podcast_data.title,
        transcript=podcast_data.transcript,
        source=podcast_data.source.value,
        subject=podcast_data.subject,
        podcast_date=podcast_data.podcast_date,
        duration_minutes=podcast_data.duration_minutes,
        participants=podcast_data.participants,
        group_id=podcast_data.group_id
    )

    if not result.get("success"):
        if result.get("error") == "duplicate":
            raise HTTPException(
                status_code=409,
                detail="Podcast already exists"
            )
        raise HTTPException(
            status_code=500,
            detail=result.get("message", "Failed to create podcast")
        )

    return PodcastResponse(**result["podcast"])


@router.get("", response_model=PodcastListResponse)
async def list_podcasts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    group_id: Optional[str] = None,
    source: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """
    List podcast transcripts for the current user.

    Supports filtering by group and source (fireflies, zoom, manual).
    """
    podcast_service = get_podcast_service()
    db = await get_database_service()
    podcast_service.set_database(db)

    result = await podcast_service.list_podcasts(
        user_id=user_id,
        group_id=group_id,
        source=source,
        page=page,
        per_page=per_page
    )

    return PodcastListResponse(
        podcasts=[PodcastResponse(**m) for m in result["podcasts"]],
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        has_more=result["has_more"]
    )


@router.get("/{podcast_id}", response_model=PodcastWithTranscript)
async def get_podcast(
    podcast_id: str,
    include_transcript: bool = Query(False),
    user_id: str = Depends(get_current_user_id)
):
    """Get a specific podcast by ID"""
    podcast_service = get_podcast_service()
    db = await get_database_service()
    podcast_service.set_database(db)

    podcast = await podcast_service.get_podcast(
        podcast_id=podcast_id,
        user_id=user_id,
        include_transcript=include_transcript
    )

    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    return PodcastWithTranscript(**podcast)


@router.delete("/{podcast_id}")
async def delete_podcast(
    podcast_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Delete a podcast transcript"""
    podcast_service = get_podcast_service()
    db = await get_database_service()
    podcast_service.set_database(db)

    # Check podcast exists
    podcast = await podcast_service.get_podcast(podcast_id, user_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    await podcast_service.delete_podcast(podcast_id, user_id)

    return {"success": True, "message": "Podcast deleted"}


@router.patch("/{podcast_id}/group")
async def move_podcast_to_group(
    podcast_id: str,
    group_id: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """Move a podcast to a different group (or remove from group if group_id is null)"""
    podcast_service = get_podcast_service()
    db = await get_database_service()
    podcast_service.set_database(db)

    # Check podcast exists
    podcast = await podcast_service.get_podcast(podcast_id, user_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    # Verify group exists if provided
    if group_id:
        group = await db.get_group(group_id, user_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

    await podcast_service.move_to_group(podcast_id, user_id, group_id)

    return {"success": True, "message": "Podcast moved to group"}


@router.put("/{podcast_id}/transcript")
async def update_podcast_transcript(
    podcast_id: str,
    transcript: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Update a podcast's transcript.

    Useful for:
    - Adding transcript when it becomes available (e.g., Zoom async processing)
    - Correcting/editing transcript content
    """
    podcast_service = get_podcast_service()
    db = await get_database_service()
    podcast_service.set_database(db)

    result = await podcast_service.update_transcript(
        podcast_id=podcast_id,
        user_id=user_id,
        transcript=transcript
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=404 if result.get("error") == "Podcast not found" else 500,
            detail=result.get("error", "Failed to update transcript")
        )

    return {"success": True, "podcast": result["podcast"]}


@router.get("/{podcast_id}/summary", response_model=PodcastSummaryResponse)
async def get_podcast_summary(
    podcast_id: str,
    user_id: str = Depends(get_current_user_id),
    force_regenerate: bool = Query(
        False,
        description="Force regeneration of summary even if cached version exists"
    )
):
    """
    Get or generate a structured summary for a podcast.

    Summary Caching:
    - Summaries are cached after first generation to avoid repeated LLM calls
    - Use force_regenerate=true to regenerate and update the cached summary
    - Cached summaries are returned instantly without any LLM calls

    Generation Process (when not cached or force_regenerate=true):
    - Analyzes the transcript to extract key information
    - Generates executive summary, key takeaways, action items, decisions, and topics
    """
    db = await get_database_service()
    podcast_service = get_podcast_service()
    podcast_service.set_database(db)
    summarization_service = get_summarization_service()

    # Check for cached summary first (unless force_regenerate)
    if not force_regenerate:
        cached = await db.get_podcast_summary(podcast_id=podcast_id, user_id=user_id)
        if cached and cached.get("summary_data"):
            logger.info(f"Returning cached summary for podcast {podcast_id}")
            summary_data = cached["summary_data"]
            # Add cache metadata to response
            summary_data["cached"] = True
            summary_data["cached_at"] = cached.get("summary_generated_at").isoformat() if cached.get("summary_generated_at") else None
            return PodcastSummaryResponse(**summary_data)

    # Check if summarization service is available for fresh generation
    if not summarization_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Summarization service not available - OpenAI API key not configured"
        )

    # Get podcast with transcript
    podcast = await podcast_service.get_podcast(
        podcast_id=podcast_id,
        user_id=user_id,
        include_transcript=True
    )

    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    transcript = podcast.get("transcript")

    if not transcript:
        raise HTTPException(
            status_code=400,
            detail="No transcript available for this podcast"
        )

    # Generate fresh summary
    logger.info(f"Generating fresh summary for podcast {podcast_id} (force_regenerate={force_regenerate})")

    # Format podcast_date for the summary
    podcast_date_str = None
    if podcast.get("podcast_date"):
        podcast_date_str = podcast["podcast_date"].strftime("%Y-%m-%d") if hasattr(podcast["podcast_date"], 'strftime') else str(podcast["podcast_date"])

    summary_result = await summarization_service.generate_podcast_summary(
        transcript=transcript,
        podcast_title=podcast.get("title", "Untitled Podcast"),
        podcast_id=podcast_id,
        podcast_subject=podcast.get("subject"),
        podcast_date=podcast_date_str,
        participants=podcast.get("participants")
    )

    if not summary_result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=summary_result.get("error", "Failed to generate summary")
        )

    # Cache the generated summary
    try:
        await db.save_podcast_summary(
            podcast_id=podcast_id,
            user_id=user_id,
            summary_data=summary_result
        )
        logger.info(f"Cached summary for podcast {podcast_id}")
    except Exception as e:
        # Log but don't fail - summary generation succeeded
        logger.warning(f"Failed to cache summary for podcast {podcast_id}: {e}")

    # Mark as freshly generated (not from cache)
    summary_result["cached"] = False

    return PodcastSummaryResponse(**summary_result)


@router.get("/stats/summary")
async def get_podcast_stats(
    user_id: str = Depends(get_current_user_id)
):
    """Get summary statistics for user's podcasts"""
    db = await get_database_service()

    # Get counts by source
    result = await db.list_podcasts(user_id=user_id, limit=1000)

    stats = {
        "total_podcasts": result["total"],
        "by_source": {},
        "with_summaries": 0
    }

    for podcast in result["podcasts"]:
        source = podcast.get("source", "unknown")
        stats["by_source"][source] = stats["by_source"].get(source, 0) + 1
        if podcast.get("has_summary"):
            stats["with_summaries"] += 1

    return stats
