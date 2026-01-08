"""
Migration script to rename meetings table to podcasts
Run via: railway run python -m scripts.migrate_meetings_to_podcasts
"""
import os
import asyncio
import asyncpg

async def migrate():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return

    print(f"Connecting to database...")
    conn = await asyncpg.connect(database_url)

    try:
        # Check if meetings table exists
        result = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'meetings')"
        )

        if not result:
            print("Table 'meetings' does not exist. Checking if 'podcasts' already exists...")
            podcasts_exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'podcasts')"
            )
            if podcasts_exists:
                print("Table 'podcasts' already exists. Migration not needed.")
            else:
                print("Neither 'meetings' nor 'podcasts' table exists.")
            return

        print("Renaming table 'meetings' to 'podcasts'...")
        await conn.execute("ALTER TABLE meetings RENAME TO podcasts")
        print("Table renamed successfully.")

        # Check if meeting_date column exists
        col_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'podcasts' AND column_name = 'meeting_date')"
        )

        if col_exists:
            print("Renaming column 'meeting_date' to 'podcast_date'...")
            await conn.execute("ALTER TABLE podcasts RENAME COLUMN meeting_date TO podcast_date")
            print("Column renamed successfully.")
        else:
            print("Column 'meeting_date' does not exist (may already be renamed).")

        print("Migration completed successfully!")

    except Exception as e:
        print(f"ERROR: {e}")
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate())
