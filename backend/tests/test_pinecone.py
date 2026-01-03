"""
Tests for Pinecone Service

Tests the Pinecone Assistant integration including:
- Transcript upload
- Knowledge search
- Context retrieval
- File management
- User isolation
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import os

# Set test environment
os.environ["PINECONE_API_KEY"] = "test-api-key"
os.environ["PINECONE_ASSISTANT_NAME"] = "test-assistant"


class TestPineconeService:
    """Test cases for PineconeService"""

    @pytest.fixture
    def mock_pinecone(self):
        """Create a mock Pinecone client"""
        with patch("app.services.pinecone_service.Pinecone") as mock:
            mock_instance = Mock()
            mock_assistant = Mock()

            mock_instance.assistant.Assistant.return_value = mock_assistant
            mock.return_value = mock_instance

            yield mock_assistant

    @pytest.fixture
    def pinecone_service(self, mock_pinecone):
        """Create a PineconeService instance with mocked client"""
        from app.services.pinecone_service import PineconeService
        service = PineconeService()
        service.assistant = mock_pinecone
        service.initialized = True
        return service

    @pytest.mark.asyncio
    async def test_upload_transcript_success(self, pinecone_service, mock_pinecone):
        """Test successful transcript upload"""
        # Setup mock response
        mock_response = Mock()
        mock_response.id = "file-123"
        mock_response.status = "ready"
        mock_pinecone.upload_bytes_stream.return_value = mock_response

        # Execute
        result = await pinecone_service.upload_transcript(
            user_id="user-1",
            video_id="abc123",
            title="Test Video",
            transcript="This is a test transcript"
        )

        # Assert
        assert result["success"] is True
        assert result["file_id"] == "file-123"
        mock_pinecone.upload_bytes_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_transcript_with_metadata(self, pinecone_service, mock_pinecone):
        """Test transcript upload with additional metadata"""
        mock_response = Mock()
        mock_response.id = "file-456"
        mock_response.status = "ready"
        mock_pinecone.upload_bytes_stream.return_value = mock_response

        result = await pinecone_service.upload_transcript(
            user_id="user-1",
            video_id="xyz789",
            title="Test Video 2",
            transcript="Another transcript",
            metadata={
                "group_id": "group-1",
                "channel_name": "Test Channel",
                "duration_seconds": 300
            }
        )

        assert result["success"] is True
        # Verify metadata was included in the call
        call_args = mock_pinecone.upload_bytes_stream.call_args
        assert "metadata" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_search_knowledge_success(self, pinecone_service, mock_pinecone):
        """Test successful knowledge search"""
        mock_response = Mock()
        mock_response.message.content = "This is the answer based on your videos."
        mock_response.citations = []
        mock_pinecone.chat.return_value = mock_response

        result = await pinecone_service.search_knowledge(
            user_id="user-1",
            query="What is the main topic?"
        )

        assert result["success"] is True
        assert "answer" in result
        mock_pinecone.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_group_filter(self, pinecone_service, mock_pinecone):
        """Test search with group filter"""
        mock_response = Mock()
        mock_response.message.content = "Answer from specific group"
        mock_response.citations = []
        mock_pinecone.chat.return_value = mock_response

        result = await pinecone_service.search_knowledge(
            user_id="user-1",
            query="What is discussed?",
            group_id="group-1"
        )

        assert result["success"] is True
        # Verify filter included group_id
        call_args = mock_pinecone.chat.call_args
        assert "filter" in call_args.kwargs
        assert call_args.kwargs["filter"]["group_id"] == "group-1"

    @pytest.mark.asyncio
    async def test_user_isolation(self, pinecone_service, mock_pinecone):
        """Test that searches are isolated by user"""
        mock_response = Mock()
        mock_response.message.content = "User-specific answer"
        mock_response.citations = []
        mock_pinecone.chat.return_value = mock_response

        # Search for user-1
        await pinecone_service.search_knowledge(
            user_id="user-1",
            query="Test query"
        )

        # Verify user_id is in the filter
        call_args = mock_pinecone.chat.call_args
        assert call_args.kwargs["filter"]["user_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_delete_file_success(self, pinecone_service, mock_pinecone):
        """Test successful file deletion"""
        mock_pinecone.delete_file.return_value = None

        result = await pinecone_service.delete_file("file-123")

        assert result["success"] is True
        mock_pinecone.delete_file.assert_called_once_with(file_id="file-123")

    @pytest.mark.asyncio
    async def test_service_not_initialized(self):
        """Test behavior when service is not initialized"""
        from app.services.pinecone_service import PineconeService

        with patch.dict(os.environ, {"PINECONE_API_KEY": ""}):
            service = PineconeService()
            service.initialized = False

            result = await service.upload_transcript(
                user_id="user-1",
                video_id="abc",
                title="Test",
                transcript="Test"
            )

            assert result["success"] is False
            assert "not initialized" in result["error"]


class TestSearchContext:
    """Test cases for context retrieval"""

    @pytest.fixture
    def mock_pinecone(self):
        with patch("app.services.pinecone_service.Pinecone") as mock:
            mock_instance = Mock()
            mock_assistant = Mock()
            mock_instance.assistant.Assistant.return_value = mock_assistant
            mock.return_value = mock_instance
            yield mock_assistant

    @pytest.fixture
    def pinecone_service(self, mock_pinecone):
        from app.services.pinecone_service import PineconeService
        service = PineconeService()
        service.assistant = mock_pinecone
        service.initialized = True
        return service

    @pytest.mark.asyncio
    async def test_get_context_for_summary(self, pinecone_service, mock_pinecone):
        """Test getting context for summary generation"""
        mock_snippet = Mock()
        mock_snippet.text = "This is relevant content"
        mock_snippet.score = 0.95

        mock_response = Mock()
        mock_response.snippets = [mock_snippet]
        mock_pinecone.context.return_value = mock_response

        result = await pinecone_service.get_context_for_summary(
            user_id="user-1",
            video_id="abc123"
        )

        assert result["success"] is True
        assert len(result["snippets"]) == 1
        mock_pinecone.context.assert_called_once()
