"""
Migration Script: Add transcript column to videos table

Run this script once to add the transcript column to existing databases.
New databases will have the column created automatically via SQLAlchemy.

Usage:
    cd backend
    python -m scripts.add_transcript_column
"""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


async def add_transcript_column():
    """Add transcript column to videos table if it doesn't exist"""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return False

    # Convert to async driver URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    print(f"Connecting to database...")
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Check if column exists
        result = await conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'videos' AND column_name = 'transcript'
        """))

        if result.fetchone():
            print("Column 'transcript' already exists in 'videos' table")
            return True

        # Add the column
        print("Adding 'transcript' column to 'videos' table...")
        await conn.execute(text("""
            ALTER TABLE videos ADD COLUMN transcript TEXT
        """))

        print("SUCCESS: Column 'transcript' added to 'videos' table")
        return True

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(add_transcript_column())
