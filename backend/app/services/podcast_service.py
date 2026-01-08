"""
Podcast Service - Business logic for podcast transcript operations
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.services.database_service import DatabaseService
from app.services.pinecone_service import PineconeService, get_pinecone_service

logger = logging.getLogger(__name__)


class PodcastService:
    """Service for podcast transcript operations"""

    def __init__(self):
        self.db: Optional[DatabaseService] = None
        self.pinecone: Optional[PineconeService] = None

    def set_database(self, db: DatabaseService):
        """Set database service instance"""
        self.db = db

    def set_pinecone(self, pinecone: PineconeService):
        """Set Pinecone service instance"""
        self.pinecone = pinecone

    async def create_podcast(
        self,
        user_id: str,
        title: str,
        transcript: str,
        source: str = "manual",
        external_id: Optional[str] = None,
        subject: Optional[str] = None,
        organizer_email: Optional[str] = None,
        podcast_date: Optional[datetime] = None,
        duration_minutes: Optional[int] = None,
        participants: Optional[List[str]] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
        group_id: Optional[str] = None,
        upload_to_pinecone: bool = True
    ) -> Dict[str, Any]:
        """
        Create a new podcast transcript.

        Args:
            user_id: Owner's user ID
            title: Podcast title
            transcript: Full transcript text
            source: Source of transcript ('fireflies', 'zoom', 'manual')
            external_id: External podcast ID (from source platform)
            subject: Podcast subject/topic
            organizer_email: Organizer's email
            podcast_date: When the podcast occurred
            duration_minutes: Podcast duration
            participants: List of participant names/emails
            source_metadata: Additional source-specific data
            group_id: Optional group to organize podcast into
            upload_to_pinecone: Whether to upload to Pinecone for RAG

        Returns:
            Created podcast data
        """
        if not self.db:
            raise RuntimeError("Database service not configured")

        # Check for duplicate if external_id provided
        if external_id:
            existing = await self.db.get_podcast_by_external_id(
                user_id=user_id,
                external_id=external_id,
                source=source
            )
            if existing:
                logger.info(f"Podcast with external_id {external_id} already exists")
                return {
                    "success": False,
                    "error": "duplicate",
                    "message": "Podcast already exists",
                    "podcast": existing
                }

        # Create podcast record
        podcast = await self.db.create_podcast(
            user_id=user_id,
            title=title,
            source=source,
            external_id=external_id,
            subject=subject,
            organizer_email=organizer_email,
            podcast_date=podcast_date,
            duration_minutes=duration_minutes,
            participants=participants or [],
            transcript=transcript,
            source_metadata=source_metadata,
            group_id=group_id
        )

        # Upload to Pinecone for RAG search
        if upload_to_pinecone and transcript:
            try:
                pinecone = self.pinecone or get_pinecone_service()
                if pinecone.is_initialized():
                    pinecone_result = await self._upload_to_pinecone(
                        podcast_id=podcast["id"],
                        user_id=user_id,
                        title=title,
                        subject=subject,
                        podcast_date=podcast_date,
                        participants=participants or [],
                        transcript=transcript,
                        source=source
                    )
                    if pinecone_result:
                        await self.db.update_podcast_pinecone_id(
                            podcast["id"],
                            pinecone_result
                        )
                        podcast["pinecone_file_id"] = pinecone_result
            except Exception as e:
                logger.error(f"Failed to upload podcast to Pinecone: {e}")
                # Podcast is still created, just not searchable via RAG

        return {
            "success": True,
            "podcast": podcast
        }

    async def _upload_to_pinecone(
        self,
        podcast_id: str,
        user_id: str,
        title: str,
        subject: Optional[str],
        podcast_date: Optional[datetime],
        participants: List[str],
        transcript: str,
        source: str
    ) -> Optional[str]:
        """Upload podcast transcript to Pinecone"""
        pinecone = self.pinecone or get_pinecone_service()

        date_str = podcast_date.strftime("%Y-%m-%d %H:%M") if podcast_date else "Unknown date"
        participants_str = ", ".join(participants) if participants else "Unknown participants"

        enhanced_transcript = f"""## Podcast Information
- **Subject:** {subject or title}
- **Date:** {date_str}
- **Source:** {source.capitalize()}
- **Participants:** {participants_str}

## Transcript

{transcript}
"""

        result = await pinecone.upload_transcript(
            user_id=user_id,
            video_id=f"podcast_{podcast_id}",
            title=title,
            transcript=enhanced_transcript,
            metadata={
                "type": "podcast",
                "source": source,
                "podcast_id": podcast_id,
                "subject": subject,
                "podcast_date": date_str,
                "participants": participants_str
            }
        )

        if result.get("success"):
            return result.get("file_id")
        return None

    async def get_podcast(
        self,
        podcast_id: str,
        user_id: str,
        include_transcript: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Get a podcast by ID"""
        if not self.db:
            raise RuntimeError("Database service not configured")

        return await self.db.get_podcast(
            podcast_id=podcast_id,
            user_id=user_id,
            include_transcript=include_transcript
        )

    async def list_podcasts(
        self,
        user_id: str,
        group_id: Optional[str] = None,
        source: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> Dict[str, Any]:
        """List podcasts for a user with pagination"""
        if not self.db:
            raise RuntimeError("Database service not configured")

        offset = (page - 1) * per_page
        result = await self.db.list_podcasts(
            user_id=user_id,
            group_id=group_id,
            source=source,
            offset=offset,
            limit=per_page
        )

        return {
            "podcasts": result["podcasts"],
            "total": result["total"],
            "page": page,
            "per_page": per_page,
            "has_more": offset + len(result["podcasts"]) < result["total"]
        }

    async def delete_podcast(
        self,
        podcast_id: str,
        user_id: str
    ) -> bool:
        """Delete a podcast and its Pinecone file"""
        if not self.db:
            raise RuntimeError("Database service not configured")

        # Get podcast to find Pinecone file ID
        podcast = await self.db.get_podcast(podcast_id, user_id)
        if not podcast:
            return False

        # Delete from Pinecone if uploaded
        if podcast.get("pinecone_file_id"):
            try:
                pinecone = self.pinecone or get_pinecone_service()
                await pinecone.delete_file(podcast["pinecone_file_id"])
            except Exception as e:
                logger.warning(f"Failed to delete Pinecone file: {e}")

        # Delete from database
        return await self.db.delete_podcast(podcast_id, user_id)

    async def move_to_group(
        self,
        podcast_id: str,
        user_id: str,
        group_id: Optional[str]
    ) -> bool:
        """Move podcast to a different group"""
        if not self.db:
            raise RuntimeError("Database service not configured")

        return await self.db.update_podcast_group(podcast_id, user_id, group_id)

    async def update_transcript(
        self,
        podcast_id: str,
        user_id: str,
        transcript: str,
        re_upload_to_pinecone: bool = True
    ) -> Dict[str, Any]:
        """
        Update a podcast's transcript (e.g., when Zoom transcript becomes available).

        Args:
            podcast_id: Podcast ID
            user_id: User ID for ownership verification
            transcript: New transcript text
            re_upload_to_pinecone: Whether to re-upload to Pinecone

        Returns:
            Updated podcast data
        """
        if not self.db:
            raise RuntimeError("Database service not configured")

        # Get existing podcast
        podcast = await self.db.get_podcast(podcast_id, user_id, include_transcript=True)
        if not podcast:
            return {"success": False, "error": "Podcast not found"}

        # Update transcript in database
        async with self.db.get_session() as session:
            from sqlalchemy import update
            from app.services.database_service import PodcastModel
            import uuid

            await session.execute(
                update(PodcastModel)
                .where(
                    PodcastModel.id == uuid.UUID(podcast_id),
                    PodcastModel.user_id == uuid.UUID(user_id)
                )
                .values(
                    transcript=transcript,
                    transcript_length=len(transcript),
                    updated_at=datetime.utcnow()
                )
            )

        # Re-upload to Pinecone
        if re_upload_to_pinecone:
            try:
                pinecone = self.pinecone or get_pinecone_service()

                # Delete old file if exists
                if podcast.get("pinecone_file_id"):
                    try:
                        await pinecone.delete_file(podcast["pinecone_file_id"])
                    except Exception:
                        pass

                # Upload new version
                new_file_id = await self._upload_to_pinecone(
                    podcast_id=podcast_id,
                    user_id=user_id,
                    title=podcast["title"],
                    subject=podcast.get("subject"),
                    podcast_date=podcast.get("podcast_date"),
                    participants=podcast.get("participants", []),
                    transcript=transcript,
                    source=podcast["source"]
                )

                if new_file_id:
                    await self.db.update_podcast_pinecone_id(podcast_id, new_file_id)

            except Exception as e:
                logger.error(f"Failed to re-upload transcript to Pinecone: {e}")

        # Get updated podcast
        updated = await self.db.get_podcast(podcast_id, user_id)
        return {"success": True, "podcast": updated}


# =============================================================================
# Singleton Instance
# =============================================================================

_podcast_service: Optional[PodcastService] = None


def get_podcast_service() -> PodcastService:
    """Get or create podcast service singleton"""
    global _podcast_service
    if _podcast_service is None:
        _podcast_service = PodcastService()
    return _podcast_service
