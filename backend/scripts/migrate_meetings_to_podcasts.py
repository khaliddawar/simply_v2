"""
Migration script to migrate data from meetings table to podcasts
Run via: railway run --service Postgres python -m scripts.migrate_meetings_to_podcasts
"""
import os
import asyncio
import asyncpg

async def migrate():
    # Use public URL for local access, internal URL for Railway
    database_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return

    print("Connecting to database...")
    conn = await asyncpg.connect(database_url)

    try:
        # Check if both tables exist
        meetings_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'meetings')"
        )
        podcasts_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'podcasts')"
        )

        print(f"Table status: meetings={meetings_exists}, podcasts={podcasts_exists}")

        if not meetings_exists and not podcasts_exists:
            print("Neither table exists. Nothing to migrate.")
            return

        if not meetings_exists and podcasts_exists:
            print("Only 'podcasts' table exists. Migration already complete.")
            return

        if meetings_exists and not podcasts_exists:
            # Simple case: just rename the table
            print("Renaming table 'meetings' to 'podcasts'...")
            await conn.execute("ALTER TABLE meetings RENAME TO podcasts")
            print("Table renamed successfully.")

            # Rename column
            print("Renaming column 'meeting_date' to 'podcast_date'...")
            await conn.execute("ALTER TABLE podcasts RENAME COLUMN meeting_date TO podcast_date")
            print("Column renamed successfully.")
            print("Migration completed!")
            return

        # Both tables exist - migrate data from meetings to podcasts
        print("Both tables exist. Migrating data from 'meetings' to 'podcasts'...")

        # Count records in meetings
        meetings_count = await conn.fetchval("SELECT COUNT(*) FROM meetings")
        print(f"Found {meetings_count} records in 'meetings' table")

        if meetings_count > 0:
            # Migrate data - map meeting_date to podcast_date
            print("Copying data from 'meetings' to 'podcasts'...")
            await conn.execute("""
                INSERT INTO podcasts (
                    id, user_id, group_id, external_id, source, title, subject,
                    organizer_email, podcast_date, duration_minutes, participants,
                    transcript, transcript_length, pinecone_file_id, source_metadata,
                    summary_data, summary_generated_at, created_at, updated_at
                )
                SELECT
                    id, user_id, group_id, external_id, source, title, subject,
                    organizer_email, meeting_date, duration_minutes, participants,
                    transcript, transcript_length, pinecone_file_id, source_metadata,
                    summary_data, summary_generated_at, created_at, updated_at
                FROM meetings
                ON CONFLICT (id) DO NOTHING
            """)
            print(f"Data migration completed.")

        # Drop the old meetings table
        print("Dropping old 'meetings' table...")
        await conn.execute("DROP TABLE meetings")
        print("Old table dropped.")

        print("Migration completed successfully!")

    except Exception as e:
        print(f"ERROR: {e}")
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate())
