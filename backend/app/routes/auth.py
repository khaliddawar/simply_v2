"""
Authentication Routes
"""
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import RedirectResponse
from typing import Optional
from pydantic import BaseModel

from app.models.user import (
    UserCreate, UserLogin, UserResponse, TokenResponse,
    GoogleOAuthRequest, PasswordResetRequest
)
from app.services.auth_service import get_auth_service, AuthService

router = APIRouter()
security = HTTPBearer()


class GoogleIdTokenRequest(BaseModel):
    """Request body for Google ID token verification"""
    id_token: str


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """Extract and validate user ID from JWT token"""
    auth_service = get_auth_service()
    user_id = auth_service.get_user_id_from_token(credentials.credentials)

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return user_id


# Optional auth dependency for testing without authentication
optional_security = HTTPBearer(auto_error=False)


def get_current_user_id_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security)
) -> str:
    """
    Extract user ID from token, or return test user ID if allow_no_auth is enabled.
    Used for testing without authentication.
    """
    from app.settings import get_settings
    settings = get_settings()

    # If allow_no_auth is enabled, return test user ID (valid UUID format)
    if settings.allow_no_auth:
        return "00000000-0000-0000-0000-000000000001"

    # Otherwise require valid token
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    auth_service = get_auth_service()
    user_id = auth_service.get_user_id_from_token(credentials.credentials)

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return user_id


@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserCreate):
    """
    Register a new user with email and password.

    Returns access token and user data on success.
    """
    auth_service = get_auth_service()

    result = await auth_service.register_user(
        email=user_data.email,
        password=user_data.password,
        first_name=user_data.first_name,
        last_name=user_data.last_name
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        expires_in=result["expires_in"],
        user=UserResponse(**result["user"])
    )


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    """
    Authenticate user with email and password.

    Returns access token and user data on success.
    """
    auth_service = get_auth_service()

    result = await auth_service.login_user(
        email=credentials.email,
        password=credentials.password
    )

    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("error"))

    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        expires_in=result["expires_in"],
        user=UserResponse(**result["user"])
    )


@router.post("/google", response_model=TokenResponse)
async def google_oauth(request: GoogleOAuthRequest):
    """
    Handle Google OAuth callback.

    Exchange authorization code for tokens and create/login user.
    """
    auth_service = get_auth_service()

    result = await auth_service.google_oauth_callback(
        code=request.code,
        redirect_uri=request.redirect_uri
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        expires_in=result["expires_in"],
        user=UserResponse(**result["user"])
    )


@router.post("/google/verify", response_model=TokenResponse)
async def verify_google_token(request: GoogleIdTokenRequest):
    """
    Verify Google ID token and authenticate user (used by Chrome extension).

    The extension uses Chrome's identity API to get an ID token,
    which is verified against Google's servers.
    Returns JWT token for subsequent API calls.
    """
    auth_service = get_auth_service()

    result = await auth_service.authenticate_extension(request.id_token)

    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("error"))

    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        expires_in=result["expires_in"],
        user=UserResponse(**result["user"])
    )


@router.get("/google/login")
async def google_login(redirect_uri: str = None):
    """
    Initiate Google OAuth flow - redirects to Google login page.
    Used by frontend for browser-based authentication.
    """
    from app.settings import get_settings
    settings = get_settings()

    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    # Use provided redirect_uri or default
    callback_uri = f"{settings.api_base_url}/api/auth/google/callback"

    # Build Google OAuth URL
    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={settings.google_client_id}&"
        f"redirect_uri={callback_uri}&"
        "response_type=code&"
        "scope=openid%20email%20profile&"
        "access_type=offline"
    )

    # Store the final redirect URI in session/state if provided
    if redirect_uri:
        google_auth_url += f"&state={redirect_uri}"

    return RedirectResponse(url=google_auth_url)


@router.get("/google/callback")
async def google_callback(code: str = None, state: str = None, error: str = None):
    """
    Handle Google OAuth callback - exchanges code for tokens.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    from app.settings import get_settings
    settings = get_settings()

    auth_service = get_auth_service()

    callback_uri = f"{settings.api_base_url}/api/auth/google/callback"

    result = await auth_service.google_oauth_callback(
        code=code,
        redirect_uri=callback_uri
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    # If state contains a redirect URI, redirect there with tokens
    if state:
        redirect_url = f"{state}?access_token={result['access_token']}"
        return RedirectResponse(url=redirect_url)

    # Otherwise return JSON response
    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        expires_in=result["expires_in"],
        user=UserResponse(**result["user"])
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(user_id: str = Depends(get_current_user_id)):
    """
    Get current authenticated user's profile.
    """
    auth_service = get_auth_service()

    if not auth_service.db:
        raise HTTPException(status_code=500, detail="Database not available")

    user = await auth_service.db.get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=user["id"],
        email=user["email"],
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        plan_type=user.get("plan_type", "free"),
        pinecone_namespace=user.get("pinecone_namespace")
    )


@router.post("/password-reset")
async def request_password_reset(request: PasswordResetRequest):
    """
    Request a password reset email.
    """
    # TODO: Implement password reset
    return {"message": "If an account exists with this email, a reset link has been sent"}


@router.post("/refresh")
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Refresh an access token.
    """
    auth_service = get_auth_service()

    # Verify current token
    user_id = auth_service.get_user_id_from_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Generate new token
    new_token = auth_service.create_access_token(user_id)

    return {
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": auth_service.access_token_expire_minutes * 60
    }


@router.post("/admin/fix-test-user-videos")
async def fix_test_user_videos(
    user_id: str = Depends(get_current_user_id)
):
    """
    One-time admin endpoint to reassign videos from test user to current user.
    This fixes videos saved with TEST_MODE enabled.

    IMPORTANT: Only run this once, then remove this endpoint.
    """
    from sqlalchemy import select, update, func
    from app.services.database_service import VideoModel
    import uuid

    auth_service = get_auth_service()

    if not auth_service.db:
        raise HTTPException(status_code=500, detail="Database not available")

    TEST_USER_ID = "00000000-0000-0000-0000-000000000001"

    try:
        # Count and update videos using SQLAlchemy
        async with auth_service.db.get_session() as session:
            # Count videos with test user ID
            count_result = await session.execute(
                select(func.count()).select_from(VideoModel).where(
                    VideoModel.user_id == uuid.UUID(TEST_USER_ID)
                )
            )
            test_video_count = count_result.scalar() or 0

            if test_video_count == 0:
                return {
                    "success": True,
                    "message": "No videos found with test user ID",
                    "videos_updated": 0
                }

            # Update videos from test user to current authenticated user
            from datetime import datetime
            await session.execute(
                update(VideoModel)
                .where(VideoModel.user_id == uuid.UUID(TEST_USER_ID))
                .values(user_id=uuid.UUID(user_id), updated_at=datetime.utcnow())
            )

        return {
            "success": True,
            "message": f"Successfully reassigned {test_video_count} videos from test user to your account",
            "videos_updated": test_video_count,
            "new_user_id": user_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fix videos: {str(e)}")


class AdminResetPasswordRequest(BaseModel):
    """Request body for admin password reset"""
    email: str
    new_password: str
    admin_secret: str


@router.post("/admin/reset-password")
async def admin_reset_password(request: AdminResetPasswordRequest):
    """
    TEMPORARY admin endpoint to reset a user's password.
    Requires admin_secret for security.

    IMPORTANT: Remove this endpoint after use.
    """
    import os

    # Simple security check - require a secret
    expected_secret = os.getenv("ADMIN_SECRET", "tubevibe-admin-2024")
    if request.admin_secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    auth_service = get_auth_service()

    if not auth_service.db:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        # Check if user exists
        user = await auth_service.db.get_user_by_email(request.email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Hash new password
        new_password_hash = auth_service.hash_password(request.new_password)

        # Update password in database using update_user method
        await auth_service.db.update_user(user["id"], {"password_hash": new_password_hash})

        return {
            "success": True,
            "message": f"Password reset for {request.email}",
            "user_id": user["id"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset password: {str(e)}")


@router.post("/admin/fix-pinecone-metadata")
async def fix_pinecone_metadata(
    user_id: str = Depends(get_current_user_id)
):
    """
    Re-upload all user's videos to Pinecone with correct user_id metadata.
    This fixes transcripts that were uploaded with TEST_MODE user_id.
    """
    from app.services.pinecone_service import get_pinecone_service
    from app.services.video_service import get_video_service

    auth_service = get_auth_service()
    pinecone_service = get_pinecone_service()
    video_service = get_video_service()

    if not auth_service.db:
        raise HTTPException(status_code=500, detail="Database not available")

    if not pinecone_service.is_initialized():
        raise HTTPException(status_code=500, detail="Pinecone service not initialized")

    try:
        # Get all videos for the current user (without transcripts first for listing)
        videos_result = await video_service.list_videos(user_id, per_page=100)
        if not videos_result.get("success"):
            raise HTTPException(status_code=400, detail=videos_result.get("error"))

        videos = videos_result.get("videos", [])
        updated_count = 0
        skipped_count = 0
        errors = []

        for video in videos:
            try:
                # Fetch each video with transcript included
                video_with_transcript = await video_service.get_video(
                    user_id=user_id,
                    video_id=video["id"],
                    include_transcript=True
                )

                if not video_with_transcript.get("success"):
                    errors.append(f"{video['title']}: Failed to fetch video details")
                    continue

                video_data = video_with_transcript.get("video", {})
                transcript = video_data.get("transcript")

                # Skip videos without transcripts
                if not transcript:
                    skipped_count += 1
                    continue

                # Re-upload to Pinecone with correct user_id
                metadata = {
                    "channel_name": video_data.get("channel_name"),
                    "duration_seconds": video_data.get("duration_seconds"),
                    "group_id": video_data.get("group_id")
                }

                result = await pinecone_service.upload_transcript(
                    user_id=user_id,  # Use the CORRECT user_id
                    video_id=video_data["id"],
                    title=video_data["title"],
                    transcript=transcript,
                    metadata=metadata
                )

                if result.get("success"):
                    # Update the pinecone_file_id in database
                    await video_service.update_video_pinecone_id(
                        video_data["id"],
                        result["file_id"]
                    )
                    updated_count += 1
                else:
                    errors.append(f"{video_data['title']}: {result.get('error')}")

            except Exception as e:
                errors.append(f"{video['title']}: {str(e)}")

        return {
            "success": True,
            "message": f"Re-uploaded {updated_count} transcripts to Pinecone with correct user_id",
            "videos_updated": updated_count,
            "videos_skipped": skipped_count,
            "total_videos": len(videos),
            "errors": errors if errors else None
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fix Pinecone metadata: {str(e)}")
