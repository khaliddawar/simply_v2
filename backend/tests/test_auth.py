"""
Tests for Authentication Service

Tests the authentication system including:
- User registration
- Login
- Token generation and validation
- Google OAuth
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
import os

# Set test environment
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only"


class TestAuthService:
    """Test cases for AuthService"""

    @pytest.fixture
    def auth_service(self):
        """Create an AuthService instance"""
        from app.services.auth_service import AuthService
        return AuthService()

    def test_hash_password(self, auth_service):
        """Test password hashing"""
        password = "test_password_123"
        hashed = auth_service.hash_password(password)

        assert hashed != password
        assert auth_service.verify_password(password, hashed) is True
        assert auth_service.verify_password("wrong_password", hashed) is False

    def test_create_access_token(self, auth_service):
        """Test JWT token creation"""
        user_id = "test-user-123"
        token = auth_service.create_access_token(user_id)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_valid_token(self, auth_service):
        """Test verification of a valid token"""
        user_id = "test-user-456"
        token = auth_service.create_access_token(user_id)

        payload = auth_service.verify_token(token)

        assert payload is not None
        assert payload["sub"] == user_id

    def test_verify_invalid_token(self, auth_service):
        """Test verification of an invalid token"""
        payload = auth_service.verify_token("invalid.token.here")

        assert payload is None

    def test_get_user_id_from_token(self, auth_service):
        """Test extracting user ID from token"""
        user_id = "test-user-789"
        token = auth_service.create_access_token(user_id)

        extracted_id = auth_service.get_user_id_from_token(token)

        assert extracted_id == user_id

    def test_generate_pinecone_namespace(self, auth_service):
        """Test Pinecone namespace generation"""
        user_id = "abc-123"
        namespace = auth_service.generate_pinecone_namespace(user_id)

        assert namespace == "user_abc-123"

    @pytest.mark.asyncio
    async def test_register_user(self, auth_service):
        """Test user registration"""
        result = await auth_service.register_user(
            email="test@example.com",
            password="securepassword123",
            first_name="Test",
            last_name="User"
        )

        assert result["success"] is True
        assert "user" in result
        assert "access_token" in result
        assert result["user"]["email"] == "test@example.com"
        assert result["user"]["pinecone_namespace"].startswith("user_")

    def test_token_expiration(self, auth_service):
        """Test that token includes expiration"""
        user_id = "test-user"
        token = auth_service.create_access_token(user_id)

        payload = auth_service.verify_token(token)

        assert "exp" in payload
        assert payload["exp"] > datetime.utcnow().timestamp()


class TestGoogleOAuth:
    """Test cases for Google OAuth"""

    @pytest.fixture
    def auth_service(self):
        from app.services.auth_service import AuthService
        service = AuthService()
        service.google_client_id = "test-client-id"
        service.google_client_secret = "test-client-secret"
        return service

    @pytest.mark.asyncio
    async def test_google_oauth_callback_success(self, auth_service):
        """Test successful Google OAuth callback"""
        with patch("httpx.AsyncClient") as mock_client:
            # Mock token exchange response
            mock_token_response = Mock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = {
                "access_token": "google-access-token",
                "id_token": "google-id-token"
            }

            # Mock userinfo response
            mock_userinfo_response = Mock()
            mock_userinfo_response.status_code = 200
            mock_userinfo_response.json.return_value = {
                "id": "google-user-123",
                "email": "user@gmail.com",
                "given_name": "Test",
                "family_name": "User"
            }

            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_token_response
            mock_instance.get.return_value = mock_userinfo_response
            mock_instance.__aenter__.return_value = mock_instance

            mock_client.return_value = mock_instance

            result = await auth_service.google_oauth_callback(
                code="test-auth-code",
                redirect_uri="http://localhost/callback"
            )

            assert result["success"] is True
            assert result["user"]["email"] == "user@gmail.com"
            assert "access_token" in result

    @pytest.mark.asyncio
    async def test_google_oauth_invalid_code(self, auth_service):
        """Test Google OAuth with invalid code"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 400

            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance

            mock_client.return_value = mock_instance

            result = await auth_service.google_oauth_callback(
                code="invalid-code"
            )

            assert result["success"] is False
            assert "error" in result
