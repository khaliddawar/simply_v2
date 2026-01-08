"""
Webhook Routes - External transcript sources (Fireflies, Zoom)
"""
import logging
import hmac
import hashlib
import json
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Request, Header, HTTPException
from fastapi.responses import JSONResponse

from app.settings import get_settings
from app.services.database_service import get_database_service
from app.services.pinecone_service import get_pinecone_service
from app.services.fireflies_service import get_fireflies_service
from app.models.meeting import (
    FirefliesWebhookPayload,
    ZoomWebhookPayload,
    WebhookResponse,
    MeetingSource
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Signature Verification
# =============================================================================

def verify_fireflies_signature(raw_body: bytes, signature_header: str, webhook_secret: str) -> bool:
    """
    Verify Fireflies webhook signature.
    Fireflies uses HMAC-SHA256 for webhook verification.
    Signature header may be in format: sha256=<hex_digest> or just <hex_digest>
    """
    if not signature_header or not webhook_secret:
        return False

    try:
        # Handle sha256= prefix if present
        if signature_header.startswith("sha256="):
            provided_signature = signature_header[7:]  # Remove 'sha256=' prefix
        else:
            provided_signature = signature_header

        expected_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            raw_body,
            hashlib.sha256
        ).hexdigest()

        logger.debug(f"Signature verification - provided: {provided_signature[:20]}..., expected: {expected_signature[:20]}...")

        return hmac.compare_digest(expected_signature, provided_signature)
    except Exception as e:
        logger.error(f"Error verifying Fireflies signature: {e}")
        return False


def verify_zoom_signature(raw_body: bytes, signature_header: str, webhook_secret: str, timestamp: str) -> bool:
    """
    Verify Zoom webhook signature.
    Zoom uses v0:timestamp:body format for signature verification.
    """
    if not signature_header or not webhook_secret or not timestamp:
        return False

    try:
        message = f"v0:{timestamp}:{raw_body.decode('utf-8')}"
        expected_signature = "v0=" + hmac.new(
            webhook_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature_header)
    except Exception as e:
        logger.error(f"Error verifying Zoom signature: {e}")
        return False


# =============================================================================
# Fireflies Webhook
# =============================================================================

@router.post("/fireflies", response_model=WebhookResponse)
async def fireflies_webhook(
    request: Request,
    x_hub_signature: Optional[str] = Header(None, alias="x-hub-signature"),
):
    """
    Handle Fireflies webhook notifications.

    Fireflies webhook payload is minimal - just meetingId and eventType.
    We fetch the full transcript details from Fireflies API.

    Configure in Fireflies: https://app.fireflies.ai/integrations/webhooks
    Webhook URL: https://your-domain.com/webhook/fireflies
    """
    settings = get_settings()

    # Get raw body for signature verification
    body = await request.body()

    # Parse JSON payload
    try:
        payload_data = json.loads(body.decode())
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in Fireflies webhook payload: {e}")
        return WebhookResponse(success=False, message="Invalid JSON payload", error=str(e))

    # Extract meeting ID and event type from minimal payload
    meeting_id = payload_data.get("meetingId")
    event_type = payload_data.get("eventType", "unknown")

    logger.info(f"Received Fireflies webhook: event={event_type}, meetingId={meeting_id}")
    logger.debug(f"Fireflies payload: {json.dumps(payload_data, indent=2)}")

    # Verify signature if secret is configured (Fireflies uses x-hub-signature)
    if settings.fireflies_webhook_secret:
        if not x_hub_signature:
            logger.warning("Missing x-hub-signature header")
            return WebhookResponse(success=False, message="Missing signature", error="Missing x-hub-signature header")

        logger.info(f"Verifying signature: header={x_hub_signature[:30]}... secret_configured=True")
        if not verify_fireflies_signature(body, x_hub_signature, settings.fireflies_webhook_secret):
            logger.warning(f"Invalid Fireflies signature - header value: {x_hub_signature}")
            return WebhookResponse(success=False, message="Invalid signature", error="Signature verification failed")
        logger.info("Fireflies signature verified successfully")
    else:
        logger.warning("Fireflies webhook secret not configured - skipping signature verification")

    # Validate meeting ID
    if not meeting_id:
        logger.warning("No meetingId in Fireflies webhook payload")
        return WebhookResponse(success=True, message="No meetingId to process")

    # Only process transcription completed events
    if event_type != "Transcription completed":
        logger.info(f"Ignoring Fireflies event type: {event_type}")
        return WebhookResponse(success=True, message=f"Event {event_type} ignored")

    # Process the webhook - fetch full transcript from Fireflies API
    try:
        # Get Fireflies service
        fireflies_service = get_fireflies_service()
        if not fireflies_service.is_initialized():
            logger.error("Fireflies API key not configured - cannot fetch transcript")
            return WebhookResponse(
                success=False,
                message="Fireflies API not configured",
                error="FIREFLIES_API_KEY not set"
            )

        # Fetch full transcript from Fireflies API
        logger.info(f"Fetching transcript {meeting_id} from Fireflies API...")
        transcript_data = await fireflies_service.get_transcript(meeting_id)

        if not transcript_data:
            logger.error(f"Failed to fetch transcript {meeting_id} from Fireflies API")
            return WebhookResponse(
                success=False,
                message="Failed to fetch transcript from Fireflies API",
                error=f"Could not retrieve transcript {meeting_id}"
            )

        # Check for transcript content
        if not transcript_data.transcript_text:
            logger.warning(f"No transcript text for meeting {meeting_id}")
            return WebhookResponse(success=True, message="No transcript text available")

        # Find user by organizer email
        db = await get_database_service()
        user = None
        if transcript_data.organizer_email:
            user = await db.get_user_by_email(transcript_data.organizer_email)

        if not user:
            logger.warning(f"No user found for organizer email: {transcript_data.organizer_email}")
            return WebhookResponse(
                success=True,
                message="Webhook received but no matching user found",
                meeting_id=meeting_id
            )

        # Check for duplicate
        existing = await db.get_meeting_by_external_id(
            user_id=user["id"],
            external_id=meeting_id,
            source="fireflies"
        )
        if existing:
            logger.info(f"Duplicate Fireflies meeting {meeting_id} for user {user['id']}")
            return WebhookResponse(
                success=True,
                message="Meeting already exists",
                meeting_id=existing["id"]
            )

        # Store meeting source metadata
        source_metadata = {
            "audio_url": transcript_data.audio_url,
            "video_url": transcript_data.video_url,
            "action_items": transcript_data.action_items,
            "keywords": transcript_data.keywords,
            "fireflies_summary": transcript_data.summary,
        }

        # Create meeting record
        meeting = await db.create_meeting(
            user_id=user["id"],
            title=transcript_data.title,
            source="fireflies",
            external_id=meeting_id,
            subject=transcript_data.title,
            organizer_email=transcript_data.organizer_email,
            meeting_date=transcript_data.date,
            duration_minutes=transcript_data.duration_minutes,
            participants=transcript_data.participants,
            transcript=transcript_data.transcript_text,
            source_metadata=source_metadata
        )

        # Upload to Pinecone for RAG
        try:
            pinecone_service = get_pinecone_service()
            pinecone_file_id = await upload_meeting_to_pinecone(
                pinecone_service=pinecone_service,
                meeting_id=meeting["id"],
                user_id=user["id"],
                title=transcript_data.title,
                subject=transcript_data.title,
                meeting_date=transcript_data.date,
                participants=transcript_data.participants,
                transcript=transcript_data.transcript_text,
                source="fireflies"
            )
            if pinecone_file_id:
                await db.update_meeting_pinecone_id(meeting["id"], pinecone_file_id)
                logger.info(f"Meeting {meeting['id']} uploaded to Pinecone: {pinecone_file_id}")
        except Exception as e:
            logger.error(f"Failed to upload meeting to Pinecone: {e}")
            # Meeting is still saved, just not in RAG

        logger.info(f"Fireflies meeting saved: {meeting['id']} - {transcript_data.title}")
        return WebhookResponse(
            success=True,
            message="Meeting transcript saved successfully",
            meeting_id=meeting["id"]
        )

    except Exception as e:
        logger.error(f"Error processing Fireflies webhook: {e}", exc_info=True)
        return WebhookResponse(success=False, message="Processing error", error=str(e))


# =============================================================================
# Zoom Webhook
# =============================================================================

@router.post("/zoom", response_model=WebhookResponse)
async def zoom_webhook(
    request: Request,
    x_zm_signature: Optional[str] = Header(None, alias="x-zm-signature"),
    x_zm_request_timestamp: Optional[str] = Header(None, alias="x-zm-request-timestamp"),
):
    """
    Handle Zoom webhook notifications.

    Zoom sends webhooks when:
    - recording.transcript_completed
    - meeting.ended (with transcript)

    Configure in Zoom Marketplace App settings.
    """
    settings = get_settings()

    # Get raw body
    body = await request.body()

    # Parse JSON payload
    try:
        payload_data = json.loads(body.decode())
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in Zoom webhook payload: {e}")
        return WebhookResponse(success=False, message="Invalid JSON payload", error=str(e))

    event_type = payload_data.get('event', 'unknown')
    logger.info(f"Received Zoom webhook: {event_type}")
    logger.debug(f"Zoom payload: {json.dumps(payload_data, indent=2)}")

    # Handle Zoom URL validation challenge
    if event_type == "endpoint.url_validation":
        plain_token = payload_data.get("payload", {}).get("plainToken")
        if plain_token and settings.zoom_webhook_secret:
            encrypted_token = hmac.new(
                settings.zoom_webhook_secret.encode('utf-8'),
                plain_token.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            return JSONResponse(
                status_code=200,
                content={
                    "plainToken": plain_token,
                    "encryptedToken": encrypted_token
                }
            )

    # Verify signature if secret is configured
    if settings.zoom_webhook_secret:
        if not x_zm_signature or not x_zm_request_timestamp:
            logger.warning("Missing Zoom signature headers")
            return WebhookResponse(success=False, message="Missing signature", error="Missing signature headers")

        if not verify_zoom_signature(body, x_zm_signature, settings.zoom_webhook_secret, x_zm_request_timestamp):
            logger.warning("Invalid Zoom signature")
            return WebhookResponse(success=False, message="Invalid signature", error="Signature verification failed")
    else:
        logger.warning("Zoom webhook secret not configured - skipping signature verification")

    # Process relevant events
    try:
        payload = ZoomWebhookPayload(**payload_data)

        # Only process transcript-related events
        if event_type not in ["recording.transcript_completed", "recording.completed"]:
            logger.info(f"Ignoring Zoom event type: {event_type}")
            return WebhookResponse(success=True, message=f"Event {event_type} ignored")

        # Extract meeting details
        meeting_id = payload.get_meeting_id()
        topic = payload.get_topic()
        start_time = payload.get_start_time()
        duration = payload.get_duration()
        host_email = payload.get_host_email()

        if not meeting_id:
            logger.warning("No meeting ID in Zoom webhook")
            return WebhookResponse(success=True, message="No meeting ID to process")

        # For Zoom, transcript needs to be fetched from recording files
        # The webhook typically contains download URLs for the transcript
        transcript_text = None
        transcript_url = None
        recording_files = payload.payload.get("object", {}).get("recording_files", []) if payload.payload else []

        for file in recording_files:
            if file.get("file_type") in ["TRANSCRIPT", "transcript"]:
                transcript_url = file.get("download_url")
                break

        # Note: Fetching the actual transcript from download_url requires Zoom OAuth token
        # For now, we'll store metadata and the user can manually add transcript
        # or implement OAuth flow to fetch transcript

        if not transcript_text and not transcript_url:
            logger.warning(f"No transcript available in Zoom webhook for meeting {meeting_id}")
            # Still save the meeting metadata for manual transcript addition
            pass

        # Parse meeting date
        meeting_date = None
        if start_time:
            try:
                meeting_date = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            except ValueError:
                logger.warning(f"Could not parse meeting date: {start_time}")

        # Find user by host email
        db = await get_database_service()
        user = None
        if host_email:
            user = await db.get_user_by_email(host_email)

        if not user:
            logger.warning(f"No user found for Zoom host email: {host_email}")
            return WebhookResponse(
                success=True,
                message="Webhook received but no matching user found",
                meeting_id=meeting_id
            )

        # Check for duplicate
        existing = await db.get_meeting_by_external_id(
            user_id=user["id"],
            external_id=meeting_id,
            source="zoom"
        )
        if existing:
            logger.info(f"Duplicate Zoom meeting {meeting_id} for user {user['id']}")
            return WebhookResponse(
                success=True,
                message="Meeting already exists",
                meeting_id=existing["id"]
            )

        # Extract participants if available
        participants = []
        participant_users = payload.payload.get("object", {}).get("participant_users", []) if payload.payload else []
        for p in participant_users:
            name = p.get("user_name") or p.get("email")
            if name:
                participants.append(name)

        # Store source metadata
        source_metadata = {
            "zoom_meeting_id": meeting_id,
            "transcript_url": transcript_url,
            "recording_files": recording_files,
            "timezone": payload.payload.get("object", {}).get("timezone") if payload.payload else None
        }

        # Create meeting record
        meeting = await db.create_meeting(
            user_id=user["id"],
            title=topic or f"Zoom Meeting {meeting_id}",
            source="zoom",
            external_id=meeting_id,
            subject=topic,
            organizer_email=host_email,
            meeting_date=meeting_date,
            duration_minutes=duration,
            participants=participants,
            transcript=transcript_text,  # May be None initially
            source_metadata=source_metadata
        )

        # Upload to Pinecone if transcript is available
        if transcript_text:
            try:
                pinecone_service = get_pinecone_service()
                pinecone_file_id = await upload_meeting_to_pinecone(
                    pinecone_service=pinecone_service,
                    meeting_id=meeting["id"],
                    user_id=user["id"],
                    title=topic or f"Zoom Meeting {meeting_id}",
                    subject=topic,
                    meeting_date=meeting_date,
                    participants=participants,
                    transcript=transcript_text,
                    source="zoom"
                )
                if pinecone_file_id:
                    await db.update_meeting_pinecone_id(meeting["id"], pinecone_file_id)
            except Exception as e:
                logger.error(f"Failed to upload Zoom meeting to Pinecone: {e}")

        logger.info(f"Zoom meeting saved: {meeting['id']}")
        return WebhookResponse(
            success=True,
            message="Meeting saved successfully" + (" (transcript pending)" if not transcript_text else ""),
            meeting_id=meeting["id"]
        )

    except Exception as e:
        logger.error(f"Error processing Zoom webhook: {e}", exc_info=True)
        return WebhookResponse(success=False, message="Processing error", error=str(e))


# =============================================================================
# Pinecone Upload Helper
# =============================================================================

async def upload_meeting_to_pinecone(
    pinecone_service,
    meeting_id: str,
    user_id: str,
    title: str,
    subject: Optional[str],
    meeting_date: Optional[datetime],
    participants: list,
    transcript: str,
    source: str
) -> Optional[str]:
    """
    Upload meeting transcript to Pinecone Assistant for RAG.

    Returns the Pinecone file ID if successful, None otherwise.
    """
    # Format transcript with meeting context
    date_str = meeting_date.strftime("%Y-%m-%d %H:%M") if meeting_date else "Unknown date"
    participants_str = ", ".join(participants) if participants else "Unknown participants"

    # Create enhanced transcript with meeting metadata embedded
    enhanced_transcript = f"""## Meeting Information
- **Subject:** {subject or title}
- **Date:** {date_str}
- **Source:** {source.capitalize()}
- **Participants:** {participants_str}

## Transcript

{transcript}
"""

    # Upload to Pinecone using existing method
    # video_id parameter is used as the content identifier
    try:
        result = await pinecone_service.upload_transcript(
            user_id=user_id,
            video_id=f"meeting_{meeting_id}",  # Use meeting prefix for identification
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
        else:
            logger.error(f"Pinecone upload failed: {result.get('error')}")
            return None
    except Exception as e:
        logger.error(f"Pinecone upload failed for meeting {meeting_id}: {e}")
        return None
