"""
Meeting Service - Business logic for meeting transcript operations
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.services.database_service import DatabaseService
from app.services.pinecone_service import PineconeService, get_pinecone_service

logger = logging.getLogger(__name__)


class MeetingService:
    """Service for meeting transcript operations"""

    def __init__(self):
        self.db: Optional[DatabaseService] = None
        self.pinecone: Optional[PineconeService] = None

    def set_database(self, db: DatabaseService):
        """Set database service instance"""
        self.db = db

    def set_pinecone(self, pinecone: PineconeService):
        """Set Pinecone service instance"""
        self.pinecone = pinecone

    async def create_meeting(
        self,
        user_id: str,
        title: str,
        transcript: str,
        source: str = "manual",
        external_id: Optional[str] = None,
        subject: Optional[str] = None,
        organizer_email: Optional[str] = None,
        meeting_date: Optional[datetime] = None,
        duration_minutes: Optional[int] = None,
        participants: Optional[List[str]] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
        group_id: Optional[str] = None,
        upload_to_pinecone: bool = True
    ) -> Dict[str, Any]:
        """
        Create a new meeting transcript.

        Args:
            user_id: Owner's user ID
            title: Meeting title
            transcript: Full transcript text
            source: Source of transcript ('fireflies', 'zoom', 'manual')
            external_id: External meeting ID (from source platform)
            subject: Meeting subject/topic
            organizer_email: Organizer's email
            meeting_date: When the meeting occurred
            duration_minutes: Meeting duration
            participants: List of participant names/emails
            source_metadata: Additional source-specific data
            group_id: Optional group to organize meeting into
            upload_to_pinecone: Whether to upload to Pinecone for RAG

        Returns:
            Created meeting data
        """
        if not self.db:
            raise RuntimeError("Database service not configured")

        # Check for duplicate if external_id provided
        if external_id:
            existing = await self.db.get_meeting_by_external_id(
                user_id=user_id,
                external_id=external_id,
                source=source
            )
            if existing:
                logger.info(f"Meeting with external_id {external_id} already exists")
                return {
                    "success": False,
                    "error": "duplicate",
                    "message": "Meeting already exists",
                    "meeting": existing
                }

        # Create meeting record
        meeting = await self.db.create_meeting(
            user_id=user_id,
            title=title,
            source=source,
            external_id=external_id,
            subject=subject,
            organizer_email=organizer_email,
            meeting_date=meeting_date,
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
                        meeting_id=meeting["id"],
                        user_id=user_id,
                        title=title,
                        subject=subject,
                        meeting_date=meeting_date,
                        participants=participants or [],
                        transcript=transcript,
                        source=source
                    )
                    if pinecone_result:
                        await self.db.update_meeting_pinecone_id(
                            meeting["id"],
                            pinecone_result
                        )
                        meeting["pinecone_file_id"] = pinecone_result
            except Exception as e:
                logger.error(f"Failed to upload meeting to Pinecone: {e}")
                # Meeting is still created, just not searchable via RAG

        return {
            "success": True,
            "meeting": meeting
        }

    async def _upload_to_pinecone(
        self,
        meeting_id: str,
        user_id: str,
        title: str,
        subject: Optional[str],
        meeting_date: Optional[datetime],
        participants: List[str],
        transcript: str,
        source: str
    ) -> Optional[str]:
        """Upload meeting transcript to Pinecone"""
        pinecone = self.pinecone or get_pinecone_service()

        date_str = meeting_date.strftime("%Y-%m-%d %H:%M") if meeting_date else "Unknown date"
        participants_str = ", ".join(participants) if participants else "Unknown participants"

        enhanced_transcript = f"""## Meeting Information
- **Subject:** {subject or title}
- **Date:** {date_str}
- **Source:** {source.capitalize()}
- **Participants:** {participants_str}

## Transcript

{transcript}
"""

        result = await pinecone.upload_transcript(
            user_id=user_id,
            video_id=f"meeting_{meeting_id}",
            title=title,
            transcript=enhanced_transcript,
            metadata={
                "type": "meeting",
                "source": source,
                "meeting_id": meeting_id,
                "subject": subject,
                "meeting_date": date_str,
                "participants": participants_str
            }
        )

        if result.get("success"):
            return result.get("file_id")
        return None

    async def get_meeting(
        self,
        meeting_id: str,
        user_id: str,
        include_transcript: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Get a meeting by ID"""
        if not self.db:
            raise RuntimeError("Database service not configured")

        return await self.db.get_meeting(
            meeting_id=meeting_id,
            user_id=user_id,
            include_transcript=include_transcript
        )

    async def list_meetings(
        self,
        user_id: str,
        group_id: Optional[str] = None,
        source: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> Dict[str, Any]:
        """List meetings for a user with pagination"""
        if not self.db:
            raise RuntimeError("Database service not configured")

        offset = (page - 1) * per_page
        result = await self.db.list_meetings(
            user_id=user_id,
            group_id=group_id,
            source=source,
            offset=offset,
            limit=per_page
        )

        return {
            "meetings": result["meetings"],
            "total": result["total"],
            "page": page,
            "per_page": per_page,
            "has_more": offset + len(result["meetings"]) < result["total"]
        }

    async def delete_meeting(
        self,
        meeting_id: str,
        user_id: str
    ) -> bool:
        """Delete a meeting and its Pinecone file"""
        if not self.db:
            raise RuntimeError("Database service not configured")

        # Get meeting to find Pinecone file ID
        meeting = await self.db.get_meeting(meeting_id, user_id)
        if not meeting:
            return False

        # Delete from Pinecone if uploaded
        if meeting.get("pinecone_file_id"):
            try:
                pinecone = self.pinecone or get_pinecone_service()
                await pinecone.delete_file(meeting["pinecone_file_id"])
            except Exception as e:
                logger.warning(f"Failed to delete Pinecone file: {e}")

        # Delete from database
        return await self.db.delete_meeting(meeting_id, user_id)

    async def move_to_group(
        self,
        meeting_id: str,
        user_id: str,
        group_id: Optional[str]
    ) -> bool:
        """Move meeting to a different group"""
        if not self.db:
            raise RuntimeError("Database service not configured")

        return await self.db.update_meeting_group(meeting_id, user_id, group_id)

    async def update_transcript(
        self,
        meeting_id: str,
        user_id: str,
        transcript: str,
        re_upload_to_pinecone: bool = True
    ) -> Dict[str, Any]:
        """
        Update a meeting's transcript (e.g., when Zoom transcript becomes available).

        Args:
            meeting_id: Meeting ID
            user_id: User ID for ownership verification
            transcript: New transcript text
            re_upload_to_pinecone: Whether to re-upload to Pinecone

        Returns:
            Updated meeting data
        """
        if not self.db:
            raise RuntimeError("Database service not configured")

        # Get existing meeting
        meeting = await self.db.get_meeting(meeting_id, user_id, include_transcript=True)
        if not meeting:
            return {"success": False, "error": "Meeting not found"}

        # Update transcript in database
        async with self.db.get_session() as session:
            from sqlalchemy import update, text
            from app.services.database_service import MeetingModel
            import uuid

            await session.execute(
                update(MeetingModel)
                .where(
                    MeetingModel.id == uuid.UUID(meeting_id),
                    MeetingModel.user_id == uuid.UUID(user_id)
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
                if meeting.get("pinecone_file_id"):
                    try:
                        await pinecone.delete_file(meeting["pinecone_file_id"])
                    except Exception:
                        pass

                # Upload new version
                new_file_id = await self._upload_to_pinecone(
                    meeting_id=meeting_id,
                    user_id=user_id,
                    title=meeting["title"],
                    subject=meeting.get("subject"),
                    meeting_date=meeting.get("meeting_date"),
                    participants=meeting.get("participants", []),
                    transcript=transcript,
                    source=meeting["source"]
                )

                if new_file_id:
                    await self.db.update_meeting_pinecone_id(meeting_id, new_file_id)

            except Exception as e:
                logger.error(f"Failed to re-upload transcript to Pinecone: {e}")

        # Get updated meeting
        updated = await self.db.get_meeting(meeting_id, user_id)
        return {"success": True, "meeting": updated}


# =============================================================================
# Singleton Instance
# =============================================================================

_meeting_service: Optional[MeetingService] = None


def get_meeting_service() -> MeetingService:
    """Get or create meeting service singleton"""
    global _meeting_service
    if _meeting_service is None:
        _meeting_service = MeetingService()
    return _meeting_service
