"""
Video Service

Handles video operations including:
- Creating videos (storing metadata + uploading to Pinecone)
- CRUD operations for videos
- Group management for videos
"""
import logging
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import datetime

from .pinecone_service import get_pinecone_service

if TYPE_CHECKING:
    from app.services.database_service import DatabaseService

logger = logging.getLogger(__name__)


class VideoService:
    """Service for video operations"""

    def __init__(self):
        """Initialize Video service"""
        self.pinecone = get_pinecone_service()
        self.db: Optional["DatabaseService"] = None

        logger.info("Video service initialized")

    def set_database(self, db: "DatabaseService"):
        """Inject database service"""
        self.db = db
        logger.info("Database service injected into Video service")

    async def create_video(
        self,
        user_id: str,
        youtube_id: str,
        title: str,
        transcript: str,
        channel_name: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        thumbnail_url: Optional[str] = None,
        group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new video entry.

        This method:
        1. Validates the input
        2. Uploads transcript to Pinecone
        3. Stores metadata in PostgreSQL

        Args:
            user_id: User's unique ID
            youtube_id: YouTube video ID
            title: Video title
            transcript: Full transcript text
            channel_name: Optional YouTube channel name
            duration_seconds: Optional video duration
            thumbnail_url: Optional thumbnail URL
            group_id: Optional group to add video to

        Returns:
            Dict with video data if successful
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            # Check if video already exists for this user
            existing = await self.db.get_video_by_youtube_id(user_id, youtube_id)
            if existing:
                logger.info(f"Video {youtube_id} already exists for user {user_id}")
                return {
                    "success": True,
                    "video": existing,
                    "already_exists": True,
                    "message": "This video is already in your library"
                }

            # Prepare metadata for Pinecone
            metadata = {
                "channel_name": channel_name,
                "duration_seconds": duration_seconds,
                "group_id": group_id
            }

            # Upload transcript to Pinecone (if initialized)
            pinecone_file_id = None
            if self.pinecone.is_initialized():
                pinecone_result = await self.pinecone.upload_transcript(
                    user_id=user_id,
                    video_id=youtube_id,
                    title=title,
                    transcript=transcript,
                    metadata=metadata
                )

                if not pinecone_result.get("success"):
                    logger.warning(f"Failed to upload to Pinecone: {pinecone_result.get('error')}")
                else:
                    pinecone_file_id = pinecone_result.get("file_id")

            # Create video in database (store transcript for summarization)
            video = await self.db.create_video(
                user_id=user_id,
                youtube_id=youtube_id,
                title=title,
                channel_name=channel_name,
                duration_seconds=duration_seconds,
                thumbnail_url=thumbnail_url,
                pinecone_file_id=pinecone_file_id,
                transcript_length=len(transcript),
                transcript=transcript,
                group_id=group_id
            )

            logger.info(f"Created video {video['id']} for user {user_id}")

            return {
                "success": True,
                "video": video
            }

        except Exception as e:
            logger.error(f"Error creating video: {e}")
            return {"success": False, "error": str(e)}

    async def get_video(
        self,
        user_id: str,
        video_id: str,
        include_transcript: bool = False
    ) -> Dict[str, Any]:
        """
        Get video by ID.

        Args:
            user_id: User's unique ID
            video_id: Video ID (internal UUID)
            include_transcript: Whether to include transcript content

        Returns:
            Dict with video data
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            video = await self.db.get_video(
                video_id, user_id, include_transcript=include_transcript
            )

            if not video:
                return {"success": False, "error": "Video not found"}

            return {
                "success": True,
                "video": video
            }

        except Exception as e:
            logger.error(f"Error getting video: {e}")
            return {"success": False, "error": str(e)}

    async def list_videos(
        self,
        user_id: str,
        group_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """
        List videos for a user.

        Args:
            user_id: User's unique ID
            group_id: Optional group filter
            page: Page number (1-indexed)
            per_page: Items per page
            sort_by: Field to sort by
            sort_order: Sort order (asc/desc)

        Returns:
            Dict with video list and pagination info
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            logger.info(f"🔍 LIST_VIDEOS called - user_id: {user_id}, group_id: {group_id}")

            result = await self.db.list_videos(
                user_id=user_id,
                group_id=group_id,
                offset=(page - 1) * per_page,
                limit=per_page
            )

            logger.info(f"📊 LIST_VIDEOS result - user_id: {user_id}, total: {result['total']}, videos_returned: {len(result['videos'])}")

            return {
                "success": True,
                "videos": result["videos"],
                "total": result["total"],
                "page": page,
                "per_page": per_page,
                "has_more": (page * per_page) < result["total"]
            }

        except Exception as e:
            logger.error(f"Error listing videos: {e}")
            return {"success": False, "error": str(e)}

    async def delete_video(self, user_id: str, video_id: str) -> Dict[str, Any]:
        """
        Delete a video.

        This method:
        1. Gets video from database
        2. Deletes from Pinecone
        3. Deletes from database

        Args:
            user_id: User's unique ID
            video_id: Video ID

        Returns:
            Dict with success status
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            # Get video from database
            video = await self.db.get_video(video_id, user_id)

            if not video:
                return {"success": False, "error": "Video not found"}

            # Delete from Pinecone if file_id exists
            if video.get("pinecone_file_id") and self.pinecone.is_initialized():
                await self.pinecone.delete_file(video["pinecone_file_id"])

            # Delete from database
            await self.db.delete_video(video_id, user_id)

            logger.info(f"Deleted video {video_id} for user {user_id}")

            return {"success": True}

        except Exception as e:
            logger.error(f"Error deleting video: {e}")
            return {"success": False, "error": str(e)}

    async def move_video_to_group(
        self,
        user_id: str,
        video_id: str,
        group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Move a video to a different group.

        Args:
            user_id: User's unique ID
            video_id: Video ID
            group_id: Target group ID (None to remove from group)

        Returns:
            Dict with success status
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            # Verify video exists and user owns it
            video = await self.db.get_video(video_id, user_id)
            if not video:
                return {"success": False, "error": "Video not found"}

            # Verify group exists if provided
            if group_id:
                group = await self.db.get_group(group_id, user_id)
                if not group:
                    return {"success": False, "error": "Group not found"}

            # Update video's group
            await self.db.update_video_group(video_id, user_id, group_id)

            logger.info(f"Moved video {video_id} to group {group_id}")

            return {"success": True}

        except Exception as e:
            logger.error(f"Error moving video to group: {e}")
            return {"success": False, "error": str(e)}

    async def update_video_pinecone_id(
        self,
        video_id: str,
        pinecone_file_id: str
    ) -> Dict[str, Any]:
        """
        Update a video's Pinecone file ID.
        Used when re-uploading transcripts to Pinecone.
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            await self.db.update_video_pinecone_id(video_id, pinecone_file_id)
            return {"success": True}
        except Exception as e:
            logger.error(f"Error updating Pinecone file ID: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance
_video_service: Optional[VideoService] = None


def get_video_service() -> VideoService:
    """Get or create Video service singleton"""
    global _video_service
    if _video_service is None:
        _video_service = VideoService()
    return _video_service
