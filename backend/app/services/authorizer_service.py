"""
Authorizer Service - Integration with Authorizer.dev

Handles:
- JWT token validation using JWKS (RS256 algorithm)
- JWKS caching for 1 hour using cachetools TTLCache
- User synchronization between Authorizer and TubeVibe
- Linking existing TubeVibe users to Authorizer accounts by email
"""
import logging
import os
from typing import Optional, Dict, Any, TYPE_CHECKING
import jwt
from jwt import PyJWKClient
from cachetools import TTLCache
from app.settings import get_settings

if TYPE_CHECKING:
    from app.services.database_service import DatabaseService

logger = logging.getLogger(__name__)


class AuthorizerService:
    """
    Service for integrating with Authorizer authentication.

    Authorizer is an open-source authentication solution that handles:
    - User registration/login
    - OAuth providers (Google, GitHub, etc.)
    - JWT token generation (RS256)

    This service:
    1. Validates Authorizer JWTs using JWKS endpoint
    2. Caches JWKS keys for 1 hour using TTLCache
    3. Creates/links TubeVibe users from Authorizer users
    4. Provides a bridge between Authorizer auth and TubeVibe-specific data
    """

    def __init__(self):
        """Initialize Authorizer service"""
        settings = get_settings()
        self.authorizer_url = settings.authorizer_url
        self.admin_secret = settings.authorizer_admin_secret
        self.webhook_secret = settings.authorizer_webhook_secret

        # JWKS client for token verification (lazy-initialized)
        self._jwks_client: Optional[PyJWKClient] = None

        # Cache for JWKS keys - 1 hour TTL, max 10 keys
        self._jwks_cache: TTLCache = TTLCache(maxsize=10, ttl=3600)

        # Database connection (to be injected)
        self.db: Optional["DatabaseService"] = None

        if self.authorizer_url:
            logger.info(f"AuthorizerService initialized with URL: {self.authorizer_url}")
        else:
            logger.warning("AuthorizerService: No authorizer_url configured, service disabled")

    def set_database(self, db: "DatabaseService"):
        """
        Inject database service dependency.

        Args:
            db: DatabaseService instance for user operations
        """
        self.db = db
        logger.info("Database service injected into AuthorizerService")

    def is_configured(self) -> bool:
        """Check if Authorizer is properly configured"""
        return bool(self.authorizer_url)

    def _get_jwks_client(self) -> PyJWKClient:
        """
        Get or create JWKS client for token verification.

        The client is lazily initialized on first use.

        Returns:
            PyJWKClient configured with Authorizer's JWKS endpoint
        """
        if self._jwks_client is None:
            if not self.authorizer_url:
                raise ValueError("Authorizer URL not configured")

            # Authorizer exposes JWKS at /.well-known/jwks.json
            jwks_url = f"{self.authorizer_url.rstrip('/')}/.well-known/jwks.json"
            self._jwks_client = PyJWKClient(
                jwks_url,
                cache_jwk_set=True,
                lifespan=3600  # Cache for 1 hour
            )
            logger.info(f"JWKS client initialized with URL: {jwks_url}")

        return self._jwks_client

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode an Authorizer JWT token using JWKS.

        Uses RS256 algorithm and validates against Authorizer's public keys.
        JWKS is cached for 1 hour to improve performance.

        Args:
            token: JWT access token from Authorizer

        Returns:
            Decoded token payload if valid, None otherwise.
            Payload contains: sub (user_id), email, given_name, family_name, etc.
        """
        if not self.authorizer_url:
            logger.error("Cannot verify token: Authorizer URL not configured")
            return None

        try:
            # Get signing key from JWKS
            jwks_client = self._get_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            # Decode and verify the token
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={
                    "verify_exp": True,
                    "verify_aud": False,  # Authorizer may not always set audience
                    "verify_iss": True
                },
                issuer=self.authorizer_url
            )

            logger.debug(f"Token verified successfully for user: {payload.get('sub')}")
            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Token verification failed: Token has expired")
            return None
        except jwt.InvalidAudienceError:
            logger.warning("Token verification failed: Invalid audience")
            return None
        except jwt.InvalidIssuerError:
            logger.warning("Token verification failed: Invalid issuer")
            return None
        except jwt.PyJWKClientError as e:
            logger.error(f"Token verification failed: JWKS client error - {e}")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token verification failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during token verification: {e}")
            return None

    async def get_or_create_tubevibe_user(
        self,
        authorizer_user_id: str,
        email: str,
        given_name: Optional[str] = None,
        family_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get or create a TubeVibe user from Authorizer user data.

        This method handles user synchronization between Authorizer and TubeVibe:
        1. First, checks if a user exists with the Authorizer user ID
        2. If not found, checks if a user exists with the same email
        3. If email match found, links the Authorizer account to existing user
        4. If no user found, creates a new TubeVibe user

        Args:
            authorizer_user_id: User ID from Authorizer (sub claim)
            email: User's email address
            given_name: User's first name (optional)
            family_name: User's last name (optional)

        Returns:
            Dict with user data if successful, None if database unavailable
        """
        if not self.db:
            logger.error("Cannot sync user: Database service not available")
            return None

        try:
            # Check if user exists with this Authorizer ID
            user = await self.db.get_user_by_authorizer_id(authorizer_user_id)

            if user:
                logger.debug(f"Found existing user by Authorizer ID: {user['id']}")
                return user

            # Check if user exists with this email (might have registered previously)
            user = await self.db.get_user_by_email(email)

            if user:
                # Link Authorizer account to existing user
                logger.info(f"Linking Authorizer account to existing user: {user['id']}")
                await self.db.link_authorizer_user(user["id"], authorizer_user_id)

                # Refresh user data after update
                user = await self.db.get_user_by_id(user["id"])
                return user

            # Create new user with Authorizer ID
            logger.info(f"Creating new TubeVibe user for Authorizer user: {authorizer_user_id}")
            user = await self.db.create_user_from_authorizer(
                authorizer_user_id=authorizer_user_id,
                email=email,
                first_name=given_name,
                last_name=family_name
            )

            logger.info(f"Created new user: {user['id']} for email: {email}")
            return user

        except Exception as e:
            logger.error(f"Error in get_or_create_tubevibe_user: {e}")
            return None

    def extract_user_info(self, token_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract user information from Authorizer token payload.

        Args:
            token_payload: Decoded JWT payload from verify_token()

        Returns:
            Dict with extracted user fields:
            - authorizer_user_id: User ID from Authorizer (sub claim)
            - email: User's email address
            - given_name: User's first name
            - family_name: User's last name
        """
        return {
            "authorizer_user_id": token_payload.get("sub"),
            "email": token_payload.get("email"),
            "given_name": token_payload.get("given_name"),
            "family_name": token_payload.get("family_name"),
        }

    async def authenticate_authorizer_token(self, token: str) -> Dict[str, Any]:
        """
        Full authentication flow for Authorizer tokens.

        Verifies the token and creates/retrieves the TubeVibe user.

        Args:
            token: JWT access token from Authorizer

        Returns:
            Dict with success status and user data or error message
        """
        # Verify the token
        payload = self.verify_token(token)
        if not payload:
            return {"success": False, "error": "Invalid or expired token"}

        # Extract user info
        user_info = self.extract_user_info(payload)

        if not user_info.get("authorizer_user_id") or not user_info.get("email"):
            return {"success": False, "error": "Token missing required claims (sub, email)"}

        # Get or create TubeVibe user
        user = await self.get_or_create_tubevibe_user(
            authorizer_user_id=user_info["authorizer_user_id"],
            email=user_info["email"],
            given_name=user_info.get("given_name"),
            family_name=user_info.get("family_name")
        )

        if not user:
            return {"success": False, "error": "Failed to sync user with database"}

        return {
            "success": True,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "first_name": user["first_name"],
                "last_name": user["last_name"],
                "plan_type": user["plan_type"],
                "pinecone_namespace": user["pinecone_namespace"]
            },
            "authorizer_user_id": user_info["authorizer_user_id"]
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_authorizer_service: Optional[AuthorizerService] = None


def get_authorizer_service() -> AuthorizerService:
    """Get or create Authorizer service singleton"""
    global _authorizer_service
    if _authorizer_service is None:
        _authorizer_service = AuthorizerService()
    return _authorizer_service
