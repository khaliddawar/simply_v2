"""
Email Service for TubeVibe Library
Sends video summaries via Postmark API with template support
"""

import os
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via Postmark API"""

    def __init__(self):
        """Initialize the Postmark email service"""
        self.api_token = os.getenv("POSTMARK_API_KEY")
        self.sender_email = os.getenv("POSTMARK_FROM_EMAIL", "summary@tubevibe.app")
        self.sender_name = os.getenv("POSTMARK_SENDER_NAME", "TubeVibe")
        self.youtube_template_id = os.getenv("POSTMARK_YOUTUBE_TEMPLATE_ID")

        self.client = None
        self.is_configured = False

        self._initialize_client()

    def _initialize_client(self):
        """Initialize Postmark client"""
        if not self.api_token:
            logger.warning("POSTMARK_API_KEY not set - email service disabled")
            return

        try:
            from postmarker.core import PostmarkClient
            self.client = PostmarkClient(server_token=self.api_token)
            self.is_configured = True
            logger.info(f"Email service initialized with sender: {self.sender_email}")
            if self.youtube_template_id:
                logger.info(f"Using YouTube summary template ID: {self.youtube_template_id}")
        except ImportError:
            logger.error("postmarker package not installed. Run: pip install postmarker")
        except Exception as e:
            logger.error(f"Failed to initialize Postmark client: {e}")

    def is_available(self) -> bool:
        """Check if email service is available"""
        return self.is_configured and self.client is not None

    def _sanitize_html(self, html: str) -> str:
        """Remove markdown code fences from HTML content"""
        if not html:
            return ""

        cleaned = html.strip()

        # Remove ```html ... ``` or ``` ... ```
        if cleaned.startswith("```"):
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        return cleaned.strip()

    def _send_email(self, email_data: Dict[str, Any]) -> bool:
        """Send email via Postmark API (synchronous)"""
        try:
            if "TemplateId" in email_data:
                response = self.client.emails.send_with_template(**email_data)
            else:
                response = self.client.emails.send(**email_data)

            return hasattr(response, 'message_id') or (isinstance(response, dict) and 'MessageID' in response)
        except Exception as e:
            logger.error(f"Postmark API error: {e}")
            return False

    async def send_summary_email(
        self,
        recipient_email: str,
        video_title: str,
        summary_html: str,
        video_id: Optional[str] = None,
        channel_name: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        transcript_length: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Send a video summary email

        Args:
            recipient_email: Email address to send to
            video_title: Title of the video
            summary_html: HTML formatted summary content
            video_id: YouTube video ID (for CTA links)
            channel_name: YouTube channel name
            duration_seconds: Video duration in seconds
            transcript_length: Length of transcript in characters

        Returns:
            Dict with success status and details
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "Email service not configured"
            }

        try:
            # Format duration
            duration_formatted = ""
            if duration_seconds and duration_seconds > 0:
                minutes = int(duration_seconds // 60)
                seconds = int(duration_seconds % 60)
                duration_formatted = f"{minutes}:{seconds:02d}"

            # Format transcript length
            transcript_info = ""
            if transcript_length and transcript_length > 0:
                word_count = transcript_length // 5  # Approximate words
                transcript_info = f"{word_count:,} words"

            # Clean the summary HTML
            clean_summary = self._sanitize_html(summary_html)

            # Use template if available
            if self.youtube_template_id:
                template_vars = {
                    "session_title": video_title,
                    "channel_name": channel_name,
                    "duration_formatted": duration_formatted if duration_formatted else None,
                    "transcript_length": transcript_info if transcript_info else None,
                    "summary": clean_summary,
                    "transcript_id": video_id,
                    "session_date": datetime.now().strftime("%B %d, %Y")
                }

                email_data = {
                    "From": f"{self.sender_name} <{self.sender_email}>",
                    "To": recipient_email,
                    "TemplateId": int(self.youtube_template_id),
                    "TemplateModel": template_vars
                }
            else:
                # Fallback to inline HTML
                subject = f"Video Summary: {video_title}"
                html_content = self._generate_summary_html(
                    video_title=video_title,
                    summary_html=clean_summary,
                    video_id=video_id,
                    channel_name=channel_name,
                    duration_formatted=duration_formatted,
                    transcript_info=transcript_info
                )

                email_data = {
                    "From": f"{self.sender_name} <{self.sender_email}>",
                    "To": recipient_email,
                    "Subject": subject,
                    "HtmlBody": html_content
                }

            # Send email in thread pool to not block
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._send_email, email_data)

            if result:
                logger.info(f"Summary email sent to {recipient_email} for video: {video_title}")
                return {
                    "success": True,
                    "message": f"Summary sent to {recipient_email}",
                    "recipient": recipient_email
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send email via Postmark"
                }

        except Exception as e:
            logger.error(f"Error sending summary email: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def send_welcome_email(
        self,
        recipient_email: str,
        first_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a welcome email to new users who signed up via Google OAuth.

        Args:
            recipient_email: Email address to send to
            first_name: User's first name for personalization

        Returns:
            Dict with success status and details
        """
        if not self.is_available():
            logger.warning("Email service not available - skipping welcome email")
            return {
                "success": False,
                "error": "Email service not configured"
            }

        try:
            # Personalize greeting
            greeting = f"Hi {first_name}," if first_name else "Welcome!"

            html_content = self._generate_welcome_html(greeting, first_name)

            email_data = {
                "From": f"{self.sender_name} <{self.sender_email}>",
                "To": recipient_email,
                "Subject": "Welcome to TubeVibe! 🎉",
                "HtmlBody": html_content
            }

            # Send email in thread pool to not block
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._send_email, email_data)

            if result:
                logger.info(f"Welcome email sent to {recipient_email}")
                return {
                    "success": True,
                    "message": f"Welcome email sent to {recipient_email}",
                    "recipient": recipient_email
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send welcome email via Postmark"
                }

        except Exception as e:
            logger.error(f"Error sending welcome email: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _generate_welcome_html(self, greeting: str, first_name: Optional[str] = None) -> str:
        """Generate HTML welcome email content"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Welcome to TubeVibe</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f5f5f5;">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #00C2B8 0%, #00a89f 100%); color: white; padding: 32px; border-radius: 12px 12px 0 0; text-align: center;">
                <h1 style="margin: 0; font-size: 28px; font-weight: 700;">Welcome to TubeVibe!</h1>
                <p style="margin: 8px 0 0 0; opacity: 0.9; font-size: 16px;">Your personal YouTube knowledge library</p>
            </div>

            <!-- Content -->
            <div style="background: white; padding: 32px; border-radius: 0 0 12px 12px;">
                <p style="font-size: 18px; margin-top: 0;">{greeting}</p>

                <p>Thanks for joining TubeVibe! You're all set to start building your personal video knowledge library.</p>

                <h3 style="color: #00C2B8; margin-top: 24px;">What you can do:</h3>
                <ul style="padding-left: 20px;">
                    <li style="margin-bottom: 8px;"><strong>Save transcripts</strong> - Capture any YouTube video's transcript with one click</li>
                    <li style="margin-bottom: 8px;"><strong>AI summaries</strong> - Get instant summaries of long videos</li>
                    <li style="margin-bottom: 8px;"><strong>Smart search</strong> - Find information across all your saved videos</li>
                    <li style="margin-bottom: 8px;"><strong>Organize</strong> - Group videos by topic or project</li>
                </ul>

                <div style="text-align: center; margin: 32px 0;">
                    <a href="https://www.youtube.com"
                       style="display: inline-block; background: linear-gradient(135deg, #00C2B8 0%, #00a89f 100%); color: white; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 16px;">
                        Start Exploring YouTube
                    </a>
                </div>

                <p style="color: #666; font-size: 14px;">
                    Just install our Chrome extension, navigate to any YouTube video, and click the TubeVibe icon to get started!
                </p>

                <!-- Footer -->
                <div style="text-align: center; color: #999; font-size: 12px; margin-top: 32px; padding-top: 16px; border-top: 1px solid #eee;">
                    <p>Happy learning!</p>
                    <p>The TubeVibe Team</p>
                </div>
            </div>
        </body>
        </html>
        """

    def _generate_summary_html(
        self,
        video_title: str,
        summary_html: str,
        video_id: Optional[str] = None,
        channel_name: Optional[str] = None,
        duration_formatted: Optional[str] = None,
        transcript_info: Optional[str] = None
    ) -> str:
        """Generate HTML email content (fallback when no template)"""

        # Build metadata section
        metadata_html = ""
        if channel_name:
            metadata_html += f"<div><strong>Channel:</strong> {channel_name}</div>"
        if duration_formatted:
            metadata_html += f"<div><strong>Duration:</strong> {duration_formatted}</div>"
        if transcript_info:
            metadata_html += f"<div><strong>Transcript:</strong> {transcript_info}</div>"

        # Build CTA section
        cta_html = ""
        if video_id:
            cta_html = f"""
            <div style="text-align: center; margin: 30px 0; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px;">
                <a href="https://www.youtube.com/watch?v={video_id}"
                   style="display: inline-block; background: white; color: #667eea; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600;">
                    Watch Video
                </a>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{video_title}</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%); color: white; padding: 24px; border-radius: 12px 12px 0 0;">
                <h1 style="margin: 0 0 12px 0; font-size: 20px; font-weight: 600;">{video_title}</h1>
                {f'<div style="font-size: 14px; opacity: 0.9;">{metadata_html}</div>' if metadata_html else ''}
            </div>

            <!-- Content -->
            <div style="background: #f8fafc; padding: 24px; border-radius: 0 0 12px 12px;">
                <div style="background: white; padding: 20px; border-radius: 8px; border-left: 4px solid #667eea;">
                    {summary_html}
                </div>

                {cta_html}

                <!-- Footer -->
                <div style="text-align: center; color: #666; font-size: 12px; margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e7eb;">
                    <p>Generated by TubeVibe &bull; {datetime.now().strftime('%B %d, %Y')}</p>
                </div>
            </div>
        </body>
        </html>
        """


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create Email service singleton"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
