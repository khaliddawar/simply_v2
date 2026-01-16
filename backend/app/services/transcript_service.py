"""
Transcript Service - Unified service for all transcript operations

This service handles transcript operations for all source types (YouTube, Fireflies, Zoom, etc.)
following the unified Transcript Library architecture. It replaces the separate VideoService
and PodcastService for new code paths while maintaining backward compatibility.

Key features:
- Create, read, update, delete transcripts from any source
- Upload to Pinecone for RAG search
- Summary generation with caching
- Group management (move to group / Recent)
- Filtering and sorting by source type, group, etc.
"""
import logging
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import datetime
from enum import Enum

from .pinecone_service import get_pinecone_service, PineconeService
from .summarization_service import get_summarization_service, SummarizationService

if TYPE_CHECKING:
    from app.services.database_service import DatabaseService

logger = logging.getLogger(__name__)


class SourceType(str, Enum):
    """Enum for transcript source types"""
    YOUTUBE = "youtube"
    FIREFLIES = "fireflies"
    ZOOM = "zoom"
    MANUAL = "manual"
    PDF = "pdf"          # Future
    AUDIO = "audio"      # Future
    DOCUMENT = "document"  # Future


class TranscriptService:
    """
    Unified service for all transcript operations.

    Replaces VideoService and PodcastService for new code paths while
    providing a consistent interface for all source types.
    """

    def __init__(self):
        """Initialize Transcript service"""
        self.pinecone: PineconeService = get_pinecone_service()
        self.summarization: SummarizationService = get_summarization_service()
        self.db: Optional["DatabaseService"] = None

        logger.info("Transcript service initialized")

    def set_database(self, db: "DatabaseService"):
        """
        Inject database service.

        This method is called during app startup in main.py to provide
        the database connection.

        Args:
            db: DatabaseService instance
        """
        self.db = db
        logger.info("Database service injected into Transcript service")

    async def create_transcript(
        self,
        user_id: str,
        source_type: str,
        title: str,
        transcript_text: str,
        external_id: Optional[str] = None,
        group_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new transcript from any source.

        This method:
        1. Checks for duplicates using (user_id, source_type, external_id)
        2. Creates the transcript record in the database
        3. Uploads transcript to Pinecone for RAG search
        4. Updates the record with pinecone_file_id

        Args:
            user_id: User's unique ID
            source_type: Type of source ('youtube', 'fireflies', 'zoom', 'manual', etc.)
            title: Transcript title
            transcript_text: Full transcript text
            external_id: External identifier (youtube_id, meeting_id, etc.) for duplicate checking
            group_id: Optional group to add transcript to
            metadata: Source-specific metadata (channel_name, participants, duration, etc.)

        Returns:
            Dict with success status and transcript data:
            - success: True if created successfully
            - transcript: Created transcript dict
            - already_exists: True if duplicate found
            - error: Error message if failed
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        metadata = metadata or {}

        try:
            # Check for duplicates if external_id is provided
            if external_id:
                existing = await self._get_transcript_by_external_id(
                    user_id=user_id,
                    source_type=source_type,
                    external_id=external_id
                )
                if existing:
                    logger.info(f"Transcript {external_id} ({source_type}) already exists for user {user_id}")
                    return {
                        "success": True,
                        "transcript": existing,
                        "already_exists": True,
                        "message": "This transcript is already in your library"
                    }

            # Create transcript in database
            transcript = await self._create_transcript_in_db(
                user_id=user_id,
                source_type=source_type,
                title=title,
                transcript_text=transcript_text,
                external_id=external_id,
                group_id=group_id,
                metadata=metadata
            )

            # Upload to Pinecone for RAG search
            if self.pinecone.is_initialized() and transcript_text:
                pinecone_result = await self._upload_to_pinecone(
                    transcript_id=transcript["id"],
                    user_id=user_id,
                    source_type=source_type,
                    title=title,
                    transcript_text=transcript_text,
                    metadata=metadata
                )

                if pinecone_result.get("success"):
                    pinecone_file_id = pinecone_result.get("file_id")
                    await self._update_transcript_pinecone_id(
                        transcript["id"],
                        pinecone_file_id
                    )
                    transcript["pinecone_file_id"] = pinecone_file_id
                else:
                    logger.warning(f"Failed to upload to Pinecone: {pinecone_result.get('error')}")

            logger.info(f"Created transcript {transcript['id']} ({source_type}) for user {user_id}")

            return {
                "success": True,
                "transcript": transcript
            }

        except Exception as e:
            logger.error(f"Error creating transcript: {e}")
            return {"success": False, "error": str(e)}

    async def list_transcripts(
        self,
        user_id: str,
        group_id: Optional[str] = None,
        source_type: Optional[str] = None,
        ungrouped_only: bool = False,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        List transcripts with filtering and sorting.

        Args:
            user_id: User's unique ID
            group_id: Filter by group ID (mutually exclusive with ungrouped_only)
            source_type: Filter by source type ('youtube', 'fireflies', etc.)
            ungrouped_only: If True, return only transcripts with group_id IS NULL (Recent section)
            sort_by: Field to sort by ('created_at', 'title', 'source_type')
            sort_order: Sort order ('asc', 'desc')
            limit: Maximum number of transcripts to return (default 100)
            offset: Number of transcripts to skip (for pagination)

        Returns:
            Dict with:
            - success: True if query succeeded
            - transcripts: List of transcript dicts
            - total: Total count matching filters (for pagination)
            - error: Error message if failed
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        # Validate sort_by
        valid_sort_fields = ["created_at", "title", "source_type"]
        if sort_by not in valid_sort_fields:
            sort_by = "created_at"

        # Validate sort_order
        if sort_order not in ["asc", "desc"]:
            sort_order = "desc"

        try:
            result = await self._list_transcripts_from_db(
                user_id=user_id,
                group_id=group_id,
                source_type=source_type,
                ungrouped_only=ungrouped_only,
                sort_by=sort_by,
                sort_order=sort_order,
                limit=limit,
                offset=offset
            )

            logger.info(
                f"Listed transcripts for user {user_id}: "
                f"total={result['total']}, returned={len(result['transcripts'])}"
            )

            return {
                "success": True,
                "transcripts": result["transcripts"],
                "total": result["total"]
            }

        except Exception as e:
            logger.error(f"Error listing transcripts: {e}")
            return {"success": False, "error": str(e)}

    async def get_transcript(
        self,
        user_id: str,
        transcript_id: str,
        include_transcript: bool = False,
        include_summary: bool = False
    ) -> Dict[str, Any]:
        """
        Get a single transcript by ID.

        Args:
            user_id: User's unique ID (for ownership verification)
            transcript_id: Transcript ID (UUID)
            include_transcript: If True, include full transcript text in response
            include_summary: If True, include cached summary data in response

        Returns:
            Dict with:
            - success: True if found
            - transcript: Transcript dict
            - error: Error message if not found or failed
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            transcript = await self._get_transcript_from_db(
                user_id=user_id,
                transcript_id=transcript_id,
                include_transcript=include_transcript,
                include_summary=include_summary
            )

            if not transcript:
                return {"success": False, "error": "Transcript not found"}

            return {
                "success": True,
                "transcript": transcript
            }

        except Exception as e:
            logger.error(f"Error getting transcript: {e}")
            return {"success": False, "error": str(e)}

    async def delete_transcript(
        self,
        user_id: str,
        transcript_id: str
    ) -> Dict[str, Any]:
        """
        Delete a transcript and its Pinecone data.

        This method:
        1. Gets transcript from database
        2. Deletes from Pinecone if file_id exists
        3. Deletes from database

        Args:
            user_id: User's unique ID (for ownership verification)
            transcript_id: Transcript ID (UUID)

        Returns:
            Dict with:
            - success: True if deleted successfully
            - error: Error message if not found or failed
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            # Get transcript to find Pinecone file ID
            transcript = await self._get_transcript_from_db(
                user_id=user_id,
                transcript_id=transcript_id,
                include_transcript=False
            )

            if not transcript:
                return {"success": False, "error": "Transcript not found"}

            # Delete from Pinecone if file_id exists
            if transcript.get("pinecone_file_id") and self.pinecone.is_initialized():
                try:
                    await self.pinecone.delete_file(transcript["pinecone_file_id"])
                except Exception as e:
                    logger.warning(f"Failed to delete from Pinecone: {e}")

            # Delete from database
            await self._delete_transcript_from_db(user_id, transcript_id)

            logger.info(f"Deleted transcript {transcript_id} for user {user_id}")

            return {"success": True}

        except Exception as e:
            logger.error(f"Error deleting transcript: {e}")
            return {"success": False, "error": str(e)}

    async def move_to_group(
        self,
        user_id: str,
        transcript_id: str,
        group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Move transcript to a group or back to Recent.

        Args:
            user_id: User's unique ID (for ownership verification)
            transcript_id: Transcript ID (UUID)
            group_id: Target group ID (None = move to Recent / ungrouped)

        Returns:
            Dict with:
            - success: True if moved successfully
            - error: Error message if not found or failed
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            # Verify transcript exists and user owns it
            transcript = await self._get_transcript_from_db(
                user_id=user_id,
                transcript_id=transcript_id
            )
            if not transcript:
                return {"success": False, "error": "Transcript not found"}

            # Verify group exists if provided
            if group_id:
                group = await self.db.get_group(group_id, user_id)
                if not group:
                    return {"success": False, "error": "Group not found"}

            # Update transcript's group
            await self._update_transcript_group(
                transcript_id=transcript_id,
                user_id=user_id,
                group_id=group_id
            )

            logger.info(f"Moved transcript {transcript_id} to group {group_id or 'Recent'}")

            return {"success": True}

        except Exception as e:
            logger.error(f"Error moving transcript to group: {e}")
            return {"success": False, "error": str(e)}

    async def get_summary(
        self,
        user_id: str,
        transcript_id: str,
        force_regenerate: bool = False
    ) -> Dict[str, Any]:
        """
        Get or generate summary for a transcript.

        Returns cached summary if exists and force_regenerate is False.
        Otherwise generates a new summary using summarization_service
        and caches the result in the database.

        Args:
            user_id: User's unique ID (for ownership verification)
            transcript_id: Transcript ID (UUID)
            force_regenerate: If True, regenerate summary even if cached

        Returns:
            Dict with:
            - success: True if summary available/generated
            - summary: Summary data dict (structured summary with sections, key_points, etc.)
            - generated_at: When summary was generated
            - from_cache: True if summary was from cache
            - error: Error message if failed
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            # Get transcript with full text
            transcript = await self._get_transcript_from_db(
                user_id=user_id,
                transcript_id=transcript_id,
                include_transcript=True,
                include_summary=True
            )

            if not transcript:
                return {"success": False, "error": "Transcript not found"}

            # Check for cached summary
            if not force_regenerate and transcript.get("summary_data"):
                return {
                    "success": True,
                    "summary": transcript["summary_data"],
                    "generated_at": transcript.get("summary_generated_at"),
                    "from_cache": True
                }

            # Generate new summary
            transcript_text = transcript.get("transcript_text")
            if not transcript_text:
                return {"success": False, "error": "Transcript text not available"}

            # Use appropriate summarization method based on source type
            source_type = transcript.get("source_type", "youtube")

            if source_type in [SourceType.FIREFLIES.value, SourceType.ZOOM.value]:
                # Use podcast summary for meeting transcripts
                summary_result = await self.summarization.generate_podcast_summary(
                    transcript=transcript_text,
                    podcast_title=transcript.get("title", "Untitled"),
                    podcast_id=transcript_id,
                    podcast_subject=transcript.get("metadata", {}).get("subject"),
                    podcast_date=transcript.get("metadata", {}).get("meeting_date"),
                    participants=transcript.get("metadata", {}).get("participants")
                )
            else:
                # Use video summary for other types
                summary_result = await self.summarization.generate_summary(
                    transcript=transcript_text,
                    video_title=transcript.get("title", "Untitled"),
                    video_id=transcript_id
                )

            if not summary_result.get("success"):
                return {
                    "success": False,
                    "error": summary_result.get("error", "Failed to generate summary")
                }

            # Cache summary in database
            await self._save_transcript_summary(
                transcript_id=transcript_id,
                user_id=user_id,
                summary_data=summary_result
            )

            logger.info(f"Generated and cached summary for transcript {transcript_id}")

            return {
                "success": True,
                "summary": summary_result,
                "generated_at": datetime.utcnow(),
                "from_cache": False
            }

        except Exception as e:
            logger.error(f"Error getting/generating summary: {e}")
            return {"success": False, "error": str(e)}

    async def get_transcript_text(
        self,
        user_id: str,
        transcript_id: str
    ) -> Dict[str, Any]:
        """
        Get just the transcript text for a transcript.

        This is a convenience method that returns only the transcript text,
        useful for cases where you don't need the full transcript metadata.

        Args:
            user_id: User's unique ID (for ownership verification)
            transcript_id: Transcript ID (UUID)

        Returns:
            Dict with:
            - success: True if found
            - transcript_text: The raw transcript text
            - title: Transcript title
            - error: Error message if not found or failed
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            transcript = await self._get_transcript_from_db(
                user_id=user_id,
                transcript_id=transcript_id,
                include_transcript=True
            )

            if not transcript:
                return {"success": False, "error": "Transcript not found"}

            return {
                "success": True,
                "transcript_text": transcript.get("transcript_text"),
                "title": transcript.get("title")
            }

        except Exception as e:
            logger.error(f"Error getting transcript text: {e}")
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Private Helper Methods - Database Operations
    # =========================================================================

    async def _get_transcript_by_external_id(
        self,
        user_id: str,
        source_type: str,
        external_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get transcript by external ID for duplicate checking.

        Uses the unique constraint on (user_id, source_type, external_id).
        Currently delegates to video or podcast service based on source type.

        In the future, this will query the unified transcripts table directly.
        """
        # For now, delegate to existing services based on source_type
        if source_type == SourceType.YOUTUBE.value:
            return await self.db.get_video_by_youtube_id(user_id, external_id)
        elif source_type in [SourceType.FIREFLIES.value, SourceType.ZOOM.value, SourceType.MANUAL.value]:
            return await self.db.get_podcast_by_external_id(user_id, external_id, source_type)

        return None

    async def _create_transcript_in_db(
        self,
        user_id: str,
        source_type: str,
        title: str,
        transcript_text: str,
        external_id: Optional[str],
        group_id: Optional[str],
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create transcript record in database.

        Currently delegates to video or podcast table based on source type.
        In the future, this will create in the unified transcripts table.
        """
        if source_type == SourceType.YOUTUBE.value:
            # Create in videos table
            return await self.db.create_video(
                user_id=user_id,
                youtube_id=external_id or "",
                title=title,
                channel_name=metadata.get("channel_name"),
                duration_seconds=metadata.get("duration_seconds"),
                thumbnail_url=metadata.get("thumbnail_url"),
                pinecone_file_id=None,
                transcript_length=len(transcript_text),
                transcript=transcript_text,
                group_id=group_id
            )
        else:
            # Create in podcasts table
            from datetime import datetime as dt
            podcast_date = metadata.get("meeting_date")
            if isinstance(podcast_date, str):
                try:
                    podcast_date = dt.fromisoformat(podcast_date.replace("Z", "+00:00"))
                except ValueError:
                    podcast_date = None

            return await self.db.create_podcast(
                user_id=user_id,
                title=title,
                source=source_type,
                external_id=external_id,
                subject=metadata.get("subject"),
                organizer_email=metadata.get("organizer_email"),
                podcast_date=podcast_date,
                duration_minutes=metadata.get("duration_minutes"),
                participants=metadata.get("participants"),
                transcript=transcript_text,
                source_metadata=metadata,
                group_id=group_id
            )

    async def _get_transcript_from_db(
        self,
        user_id: str,
        transcript_id: str,
        include_transcript: bool = False,
        include_summary: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Get transcript from database.

        Tries videos table first, then podcasts table.
        Normalizes response to unified format.
        """
        # Try videos table first
        video = await self.db.get_video(
            transcript_id,
            user_id,
            include_transcript=include_transcript
        )
        if video:
            return self._normalize_video_to_transcript(video, include_summary)

        # Try podcasts table
        podcast = await self.db.get_podcast(
            transcript_id,
            user_id,
            include_transcript=include_transcript
        )
        if podcast:
            return self._normalize_podcast_to_transcript(podcast, include_summary)

        return None

    async def _list_transcripts_from_db(
        self,
        user_id: str,
        group_id: Optional[str],
        source_type: Optional[str],
        ungrouped_only: bool,
        sort_by: str,
        sort_order: str,
        limit: int,
        offset: int
    ) -> Dict[str, Any]:
        """
        List transcripts from database.

        Combines results from videos and podcasts tables.
        Applies filtering and sorting across both sources.
        """
        transcripts = []
        total = 0

        # Determine which tables to query based on source_type filter
        include_videos = source_type is None or source_type == SourceType.YOUTUBE.value
        include_podcasts = source_type is None or source_type in [
            SourceType.FIREFLIES.value,
            SourceType.ZOOM.value,
            SourceType.MANUAL.value
        ]

        # Get videos if needed
        if include_videos:
            # Handle ungrouped_only for videos
            video_group_id = None if ungrouped_only else group_id

            # If ungrouped_only, we need to filter for NULL group_id
            # The current DB method doesn't support this directly
            # We'll need to get all and filter client-side for now
            video_result = await self.db.list_videos(
                user_id=user_id,
                group_id=video_group_id,
                offset=0,
                limit=1000  # Get all for now
            )

            videos = video_result.get("videos", [])

            # Filter for ungrouped if needed
            if ungrouped_only:
                videos = [v for v in videos if v.get("group_id") is None]

            # Normalize to transcript format
            for v in videos:
                transcripts.append(self._normalize_video_to_transcript(v))

        # Get podcasts if needed
        if include_podcasts:
            podcast_source = None
            if source_type and source_type != SourceType.YOUTUBE.value:
                podcast_source = source_type

            podcast_result = await self.db.list_podcasts(
                user_id=user_id,
                group_id=group_id if not ungrouped_only else None,
                source=podcast_source,
                offset=0,
                limit=1000  # Get all for now
            )

            podcasts = podcast_result.get("podcasts", [])

            # Filter for ungrouped if needed
            if ungrouped_only:
                podcasts = [p for p in podcasts if p.get("group_id") is None]

            # Normalize to transcript format
            for p in podcasts:
                transcripts.append(self._normalize_podcast_to_transcript(p))

        # Sort combined results
        reverse = sort_order == "desc"
        if sort_by == "title":
            transcripts.sort(key=lambda x: x.get("title", "").lower(), reverse=reverse)
        elif sort_by == "source_type":
            transcripts.sort(key=lambda x: x.get("source_type", ""), reverse=reverse)
        else:  # created_at (default)
            transcripts.sort(
                key=lambda x: x.get("created_at") or datetime.min,
                reverse=reverse
            )

        # Apply pagination
        total = len(transcripts)
        transcripts = transcripts[offset:offset + limit]

        return {
            "transcripts": transcripts,
            "total": total
        }

    async def _delete_transcript_from_db(
        self,
        user_id: str,
        transcript_id: str
    ) -> bool:
        """
        Delete transcript from database.

        Tries videos table first, then podcasts table.
        """
        # Try to delete from videos
        try:
            video = await self.db.get_video(transcript_id, user_id)
            if video:
                await self.db.delete_video(transcript_id, user_id)
                return True
        except Exception:
            pass

        # Try to delete from podcasts
        try:
            podcast = await self.db.get_podcast(transcript_id, user_id)
            if podcast:
                await self.db.delete_podcast(transcript_id, user_id)
                return True
        except Exception:
            pass

        return False

    async def _update_transcript_pinecone_id(
        self,
        transcript_id: str,
        pinecone_file_id: str
    ) -> bool:
        """
        Update transcript's Pinecone file ID.

        Tries videos table first, then podcasts table.
        """
        try:
            await self.db.update_video_pinecone_id(transcript_id, pinecone_file_id)
            return True
        except Exception:
            pass

        try:
            await self.db.update_podcast_pinecone_id(transcript_id, pinecone_file_id)
            return True
        except Exception:
            pass

        return False

    async def _update_transcript_group(
        self,
        transcript_id: str,
        user_id: str,
        group_id: Optional[str]
    ) -> bool:
        """
        Update transcript's group.

        Tries videos table first, then podcasts table.
        """
        try:
            video = await self.db.get_video(transcript_id, user_id)
            if video:
                await self.db.update_video_group(transcript_id, user_id, group_id)
                return True
        except Exception:
            pass

        try:
            podcast = await self.db.get_podcast(transcript_id, user_id)
            if podcast:
                await self.db.update_podcast_group(transcript_id, user_id, group_id)
                return True
        except Exception:
            pass

        return False

    async def _save_transcript_summary(
        self,
        transcript_id: str,
        user_id: str,
        summary_data: Dict[str, Any]
    ) -> bool:
        """
        Save summary to database for caching.

        Tries videos table first, then podcasts table.
        """
        try:
            video = await self.db.get_video(transcript_id, user_id)
            if video:
                await self.db.save_video_summary(transcript_id, user_id, summary_data)
                return True
        except Exception:
            pass

        try:
            podcast = await self.db.get_podcast(transcript_id, user_id)
            if podcast:
                await self.db.save_podcast_summary(transcript_id, user_id, summary_data)
                return True
        except Exception:
            pass

        return False

    # =========================================================================
    # Private Helper Methods - Pinecone Operations
    # =========================================================================

    async def _upload_to_pinecone(
        self,
        transcript_id: str,
        user_id: str,
        source_type: str,
        title: str,
        transcript_text: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Upload transcript to Pinecone for RAG search.

        Creates enhanced content with metadata header and transcript.
        """
        # Build enhanced content based on source type
        if source_type == SourceType.YOUTUBE.value:
            # Standard video format
            content_metadata = {
                "channel_name": metadata.get("channel_name"),
                "duration_seconds": metadata.get("duration_seconds"),
                "group_id": metadata.get("group_id"),
                "youtube_id": metadata.get("youtube_id", metadata.get("external_id"))
            }

            return await self.pinecone.upload_transcript(
                user_id=user_id,
                video_id=transcript_id,
                title=title,
                transcript=transcript_text,
                metadata=content_metadata
            )
        else:
            # Meeting/podcast format - enhance transcript with context
            participants = metadata.get("participants", [])
            participants_str = ", ".join(participants) if participants else "Unknown participants"
            meeting_date = metadata.get("meeting_date", "Unknown date")
            subject = metadata.get("subject", title)

            enhanced_transcript = f"""## Transcript Information
- **Subject:** {subject}
- **Date:** {meeting_date}
- **Source:** {source_type.capitalize()}
- **Participants:** {participants_str}

## Transcript

{transcript_text}
"""

            content_metadata = {
                "type": "transcript",
                "source": source_type,
                "transcript_id": transcript_id,
                "subject": subject,
                "meeting_date": str(meeting_date),
                "participants": participants_str
            }

            return await self.pinecone.upload_transcript(
                user_id=user_id,
                video_id=f"transcript_{transcript_id}",
                title=title,
                transcript=enhanced_transcript,
                metadata=content_metadata
            )

    # =========================================================================
    # Private Helper Methods - Data Normalization
    # =========================================================================

    def _normalize_video_to_transcript(
        self,
        video: Dict[str, Any],
        include_summary: bool = False
    ) -> Dict[str, Any]:
        """
        Normalize video record to unified transcript format.
        """
        result = {
            "id": video.get("id"),
            "user_id": video.get("user_id"),
            "group_id": video.get("group_id"),
            "source_type": SourceType.YOUTUBE.value,
            "external_id": video.get("youtube_id"),
            "title": video.get("title"),
            "transcript_length": video.get("transcript_length"),
            "pinecone_file_id": video.get("pinecone_file_id"),
            "has_summary": video.get("has_summary", False),
            "summary_generated_at": video.get("summary_generated_at"),
            "metadata": {
                "youtube_id": video.get("youtube_id"),
                "channel_name": video.get("channel_name"),
                "duration_seconds": video.get("duration_seconds"),
                "thumbnail_url": video.get("thumbnail_url")
            },
            "created_at": video.get("created_at"),
            "updated_at": video.get("updated_at")
        }

        # Include transcript text if present
        if "transcript" in video:
            result["transcript_text"] = video.get("transcript")

        # Include summary data if requested
        if include_summary and "summary_data" in video:
            result["summary_data"] = video.get("summary_data")

        return result

    def _normalize_podcast_to_transcript(
        self,
        podcast: Dict[str, Any],
        include_summary: bool = False
    ) -> Dict[str, Any]:
        """
        Normalize podcast record to unified transcript format.
        """
        result = {
            "id": podcast.get("id"),
            "user_id": podcast.get("user_id"),
            "group_id": podcast.get("group_id"),
            "source_type": podcast.get("source", SourceType.MANUAL.value),
            "external_id": podcast.get("external_id"),
            "title": podcast.get("title"),
            "transcript_length": podcast.get("transcript_length"),
            "pinecone_file_id": podcast.get("pinecone_file_id"),
            "has_summary": podcast.get("has_summary", False),
            "summary_generated_at": podcast.get("summary_generated_at"),
            "metadata": {
                "subject": podcast.get("subject"),
                "organizer_email": podcast.get("organizer_email"),
                "meeting_date": podcast.get("podcast_date"),
                "duration_minutes": podcast.get("duration_minutes"),
                "participants": podcast.get("participants", []),
                "source_metadata": podcast.get("source_metadata")
            },
            "created_at": podcast.get("created_at"),
            "updated_at": podcast.get("updated_at")
        }

        # Include transcript text if present
        if "transcript" in podcast:
            result["transcript_text"] = podcast.get("transcript")

        # Include summary data if requested
        if include_summary and "summary_data" in podcast:
            result["summary_data"] = podcast.get("summary_data")

        return result


# =============================================================================
# Singleton Instance
# =============================================================================

_transcript_service: Optional[TranscriptService] = None


def get_transcript_service() -> TranscriptService:
    """Get or create Transcript service singleton"""
    global _transcript_service
    if _transcript_service is None:
        _transcript_service = TranscriptService()
    return _transcript_service
