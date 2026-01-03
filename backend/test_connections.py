"""
Test script to verify database and Pinecone connections.

Run from the backend directory:
    python test_connections.py
"""
import asyncio
import os
import sys

# Fix Windows encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


async def test_database():
    """Test database connection"""
    print("\n" + "="*60)
    print("TESTING DATABASE CONNECTION")
    print("="*60)

    try:
        from app.services.database_service import DatabaseService

        db = DatabaseService()
        print(f"Database URL: {db.database_url[:50]}...")

        await db.initialize()
        print("[OK] Database initialized successfully!")

        # Test creating a user
        print("\nTesting user creation...")
        user = await db.create_user(
            email="test@example.com",
            first_name="Test",
            last_name="User"
        )
        print(f"[OK] Created test user: {user['id']}")

        # Test retrieving the user
        print("\nTesting user retrieval...")
        retrieved = await db.get_user_by_email("test@example.com")
        if retrieved:
            print(f"[OK] Retrieved user: {retrieved['email']}")
        else:
            print("[FAIL] Failed to retrieve user")

        # Clean up - delete test user
        print("\nCleaning up test user...")
        async with db.get_session() as session:
            from app.services.database_service import UserModel
            from sqlalchemy import delete
            await session.execute(
                delete(UserModel).where(UserModel.email == "test@example.com")
            )
        print("[OK] Test user deleted")

        await db.close()
        print("\n[OK] DATABASE TEST PASSED!")
        return True

    except Exception as e:
        print(f"\n[FAIL] DATABASE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pinecone():
    """Test Pinecone connection"""
    print("\n" + "="*60)
    print("TESTING PINECONE CONNECTION")
    print("="*60)

    try:
        from app.services.pinecone_service import PineconeService

        pinecone = PineconeService()

        print(f"API Key set: {'Yes' if pinecone.api_key else 'No'}")
        print(f"Assistant name: {pinecone.assistant_name}")
        print(f"Initialized: {pinecone.initialized}")

        if pinecone.initialized:
            print("\n[OK] PINECONE TEST PASSED!")
            return True
        else:
            print("\n[FAIL] Pinecone not initialized - check API key")
            return False

    except Exception as e:
        print(f"\n[FAIL] PINECONE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("\n" + "#"*60)
    print("# TUBEVIBE LIBRARY - CONNECTION TESTS")
    print("#"*60)

    # Test database
    db_ok = await test_database()

    # Test Pinecone
    pinecone_ok = test_pinecone()

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Database:  {'[PASS]' if db_ok else '[FAIL]'}")
    print(f"Pinecone:  {'[PASS]' if pinecone_ok else '[FAIL]'}")
    print("="*60)

    if db_ok and pinecone_ok:
        print("\nAll connections working! Ready to proceed.")
        return 0
    else:
        print("\nSome connections failed. Please check configuration.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
