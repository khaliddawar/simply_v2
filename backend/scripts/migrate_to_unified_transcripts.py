"""
Migration script: videos + podcasts -> transcripts

This script migrates data from the separate 'videos' and 'podcasts' tables
to the new unified 'transcripts' table.

The migration:
1. Creates the 'transcripts' table if it doesn't exist
2. Migrates all rows from 'videos' table (source_type='youtube')
3. Migrates all rows from 'podcasts' table (source_type from the source column)
4. Preserves all IDs, pinecone_file_ids, and summary_data
5. Builds metadata JSON from source-specific fields
6. Verifies counts match after migration
7. Does NOT delete old tables (keep for rollback safety)

Run with:
    cd backend
    python -m scripts.migrate_to_unified_transcripts

Or on Railway:
    railway run python -m scripts.migrate_to_unified_transcripts
"""
import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv
import asyncpg

# Load environment variables from project root
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


async def create_transcripts_table(conn: asyncpg.Connection) -> bool:
    """
    Create the transcripts table if it doesn't exist.

    Returns True if table was created, False if it already exists.
    """
    # Check if table exists
    exists = await conn.fetchval(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'transcripts')"
    )

    if exists:
        print("Table 'transcripts' already exists.")
        return False

    print("Creating 'transcripts' table...")

    # Create the table
    await conn.execute("""
        CREATE TABLE transcripts (
            -- Identity
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            group_id UUID REFERENCES video_groups(id) ON DELETE SET NULL,

            -- Source identification
            source_type VARCHAR(50) NOT NULL,
            external_id VARCHAR(255),

            -- Core content
            title VARCHAR(500) NOT NULL,
            transcript_text TEXT,
            transcript_length INTEGER,

            -- Pinecone integration
            pinecone_file_id VARCHAR(100),

            -- Summary cache
            summary_data JSONB,
            summary_generated_at TIMESTAMP WITH TIME ZONE,

            -- Source-specific metadata (flexible JSON)
            metadata JSONB DEFAULT '{}',

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

            -- Constraints
            UNIQUE(user_id, source_type, external_id)
        )
    """)

    # Create indexes for common queries
    print("Creating indexes on 'transcripts' table...")
    await conn.execute("CREATE INDEX idx_transcripts_user_id ON transcripts(user_id)")
    await conn.execute("CREATE INDEX idx_transcripts_group_id ON transcripts(group_id)")
    await conn.execute("CREATE INDEX idx_transcripts_source_type ON transcripts(source_type)")
    await conn.execute("CREATE INDEX idx_transcripts_created_at ON transcripts(created_at DESC)")
    await conn.execute("CREATE INDEX idx_transcripts_user_source ON transcripts(user_id, source_type)")
    await conn.execute("CREATE INDEX idx_transcripts_external_id ON transcripts(external_id)")

    print("Table 'transcripts' created successfully.")
    return True


async def migrate_videos(conn: asyncpg.Connection) -> int:
    """
    Migrate all videos to transcripts table.

    Returns the number of migrated rows.
    """
    # Check if videos table exists
    videos_exists = await conn.fetchval(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'videos')"
    )

    if not videos_exists:
        print("Table 'videos' does not exist. Skipping video migration.")
        return 0

    # Count videos
    video_count = await conn.fetchval("SELECT COUNT(*) FROM videos")
    print(f"Found {video_count} videos to migrate.")

    if video_count == 0:
        return 0

    # Fetch all videos
    videos = await conn.fetch("SELECT * FROM videos")

    migrated = 0
    skipped = 0

    for video in videos:
        # Build metadata JSON from video-specific fields
        metadata = {
            "youtube_id": video['youtube_id'],
            "channel_name": video['channel_name'],
            "duration_seconds": video['duration_seconds'],
            "thumbnail_url": video['thumbnail_url']
        }
        # Remove None values from metadata
        metadata = {k: v for k, v in metadata.items() if v is not None}

        try:
            await conn.execute("""
                INSERT INTO transcripts (
                    id, user_id, group_id, source_type, external_id,
                    title, transcript_text, transcript_length,
                    pinecone_file_id, summary_data, summary_generated_at,
                    metadata, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, 'youtube', $4,
                    $5, $6, $7,
                    $8, $9, $10,
                    $11, $12, $13
                )
                ON CONFLICT (user_id, source_type, external_id) DO NOTHING
            """,
                video['id'],
                video['user_id'],
                video['group_id'],
                video['youtube_id'],  # external_id = youtube_id
                video['title'],
                video['transcript'],  # transcript_text = transcript
                video['transcript_length'],
                video['pinecone_file_id'],
                json.dumps(video['summary_data']) if video['summary_data'] else None,
                video['summary_generated_at'],
                json.dumps(metadata),
                video['created_at'],
                video['updated_at']
            )
            migrated += 1
        except Exception as e:
            print(f"  Warning: Failed to migrate video {video['id']}: {e}")
            skipped += 1

    print(f"  Migrated {migrated} videos, skipped {skipped} (duplicates or errors).")
    return migrated


async def migrate_podcasts(conn: asyncpg.Connection) -> int:
    """
    Migrate all podcasts to transcripts table.

    Returns the number of migrated rows.
    """
    # Check if podcasts table exists
    podcasts_exists = await conn.fetchval(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'podcasts')"
    )

    if not podcasts_exists:
        print("Table 'podcasts' does not exist. Skipping podcast migration.")
        return 0

    # Count podcasts
    podcast_count = await conn.fetchval("SELECT COUNT(*) FROM podcasts")
    print(f"Found {podcast_count} podcasts to migrate.")

    if podcast_count == 0:
        return 0

    # Fetch all podcasts
    podcasts = await conn.fetch("SELECT * FROM podcasts")

    migrated = 0
    skipped = 0

    for podcast in podcasts:
        # Determine source_type from the 'source' column
        # The podcasts table has a 'source' column with values like 'fireflies', 'zoom', 'manual'
        source_type = podcast['source'] or 'manual'

        # Build metadata JSON from podcast-specific fields
        metadata = {
            "subject": podcast['subject'],
            "organizer_email": podcast['organizer_email'],
            "meeting_date": podcast['podcast_date'].isoformat() if podcast['podcast_date'] else None,
            "duration_minutes": podcast['duration_minutes'],
            "participants": podcast['participants'],
            "source_metadata": podcast['source_metadata']
        }
        # Remove None values from metadata
        metadata = {k: v for k, v in metadata.items() if v is not None}

        try:
            await conn.execute("""
                INSERT INTO transcripts (
                    id, user_id, group_id, source_type, external_id,
                    title, transcript_text, transcript_length,
                    pinecone_file_id, summary_data, summary_generated_at,
                    metadata, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8,
                    $9, $10, $11,
                    $12, $13, $14
                )
                ON CONFLICT (user_id, source_type, external_id) DO NOTHING
            """,
                podcast['id'],
                podcast['user_id'],
                podcast['group_id'],
                source_type,
                podcast['external_id'],
                podcast['title'],
                podcast['transcript'],  # transcript_text = transcript
                podcast['transcript_length'],
                podcast['pinecone_file_id'],
                json.dumps(podcast['summary_data']) if podcast['summary_data'] else None,
                podcast['summary_generated_at'],
                json.dumps(metadata),
                podcast['created_at'],
                podcast['updated_at']
            )
            migrated += 1
        except Exception as e:
            print(f"  Warning: Failed to migrate podcast {podcast['id']}: {e}")
            skipped += 1

    print(f"  Migrated {migrated} podcasts, skipped {skipped} (duplicates or errors).")
    return migrated


async def verify_migration(conn: asyncpg.Connection) -> bool:
    """
    Verify that the migration was successful by comparing counts.

    Returns True if verification passes.
    """
    print("\nVerifying migration...")

    # Count original records
    videos_count = 0
    podcasts_count = 0

    videos_exists = await conn.fetchval(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'videos')"
    )
    if videos_exists:
        videos_count = await conn.fetchval("SELECT COUNT(*) FROM videos")

    podcasts_exists = await conn.fetchval(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'podcasts')"
    )
    if podcasts_exists:
        podcasts_count = await conn.fetchval("SELECT COUNT(*) FROM podcasts")

    old_total = videos_count + podcasts_count

    # Count new records
    new_count = await conn.fetchval("SELECT COUNT(*) FROM transcripts")

    print(f"  Original videos:   {videos_count}")
    print(f"  Original podcasts: {podcasts_count}")
    print(f"  Expected total:    {old_total}")
    print(f"  New transcripts:   {new_count}")

    if new_count >= old_total:
        print(f"  PASS: Migration count verified ({new_count} >= {old_total})")
        return True
    else:
        print(f"  WARNING: Count mismatch - some records may have been skipped")
        print(f"           This could be due to duplicate entries or migration errors")
        return False


async def show_summary(conn: asyncpg.Connection):
    """Show a summary of the transcripts table after migration."""
    print("\n--- Migration Summary ---")

    # Count by source_type
    result = await conn.fetch("""
        SELECT source_type, COUNT(*) as count
        FROM transcripts
        GROUP BY source_type
        ORDER BY count DESC
    """)

    print("\nTranscripts by source type:")
    for row in result:
        print(f"  {row['source_type']}: {row['count']}")

    # Total count
    total = await conn.fetchval("SELECT COUNT(*) FROM transcripts")
    print(f"\nTotal transcripts: {total}")

    # Check for transcripts with summaries
    with_summary = await conn.fetchval(
        "SELECT COUNT(*) FROM transcripts WHERE summary_data IS NOT NULL"
    )
    print(f"Transcripts with summaries: {with_summary}")

    # Check for transcripts with Pinecone IDs
    with_pinecone = await conn.fetchval(
        "SELECT COUNT(*) FROM transcripts WHERE pinecone_file_id IS NOT NULL"
    )
    print(f"Transcripts in Pinecone: {with_pinecone}")


async def migrate():
    """Main migration function."""
    # Get database URL
    database_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")

    if not database_url:
        print("ERROR: DATABASE_URL not set")
        print("Please set DATABASE_URL or DATABASE_PUBLIC_URL environment variable")
        return

    print("=" * 60)
    print("Unified Transcripts Migration")
    print("=" * 60)
    print("\nConnecting to database...")

    conn = await asyncpg.connect(database_url)

    try:
        # Step 1: Create transcripts table
        print("\n--- Step 1: Create transcripts table ---")
        await create_transcripts_table(conn)

        # Step 2: Migrate videos
        print("\n--- Step 2: Migrate videos ---")
        videos_migrated = await migrate_videos(conn)

        # Step 3: Migrate podcasts
        print("\n--- Step 3: Migrate podcasts ---")
        podcasts_migrated = await migrate_podcasts(conn)

        # Step 4: Verify migration
        print("\n--- Step 4: Verify migration ---")
        await verify_migration(conn)

        # Show summary
        await show_summary(conn)

        print("\n" + "=" * 60)
        print("Migration completed!")
        print("=" * 60)
        print("\nIMPORTANT: Old tables (videos, podcasts) have been preserved for rollback safety.")
        print("Once you've verified everything works, you can manually drop them if desired:")
        print("  DROP TABLE videos;")
        print("  DROP TABLE podcasts;")

    except Exception as e:
        print(f"\nERROR: Migration failed: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
