"""
Database Service - Railway PostgreSQL Integration

Handles all database operations using asyncpg and SQLAlchemy async.
"""
import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

# Load environment variables from .env
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(env_path)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey, JSON, select, update, delete, text
from sqlalchemy.dialects.postgresql import UUID

logger = logging.getLogger(__name__)


# SQLAlchemy Base
class Base(DeclarativeBase):
    pass


# =============================================================================
# Database Models (SQLAlchemy ORM)
# =============================================================================

class UserModel(Base):
    """User table"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # NULL for OAuth users
    google_id = Column(String(255), nullable=True, unique=True, index=True)
    authorizer_user_id = Column(String(255), unique=True, nullable=True, index=True)
    auth_provider = Column(String(50), default='legacy')  # 'legacy' or 'authorizer'
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    plan_type = Column(String(20), default="free")
    plan_limits = Column(JSON, default={})
    pinecone_namespace = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VideoGroupModel(Base):
    """Video groups table"""
    __tablename__ = "video_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    color = Column(String(7), default="#3B82F6")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VideoModel(Base):
    """Videos table - stores metadata and transcript for summarization"""
    __tablename__ = "videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(UUID(as_uuid=True), ForeignKey("video_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    youtube_id = Column(String(20), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    channel_name = Column(String(255), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    pinecone_file_id = Column(String(100), nullable=True)
    transcript_length = Column(Integer, nullable=True)
    transcript = Column(Text, nullable=True)  # Raw transcript for summarization
    # Summary caching - stores generated summary to avoid repeated LLM calls
    summary_data = Column(JSON, nullable=True)  # Full structured summary as JSON
    summary_generated_at = Column(DateTime, nullable=True)  # When summary was generated
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SubscriptionModel(Base):
    """Subscriptions table"""
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    paddle_subscription_id = Column(String(100), nullable=True)
    paddle_customer_id = Column(String(100), nullable=True)
    plan = Column(String(20), nullable=False, default="free")
    status = Column(String(20), nullable=False, default="active")
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)
    cancelled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    extra_data = Column(JSON, nullable=True)


class PodcastModel(Base):
    """Podcast transcripts table - stores transcripts from Fireflies, Zoom, etc."""
    __tablename__ = "podcasts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(UUID(as_uuid=True), ForeignKey("video_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    external_id = Column(String(255), nullable=True, index=True)  # Fireflies meeting_id or Zoom recording_id
    source = Column(String(50), nullable=False, default="manual")  # 'fireflies', 'zoom', 'manual'
    title = Column(String(500), nullable=False)
    subject = Column(String(500), nullable=True)  # Podcast subject/topic
    organizer_email = Column(String(255), nullable=True)
    podcast_date = Column(DateTime, nullable=True)  # When the podcast occurred
    duration_minutes = Column(Integer, nullable=True)
    participants = Column(JSON, nullable=True)  # List of participant names/emails
    transcript = Column(Text, nullable=True)
    transcript_length = Column(Integer, nullable=True)
    pinecone_file_id = Column(String(100), nullable=True)
    # Source-specific metadata (audio_url, video_url, action_items, etc.)
    source_metadata = Column(JSON, nullable=True)
    # Summary caching
    summary_data = Column(JSON, nullable=True)
    summary_generated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =============================================================================
# Database Service
# =============================================================================

class DatabaseService:
    """Service for database operations"""

    def __init__(self):
        """Initialize database service"""
        self.engine = None
        self.async_session = None
        self.initialized = False

        # Get database URL - use public URL for local dev, internal for Railway
        self.database_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")

        if self.database_url:
            # Convert postgresql:// to postgresql+asyncpg://
            if self.database_url.startswith("postgresql://"):
                self.database_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    async def initialize(self):
        """Initialize database connection and create tables"""
        if self.initialized:
            return

        if not self.database_url:
            logger.error("DATABASE_URL not set")
            return

        try:
            # Create async engine with connection pool resilience settings
            self.engine = create_async_engine(
                self.database_url,
                echo=os.getenv("DEBUG", "false").lower() == "true",
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,  # Validates connections before use (prevents "connection closed")
                pool_recycle=300,    # Recycle connections every 5 minutes
                pool_timeout=30,     # Timeout for getting connection from pool
            )

            # Create session factory
            self.async_session = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            # Create tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # Run migrations for new columns (safe to run multiple times)
            await self._run_migrations()

            self.initialized = True
            logger.info("Database service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def _run_migrations(self):
        """Run database migrations for new columns"""
        try:
            async with self.engine.begin() as conn:
                # Check if transcript column exists in videos table
                result = await conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'videos' AND column_name = 'transcript'
                """))

                if not result.fetchone():
                    logger.info("Adding 'transcript' column to videos table...")
                    await conn.execute(text("""
                        ALTER TABLE videos ADD COLUMN transcript TEXT
                    """))
                    logger.info("Migration: 'transcript' column added successfully")

                # Check if summary_data column exists in videos table
                result = await conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'videos' AND column_name = 'summary_data'
                """))

                if not result.fetchone():
                    logger.info("Adding 'summary_data' column to videos table...")
                    await conn.execute(text("""
                        ALTER TABLE videos ADD COLUMN summary_data JSONB
                    """))
                    logger.info("Migration: 'summary_data' column added successfully")

                # Check if summary_generated_at column exists in videos table
                result = await conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'videos' AND column_name = 'summary_generated_at'
                """))

                if not result.fetchone():
                    logger.info("Adding 'summary_generated_at' column to videos table...")
                    await conn.execute(text("""
                        ALTER TABLE videos ADD COLUMN summary_generated_at TIMESTAMP
                    """))
                    logger.info("Migration: 'summary_generated_at' column added successfully")

                # Check if authorizer_user_id column exists in users table
                result = await conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'authorizer_user_id'
                """))

                if not result.fetchone():
                    logger.info("Adding 'authorizer_user_id' column to users table...")
                    await conn.execute(text("""
                        ALTER TABLE users ADD COLUMN authorizer_user_id VARCHAR(255) UNIQUE
                    """))
                    await conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS ix_users_authorizer_user_id ON users (authorizer_user_id)
                    """))
                    logger.info("Migration: 'authorizer_user_id' column added successfully")

                # Check if auth_provider column exists in users table
                result = await conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'auth_provider'
                """))

                if not result.fetchone():
                    logger.info("Adding 'auth_provider' column to users table...")
                    await conn.execute(text("""
                        ALTER TABLE users ADD COLUMN auth_provider VARCHAR(50) DEFAULT 'legacy'
                    """))
                    logger.info("Migration: 'auth_provider' column added successfully")

        except Exception as e:
            logger.warning(f"Migration check/run failed (may be ok for new db): {e}")

    async def close(self):
        """Close database connection"""
        if self.engine:
            await self.engine.dispose()
            self.initialized = False
            logger.info("Database connection closed")

    @asynccontextmanager
    async def get_session(self):
        """Get database session context manager"""
        if not self.initialized:
            await self.initialize()

        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # =========================================================================
    # User Operations
    # =========================================================================

    async def create_user(
        self,
        email: str,
        password_hash: Optional[str] = None,
        google_id: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new user"""
        async with self.get_session() as session:
            user_id = uuid.uuid4()
            namespace = f"user_{user_id}"

            user = UserModel(
                id=user_id,
                email=email,
                password_hash=password_hash,
                google_id=google_id,
                first_name=first_name,
                last_name=last_name,
                pinecone_namespace=namespace
            )

            session.add(user)
            await session.flush()

            return {
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "plan_type": user.plan_type,
                "pinecone_namespace": user.pinecone_namespace,
                "created_at": user.created_at
            }

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        async with self.get_session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.email == email)
            )
            user = result.scalar_one_or_none()

            if not user:
                return None

            return self._user_to_dict(user)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        async with self.get_session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.id == uuid.UUID(user_id))
            )
            user = result.scalar_one_or_none()

            if not user:
                return None

            return self._user_to_dict(user)

    async def get_user_by_google_id(self, google_id: str) -> Optional[Dict[str, Any]]:
        """Get user by Google ID"""
        async with self.get_session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.google_id == google_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                return None

            return self._user_to_dict(user)

    async def get_user_by_authorizer_id(self, authorizer_id: str) -> Optional[Dict[str, Any]]:
        """Get user by Authorizer user ID"""
        async with self.get_session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.authorizer_user_id == authorizer_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                return None

            return self._user_to_dict(user)

    async def create_user_from_authorizer(
        self,
        authorizer_user_id: str,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create TubeVibe user from Authorizer authentication"""
        async with self.get_session() as session:
            user_id = uuid.uuid4()
            pinecone_namespace = f"user_{user_id}"

            user = UserModel(
                id=user_id,
                email=email,
                authorizer_user_id=authorizer_user_id,
                auth_provider='authorizer',
                first_name=first_name,
                last_name=last_name,
                pinecone_namespace=pinecone_namespace
            )

            session.add(user)
            await session.flush()

            return {
                "id": str(user.id),
                "email": user.email,
                "authorizer_user_id": user.authorizer_user_id,
                "auth_provider": user.auth_provider,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "plan_type": user.plan_type,
                "pinecone_namespace": user.pinecone_namespace,
                "created_at": user.created_at
            }

    async def link_authorizer_user(self, user_id: str, authorizer_user_id: str) -> bool:
        """Link existing user to Authorizer user ID"""
        async with self.get_session() as session:
            result = await session.execute(
                update(UserModel)
                .where(UserModel.id == uuid.UUID(user_id))
                .values(
                    authorizer_user_id=authorizer_user_id,
                    auth_provider='authorizer',
                    updated_at=datetime.utcnow()
                )
            )
            return result.rowcount > 0

    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """Update user fields"""
        async with self.get_session() as session:
            updates["updated_at"] = datetime.utcnow()
            await session.execute(
                update(UserModel)
                .where(UserModel.id == uuid.UUID(user_id))
                .values(**updates)
            )
            return True

    async def update_user_by_email(self, email: str, updates: Dict[str, Any]) -> bool:
        """Update user fields by email address"""
        async with self.get_session() as session:
            updates["updated_at"] = datetime.utcnow()
            result = await session.execute(
                update(UserModel)
                .where(UserModel.email == email.lower())
                .values(**updates)
            )
            return result.rowcount > 0

    def _user_to_dict(self, user: UserModel) -> Dict[str, Any]:
        """Convert user model to dictionary"""
        return {
            "id": str(user.id),
            "email": user.email,
            "password_hash": user.password_hash,
            "google_id": user.google_id,
            "authorizer_user_id": user.authorizer_user_id,
            "auth_provider": user.auth_provider,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "plan_type": user.plan_type,
            "plan_limits": user.plan_limits,
            "pinecone_namespace": user.pinecone_namespace,
            "created_at": user.created_at,
            "updated_at": user.updated_at
        }

    # =========================================================================
    # Video Operations
    # =========================================================================

    async def create_video(
        self,
        user_id: str,
        youtube_id: str,
        title: str,
        channel_name: Optional[str] = None,
        duration_seconds: Optional[int] = None,
        thumbnail_url: Optional[str] = None,
        pinecone_file_id: Optional[str] = None,
        transcript_length: Optional[int] = None,
        transcript: Optional[str] = None,
        group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new video entry"""
        async with self.get_session() as session:
            video = VideoModel(
                user_id=uuid.UUID(user_id),
                youtube_id=youtube_id,
                title=title,
                channel_name=channel_name,
                duration_seconds=duration_seconds,
                thumbnail_url=thumbnail_url,
                pinecone_file_id=pinecone_file_id,
                transcript_length=transcript_length,
                transcript=transcript,
                group_id=uuid.UUID(group_id) if group_id else None
            )

            session.add(video)
            await session.flush()

            return self._video_to_dict(video)

    async def get_video(
        self, video_id: str, user_id: str, include_transcript: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Get video by ID (with user ownership check)"""
        async with self.get_session() as session:
            result = await session.execute(
                select(VideoModel).where(
                    VideoModel.id == uuid.UUID(video_id),
                    VideoModel.user_id == uuid.UUID(user_id)
                )
            )
            video = result.scalar_one_or_none()

            if not video:
                return None

            return self._video_to_dict(video, include_transcript=include_transcript)

    async def get_video_by_youtube_id(
        self, user_id: str, youtube_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get video by YouTube ID for a specific user (for duplicate checking)"""
        async with self.get_session() as session:
            result = await session.execute(
                select(VideoModel).where(
                    VideoModel.youtube_id == youtube_id,
                    VideoModel.user_id == uuid.UUID(user_id)
                )
            )
            video = result.scalar_one_or_none()

            if not video:
                return None

            return self._video_to_dict(video)

    async def list_videos(
        self,
        user_id: str,
        group_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 20
    ) -> Dict[str, Any]:
        """List videos for a user"""
        async with self.get_session() as session:
            query = select(VideoModel).where(VideoModel.user_id == uuid.UUID(user_id))

            if group_id:
                query = query.where(VideoModel.group_id == uuid.UUID(group_id))

            # Get total count
            count_result = await session.execute(
                select(VideoModel.id).where(VideoModel.user_id == uuid.UUID(user_id))
            )
            total = len(count_result.all())

            # Get paginated results
            query = query.order_by(VideoModel.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(query)
            videos = result.scalars().all()

            return {
                "videos": [self._video_to_dict(v) for v in videos],
                "total": total,
                "offset": offset,
                "limit": limit
            }

    async def delete_video(self, video_id: str, user_id: str) -> bool:
        """Delete a video"""
        async with self.get_session() as session:
            await session.execute(
                delete(VideoModel).where(
                    VideoModel.id == uuid.UUID(video_id),
                    VideoModel.user_id == uuid.UUID(user_id)
                )
            )
            return True

    async def update_video_group(self, video_id: str, user_id: str, group_id: Optional[str]) -> bool:
        """Move video to a different group"""
        async with self.get_session() as session:
            await session.execute(
                update(VideoModel)
                .where(
                    VideoModel.id == uuid.UUID(video_id),
                    VideoModel.user_id == uuid.UUID(user_id)
                )
                .values(
                    group_id=uuid.UUID(group_id) if group_id else None,
                    updated_at=datetime.utcnow()
                )
            )
            return True

    async def update_video_pinecone_id(self, video_id: str, pinecone_file_id: str) -> bool:
        """Update video's Pinecone file ID after re-upload"""
        async with self.get_session() as session:
            await session.execute(
                update(VideoModel)
                .where(VideoModel.id == uuid.UUID(video_id))
                .values(
                    pinecone_file_id=pinecone_file_id,
                    updated_at=datetime.utcnow()
                )
            )
            return True

    async def save_video_summary(
        self,
        video_id: str,
        user_id: str,
        summary_data: Dict[str, Any]
    ) -> bool:
        """
        Save generated summary to database for caching.

        Args:
            video_id: The video UUID
            user_id: The user UUID (for ownership verification)
            summary_data: The full structured summary dict

        Returns:
            True if saved successfully
        """
        async with self.get_session() as session:
            result = await session.execute(
                update(VideoModel)
                .where(
                    VideoModel.id == uuid.UUID(video_id),
                    VideoModel.user_id == uuid.UUID(user_id)
                )
                .values(
                    summary_data=summary_data,
                    summary_generated_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            )
            return result.rowcount > 0

    async def get_video_summary(
        self,
        video_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached summary for a video.

        Args:
            video_id: The video UUID
            user_id: The user UUID (for ownership verification)

        Returns:
            Dict with summary_data and summary_generated_at, or None if no summary exists
        """
        async with self.get_session() as session:
            result = await session.execute(
                select(
                    VideoModel.summary_data,
                    VideoModel.summary_generated_at,
                    VideoModel.title
                ).where(
                    VideoModel.id == uuid.UUID(video_id),
                    VideoModel.user_id == uuid.UUID(user_id)
                )
            )
            row = result.fetchone()

            if not row or row.summary_data is None:
                return None

            return {
                "summary_data": row.summary_data,
                "summary_generated_at": row.summary_generated_at,
                "video_title": row.title
            }

    async def clear_video_summary(self, video_id: str, user_id: str) -> bool:
        """
        Clear cached summary for a video (useful before regeneration).

        Args:
            video_id: The video UUID
            user_id: The user UUID (for ownership verification)

        Returns:
            True if cleared successfully
        """
        async with self.get_session() as session:
            await session.execute(
                update(VideoModel)
                .where(
                    VideoModel.id == uuid.UUID(video_id),
                    VideoModel.user_id == uuid.UUID(user_id)
                )
                .values(
                    summary_data=None,
                    summary_generated_at=None,
                    updated_at=datetime.utcnow()
                )
            )
            return True

    def _video_to_dict(
        self,
        video: VideoModel,
        include_transcript: bool = False,
        include_summary: bool = False
    ) -> Dict[str, Any]:
        """Convert video model to dictionary"""
        result = {
            "id": str(video.id),
            "user_id": str(video.user_id),
            "group_id": str(video.group_id) if video.group_id else None,
            "youtube_id": video.youtube_id,
            "title": video.title,
            "channel_name": video.channel_name,
            "duration_seconds": video.duration_seconds,
            "thumbnail_url": video.thumbnail_url,
            "pinecone_file_id": video.pinecone_file_id,
            "transcript_length": video.transcript_length,
            "has_summary": video.summary_data is not None,
            "summary_generated_at": video.summary_generated_at,
            "created_at": video.created_at,
            "updated_at": video.updated_at
        }
        if include_transcript:
            result["transcript"] = video.transcript
        if include_summary:
            result["summary_data"] = video.summary_data
        return result

    # =========================================================================
    # Group Operations
    # =========================================================================

    async def create_group(
        self,
        user_id: str,
        name: str,
        description: Optional[str] = None,
        color: str = "#3B82F6"
    ) -> Dict[str, Any]:
        """Create a new video group"""
        async with self.get_session() as session:
            group = VideoGroupModel(
                user_id=uuid.UUID(user_id),
                name=name,
                description=description,
                color=color
            )

            session.add(group)
            await session.flush()

            return self._group_to_dict(group)

    async def list_groups(self, user_id: str) -> List[Dict[str, Any]]:
        """List groups for a user"""
        async with self.get_session() as session:
            result = await session.execute(
                select(VideoGroupModel)
                .where(VideoGroupModel.user_id == uuid.UUID(user_id))
                .order_by(VideoGroupModel.name)
            )
            groups = result.scalars().all()

            return [self._group_to_dict(g) for g in groups]

    async def get_group(self, group_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get group by ID"""
        async with self.get_session() as session:
            result = await session.execute(
                select(VideoGroupModel).where(
                    VideoGroupModel.id == uuid.UUID(group_id),
                    VideoGroupModel.user_id == uuid.UUID(user_id)
                )
            )
            group = result.scalar_one_or_none()

            if not group:
                return None

            return self._group_to_dict(group)

    async def update_group(self, group_id: str, user_id: str, updates: Dict[str, Any]) -> bool:
        """Update group fields"""
        async with self.get_session() as session:
            updates["updated_at"] = datetime.utcnow()
            await session.execute(
                update(VideoGroupModel)
                .where(
                    VideoGroupModel.id == uuid.UUID(group_id),
                    VideoGroupModel.user_id == uuid.UUID(user_id)
                )
                .values(**updates)
            )
            return True

    async def delete_group(self, group_id: str, user_id: str) -> bool:
        """Delete a group (videos become ungrouped)"""
        async with self.get_session() as session:
            await session.execute(
                delete(VideoGroupModel).where(
                    VideoGroupModel.id == uuid.UUID(group_id),
                    VideoGroupModel.user_id == uuid.UUID(user_id)
                )
            )
            return True

    def _group_to_dict(self, group: VideoGroupModel) -> Dict[str, Any]:
        """Convert group model to dictionary"""
        return {
            "id": str(group.id),
            "user_id": str(group.user_id),
            "name": group.name,
            "description": group.description,
            "color": group.color,
            "created_at": group.created_at,
            "updated_at": group.updated_at
        }

    # =========================================================================
    # Subscription Operations
    # =========================================================================

    async def get_subscription(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's subscription"""
        async with self.get_session() as session:
            result = await session.execute(
                select(SubscriptionModel).where(SubscriptionModel.user_id == uuid.UUID(user_id))
            )
            sub = result.scalar_one_or_none()

            if not sub:
                return None

            return self._subscription_to_dict(sub)

    async def create_or_update_subscription(
        self,
        user_id: str,
        plan: str,
        status: str,
        paddle_subscription_id: Optional[str] = None,
        paddle_customer_id: Optional[str] = None,
        current_period_start: Optional[datetime] = None,
        current_period_end: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Create or update subscription"""
        async with self.get_session() as session:
            # Check if subscription exists
            result = await session.execute(
                select(SubscriptionModel).where(SubscriptionModel.user_id == uuid.UUID(user_id))
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing
                existing.plan = plan
                existing.status = status
                existing.paddle_subscription_id = paddle_subscription_id
                existing.paddle_customer_id = paddle_customer_id
                existing.current_period_start = current_period_start
                existing.current_period_end = current_period_end
                existing.updated_at = datetime.utcnow()
                await session.flush()
                return self._subscription_to_dict(existing)
            else:
                # Create new
                sub = SubscriptionModel(
                    user_id=uuid.UUID(user_id),
                    plan=plan,
                    status=status,
                    paddle_subscription_id=paddle_subscription_id,
                    paddle_customer_id=paddle_customer_id,
                    current_period_start=current_period_start,
                    current_period_end=current_period_end
                )
                session.add(sub)
                await session.flush()
                return self._subscription_to_dict(sub)

    async def get_subscription_by_paddle_id(self, paddle_subscription_id: str) -> Optional[Dict[str, Any]]:
        """Get subscription by Paddle subscription ID"""
        async with self.get_session() as session:
            result = await session.execute(
                select(SubscriptionModel).where(
                    SubscriptionModel.paddle_subscription_id == paddle_subscription_id
                )
            )
            sub = result.scalar_one_or_none()
            return self._subscription_to_dict(sub) if sub else None

    async def update_subscription_by_paddle_id(
        self,
        paddle_subscription_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """Update subscription by Paddle subscription ID"""
        async with self.get_session() as session:
            updates["updated_at"] = datetime.utcnow()
            result = await session.execute(
                update(SubscriptionModel)
                .where(SubscriptionModel.paddle_subscription_id == paddle_subscription_id)
                .values(**updates)
            )
            return result.rowcount > 0

    async def get_user_by_paddle_subscription_id(self, paddle_subscription_id: str) -> Optional[Dict[str, Any]]:
        """Get user by their Paddle subscription ID"""
        async with self.get_session() as session:
            # First find the subscription
            result = await session.execute(
                select(SubscriptionModel).where(
                    SubscriptionModel.paddle_subscription_id == paddle_subscription_id
                )
            )
            sub = result.scalar_one_or_none()
            if not sub:
                return None

            # Then get the user
            user_result = await session.execute(
                select(UserModel).where(UserModel.id == sub.user_id)
            )
            user = user_result.scalar_one_or_none()
            return self._user_to_dict(user) if user else None

    def _subscription_to_dict(self, sub: SubscriptionModel) -> Dict[str, Any]:
        """Convert subscription model to dictionary"""
        return {
            "id": str(sub.id),
            "user_id": str(sub.user_id),
            "paddle_subscription_id": sub.paddle_subscription_id,
            "paddle_customer_id": sub.paddle_customer_id,
            "plan": sub.plan,
            "status": sub.status,
            "current_period_start": sub.current_period_start,
            "current_period_end": sub.current_period_end,
            "cancel_at_period_end": sub.cancel_at_period_end,
            "cancelled_at": sub.cancelled_at,
            "created_at": sub.created_at,
            "updated_at": sub.updated_at
        }

    # =========================================================================
    # Podcast Transcript Operations
    # =========================================================================

    async def create_podcast(
        self,
        user_id: str,
        title: str,
        source: str = "manual",
        external_id: Optional[str] = None,
        subject: Optional[str] = None,
        organizer_email: Optional[str] = None,
        podcast_date: Optional[datetime] = None,
        duration_minutes: Optional[int] = None,
        participants: Optional[List[str]] = None,
        transcript: Optional[str] = None,
        pinecone_file_id: Optional[str] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
        group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new podcast transcript entry"""
        async with self.get_session() as session:
            podcast = PodcastModel(
                user_id=uuid.UUID(user_id),
                external_id=external_id,
                source=source,
                title=title,
                subject=subject,
                organizer_email=organizer_email,
                podcast_date=podcast_date,
                duration_minutes=duration_minutes,
                participants=participants or [],
                transcript=transcript,
                transcript_length=len(transcript) if transcript else 0,
                pinecone_file_id=pinecone_file_id,
                source_metadata=source_metadata,
                group_id=uuid.UUID(group_id) if group_id else None
            )

            session.add(podcast)
            await session.flush()

            return self._podcast_to_dict(podcast)

    async def get_podcast(
        self, podcast_id: str, user_id: str, include_transcript: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Get podcast by ID (with user ownership check)"""
        async with self.get_session() as session:
            result = await session.execute(
                select(PodcastModel).where(
                    PodcastModel.id == uuid.UUID(podcast_id),
                    PodcastModel.user_id == uuid.UUID(user_id)
                )
            )
            podcast = result.scalar_one_or_none()

            if not podcast:
                return None

            return self._podcast_to_dict(podcast, include_transcript=include_transcript)

    async def get_podcast_by_external_id(
        self, user_id: str, external_id: str, source: str
    ) -> Optional[Dict[str, Any]]:
        """Get podcast by external ID for a specific user (for duplicate checking)"""
        async with self.get_session() as session:
            result = await session.execute(
                select(PodcastModel).where(
                    PodcastModel.external_id == external_id,
                    PodcastModel.source == source,
                    PodcastModel.user_id == uuid.UUID(user_id)
                )
            )
            podcast = result.scalar_one_or_none()

            if not podcast:
                return None

            return self._podcast_to_dict(podcast)

    async def list_podcasts(
        self,
        user_id: str,
        group_id: Optional[str] = None,
        source: Optional[str] = None,
        offset: int = 0,
        limit: int = 20
    ) -> Dict[str, Any]:
        """List podcasts for a user"""
        async with self.get_session() as session:
            query = select(PodcastModel).where(PodcastModel.user_id == uuid.UUID(user_id))

            if group_id:
                query = query.where(PodcastModel.group_id == uuid.UUID(group_id))

            if source:
                query = query.where(PodcastModel.source == source)

            # Get total count
            count_query = select(PodcastModel.id).where(PodcastModel.user_id == uuid.UUID(user_id))
            if group_id:
                count_query = count_query.where(PodcastModel.group_id == uuid.UUID(group_id))
            if source:
                count_query = count_query.where(PodcastModel.source == source)

            count_result = await session.execute(count_query)
            total = len(count_result.all())

            # Get paginated results
            query = query.order_by(PodcastModel.podcast_date.desc().nulls_last(), PodcastModel.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(query)
            podcasts = result.scalars().all()

            return {
                "podcasts": [self._podcast_to_dict(m) for m in podcasts],
                "total": total,
                "offset": offset,
                "limit": limit
            }

    async def delete_podcast(self, podcast_id: str, user_id: str) -> bool:
        """Delete a podcast"""
        async with self.get_session() as session:
            await session.execute(
                delete(PodcastModel).where(
                    PodcastModel.id == uuid.UUID(podcast_id),
                    PodcastModel.user_id == uuid.UUID(user_id)
                )
            )
            return True

    async def update_podcast_group(self, podcast_id: str, user_id: str, group_id: Optional[str]) -> bool:
        """Move podcast to a different group"""
        async with self.get_session() as session:
            await session.execute(
                update(PodcastModel)
                .where(
                    PodcastModel.id == uuid.UUID(podcast_id),
                    PodcastModel.user_id == uuid.UUID(user_id)
                )
                .values(
                    group_id=uuid.UUID(group_id) if group_id else None,
                    updated_at=datetime.utcnow()
                )
            )
            return True

    async def update_podcast_pinecone_id(self, podcast_id: str, pinecone_file_id: str) -> bool:
        """Update podcast's Pinecone file ID after upload"""
        async with self.get_session() as session:
            await session.execute(
                update(PodcastModel)
                .where(PodcastModel.id == uuid.UUID(podcast_id))
                .values(
                    pinecone_file_id=pinecone_file_id,
                    updated_at=datetime.utcnow()
                )
            )
            return True

    async def save_podcast_summary(
        self,
        podcast_id: str,
        user_id: str,
        summary_data: Dict[str, Any]
    ) -> bool:
        """Save generated summary to database for caching"""
        async with self.get_session() as session:
            result = await session.execute(
                update(PodcastModel)
                .where(
                    PodcastModel.id == uuid.UUID(podcast_id),
                    PodcastModel.user_id == uuid.UUID(user_id)
                )
                .values(
                    summary_data=summary_data,
                    summary_generated_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            )
            return result.rowcount > 0

    async def get_podcast_summary(
        self,
        podcast_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached summary for a podcast"""
        async with self.get_session() as session:
            result = await session.execute(
                select(
                    PodcastModel.summary_data,
                    PodcastModel.summary_generated_at,
                    PodcastModel.title,
                    PodcastModel.subject,
                    PodcastModel.podcast_date,
                    PodcastModel.participants
                ).where(
                    PodcastModel.id == uuid.UUID(podcast_id),
                    PodcastModel.user_id == uuid.UUID(user_id)
                )
            )
            row = result.fetchone()

            if not row or row.summary_data is None:
                return None

            return {
                "summary_data": row.summary_data,
                "summary_generated_at": row.summary_generated_at,
                "podcast_title": row.title,
                "podcast_subject": row.subject,
                "podcast_date": row.podcast_date,
                "participants": row.participants
            }

    def _podcast_to_dict(
        self,
        podcast: PodcastModel,
        include_transcript: bool = False,
        include_summary: bool = False
    ) -> Dict[str, Any]:
        """Convert podcast model to dictionary"""
        result = {
            "id": str(podcast.id),
            "user_id": str(podcast.user_id),
            "group_id": str(podcast.group_id) if podcast.group_id else None,
            "external_id": podcast.external_id,
            "source": podcast.source,
            "title": podcast.title,
            "subject": podcast.subject,
            "organizer_email": podcast.organizer_email,
            "podcast_date": podcast.podcast_date,
            "duration_minutes": podcast.duration_minutes,
            "participants": podcast.participants or [],
            "transcript_length": podcast.transcript_length,
            "pinecone_file_id": podcast.pinecone_file_id,
            "source_metadata": podcast.source_metadata,
            "has_summary": podcast.summary_data is not None,
            "summary_generated_at": podcast.summary_generated_at,
            "created_at": podcast.created_at,
            "updated_at": podcast.updated_at
        }
        if include_transcript:
            result["transcript"] = podcast.transcript
        if include_summary:
            result["summary_data"] = podcast.summary_data
        return result


# =============================================================================
# Singleton Instance
# =============================================================================

_database_service: Optional[DatabaseService] = None


async def get_database_service() -> DatabaseService:
    """Get or create database service singleton"""
    global _database_service
    if _database_service is None:
        _database_service = DatabaseService()
        await _database_service.initialize()
    return _database_service
