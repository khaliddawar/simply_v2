"""
Fireflies Service - GraphQL API client for fetching meeting transcripts

Fireflies.ai API Documentation: https://docs.fireflies.ai/graphql-api/
"""
import logging
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from app.settings import get_settings

logger = logging.getLogger(__name__)

FIREFLIES_API_URL = "https://api.fireflies.ai/graphql"


@dataclass
class FirefliesTranscript:
    """Parsed transcript data from Fireflies API"""
    id: str
    title: str
    organizer_email: Optional[str]
    date: Optional[datetime]
    duration_minutes: Optional[int]
    participants: List[str]
    transcript_text: str
    sentences: List[Dict[str, Any]]
    summary: Optional[str]
    action_items: List[str]
    keywords: List[str]
    audio_url: Optional[str]
    video_url: Optional[str]
    raw_data: Dict[str, Any]


class FirefliesService:
    """Service for interacting with Fireflies GraphQL API"""

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.fireflies_api_key
        self.initialized = bool(self.api_key)

        if not self.initialized:
            logger.warning("FIREFLIES_API_KEY not set - Fireflies service disabled")

    def is_initialized(self) -> bool:
        """Check if service is properly configured"""
        return self.initialized

    async def get_transcript(self, transcript_id: str) -> Optional[FirefliesTranscript]:
        """
        Fetch a complete transcript from Fireflies API by ID.

        Args:
            transcript_id: The Fireflies meeting/transcript ID

        Returns:
            FirefliesTranscript object with all meeting data, or None if failed
        """
        if not self.initialized:
            logger.error("Fireflies service not initialized - missing API key")
            return None

        # GraphQL query to fetch complete transcript details
        query = """
        query Transcript($transcriptId: String!) {
            transcript(id: $transcriptId) {
                id
                title
                organizer_email
                host_email
                date
                dateString
                duration
                participants
                fireflies_users
                transcript_url
                audio_url
                video_url
                speakers {
                    id
                    name
                }
                sentences {
                    index
                    speaker_name
                    speaker_id
                    text
                    raw_text
                    start_time
                    end_time
                }
                summary {
                    keywords
                    action_items
                    outline
                    shorthand_bullet
                    overview
                    bullet_gist
                    gist
                    short_summary
                }
            }
        }
        """

        variables = {"transcriptId": transcript_id}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    FIREFLIES_API_URL,
                    json={"query": query, "variables": variables},
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code != 200:
                    logger.error(f"Fireflies API error: {response.status_code} - {response.text}")
                    return None

                data = response.json()

                if "errors" in data:
                    logger.error(f"Fireflies GraphQL errors: {data['errors']}")
                    return None

                transcript_data = data.get("data", {}).get("transcript")
                if not transcript_data:
                    logger.warning(f"No transcript found for ID: {transcript_id}")
                    return None

                return self._parse_transcript(transcript_data)

        except httpx.TimeoutException:
            logger.error(f"Fireflies API timeout for transcript {transcript_id}")
            return None
        except Exception as e:
            logger.error(f"Error fetching transcript from Fireflies: {e}", exc_info=True)
            return None

    def _parse_transcript(self, data: Dict[str, Any]) -> FirefliesTranscript:
        """Parse raw API response into FirefliesTranscript object"""

        # Extract organizer email (try both fields)
        organizer_email = data.get("organizer_email") or data.get("host_email")

        # Parse date
        meeting_date = None
        if data.get("date"):
            try:
                # Fireflies returns Unix timestamp in milliseconds
                timestamp = int(data["date"]) / 1000
                meeting_date = datetime.fromtimestamp(timestamp)
            except (ValueError, TypeError):
                pass

        # Duration in minutes (API returns seconds)
        duration_minutes = None
        if data.get("duration"):
            try:
                duration_minutes = int(data["duration"]) // 60
            except (ValueError, TypeError):
                pass

        # Extract participants
        participants = data.get("participants") or []
        if isinstance(participants, str):
            participants = [p.strip() for p in participants.split(",") if p.strip()]

        # Build transcript text from sentences
        sentences = data.get("sentences") or []
        transcript_lines = []
        for sentence in sentences:
            speaker = sentence.get("speaker_name", "Speaker")
            text = sentence.get("text", "")
            if text:
                transcript_lines.append(f"{speaker}: {text}")

        transcript_text = "\n".join(transcript_lines)

        # Extract summary data
        summary_data = data.get("summary") or {}
        summary_text = (
            summary_data.get("overview") or
            summary_data.get("gist") or
            summary_data.get("short_summary") or
            ""
        )
        action_items = summary_data.get("action_items") or []
        keywords = summary_data.get("keywords") or []

        return FirefliesTranscript(
            id=data.get("id", ""),
            title=data.get("title", "Untitled Meeting"),
            organizer_email=organizer_email,
            date=meeting_date,
            duration_minutes=duration_minutes,
            participants=participants,
            transcript_text=transcript_text,
            sentences=sentences,
            summary=summary_text,
            action_items=action_items if isinstance(action_items, list) else [],
            keywords=keywords if isinstance(keywords, list) else [],
            audio_url=data.get("audio_url"),
            video_url=data.get("video_url"),
            raw_data=data
        )

    async def list_recent_transcripts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        List recent transcripts (useful for testing/debugging).

        Args:
            limit: Maximum number of transcripts to return

        Returns:
            List of transcript summaries
        """
        if not self.initialized:
            return []

        query = """
        query Transcripts($limit: Int) {
            transcripts(limit: $limit) {
                id
                title
                date
                organizer_email
                duration
                participants
            }
        }
        """

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    FIREFLIES_API_URL,
                    json={"query": query, "variables": {"limit": limit}},
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code != 200:
                    logger.error(f"Fireflies API error: {response.status_code}")
                    return []

                data = response.json()
                return data.get("data", {}).get("transcripts", [])

        except Exception as e:
            logger.error(f"Error listing Fireflies transcripts: {e}")
            return []


# =============================================================================
# Singleton Instance
# =============================================================================

_fireflies_service: Optional[FirefliesService] = None


def get_fireflies_service() -> FirefliesService:
    """Get or create Fireflies service singleton"""
    global _fireflies_service
    if _fireflies_service is None:
        _fireflies_service = FirefliesService()
    return _fireflies_service
