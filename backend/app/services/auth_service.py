"""
Authentication Service

Handles user authentication including:
- Email/password registration and login
- Google OAuth integration
- JWT token generation and validation
- Password reset flow
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, TYPE_CHECKING
import httpx
from jose import jwt, JWTError
from passlib.context import CryptContext

if TYPE_CHECKING:
    from app.services.database_service import DatabaseService

logger = logging.getLogger(__name__)


class AuthService:
    """Service for handling user authentication"""

    def __init__(self):
        """Initialize Auth service"""
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        # JWT settings
        self.secret_key = os.getenv("JWT_SECRET_KEY", "development-secret-key")
        self.algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.access_token_expire_minutes = int(
            os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "10080")
        )  # 7 days

        # Google OAuth settings
        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")

        # Database connection (to be injected)
        self.db: Optional["DatabaseService"] = None

        logger.info("Auth service initialized")

    def set_database(self, db: "DatabaseService"):
        """Inject database service"""
        self.db = db
        logger.info("Database service injected into Auth service")

    def _truncate_password(self, password: str) -> str:
        """Truncate password to 72 bytes (bcrypt limit)"""
        # Encode to bytes and truncate to 72 bytes, then decode back
        return password.encode('utf-8')[:72].decode('utf-8', errors='ignore')

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt (truncated to 72 bytes)"""
        return self.pwd_context.hash(self._truncate_password(password))

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash (truncated to 72 bytes)"""
        return self.pwd_context.verify(self._truncate_password(plain_password), hashed_password)

    def create_access_token(
        self,
        user_id: str,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create a JWT access token.

        Args:
            user_id: User's unique ID
            expires_delta: Optional custom expiration time

        Returns:
            JWT token string
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=self.access_token_expire_minutes
            )

        payload = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode a JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded payload if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload
        except JWTError as e:
            logger.warning(f"Token verification failed: {e}")
            return None

    def get_user_id_from_token(self, token: str) -> Optional[str]:
        """Extract user ID from a valid token"""
        payload = self.verify_token(token)
        if payload:
            return payload.get("sub")
        return None

    def generate_pinecone_namespace(self, user_id: str) -> str:
        """Generate a Pinecone namespace for a user"""
        return f"user_{user_id}"

    async def register_user(
        self,
        email: str,
        password: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register a new user with email and password.

        Args:
            email: User's email address
            password: Plain text password
            first_name: Optional first name
            last_name: Optional last name

        Returns:
            Dict with user data and tokens
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            # Check if user already exists
            existing_user = await self.db.get_user_by_email(email)
            if existing_user:
                return {"success": False, "error": "Email already registered"}

            # Hash password
            password_hash = self.hash_password(password)

            # Create user in database
            user = await self.db.create_user(
                email=email,
                password_hash=password_hash,
                first_name=first_name,
                last_name=last_name
            )

            # Generate access token
            access_token = self.create_access_token(user["id"])

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
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": self.access_token_expire_minutes * 60
            }

        except Exception as e:
            logger.error(f"Error registering user: {e}")
            return {"success": False, "error": str(e)}

    async def login_user(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate a user with email and password.

        Args:
            email: User's email address
            password: Plain text password

        Returns:
            Dict with user data and tokens if successful
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            # Get user from database
            user = await self.db.get_user_by_email(email)

            if not user:
                return {"success": False, "error": "Invalid email or password"}

            # Verify password
            if not user.get("password_hash"):
                return {"success": False, "error": "Please login with Google"}

            if not self.verify_password(password, user["password_hash"]):
                return {"success": False, "error": "Invalid email or password"}

            # Generate access token
            access_token = self.create_access_token(user["id"])

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
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": self.access_token_expire_minutes * 60
            }

        except Exception as e:
            logger.error(f"Error logging in user: {e}")
            return {"success": False, "error": str(e)}

    async def google_oauth_callback(
        self,
        code: str,
        redirect_uri: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle Google OAuth callback.

        Args:
            code: Authorization code from Google
            redirect_uri: OAuth redirect URI

        Returns:
            Dict with user data and tokens
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            # Exchange code for tokens
            token_url = "https://oauth2.googleapis.com/token"
            token_data = {
                "code": code,
                "client_id": self.google_client_id,
                "client_secret": self.google_client_secret,
                "redirect_uri": redirect_uri or self.google_redirect_uri,
                "grant_type": "authorization_code"
            }

            async with httpx.AsyncClient() as client:
                token_response = await client.post(token_url, data=token_data)

                if token_response.status_code != 200:
                    return {
                        "success": False,
                        "error": "Failed to exchange OAuth code"
                    }

                tokens = token_response.json()
                access_token = tokens.get("access_token")

                # Get user info from Google
                userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
                headers = {"Authorization": f"Bearer {access_token}"}
                userinfo_response = await client.get(userinfo_url, headers=headers)

                if userinfo_response.status_code != 200:
                    return {
                        "success": False,
                        "error": "Failed to get user info from Google"
                    }

                google_user = userinfo_response.json()

            # Extract user data from Google response
            google_id = google_user.get("id")
            email = google_user.get("email")
            first_name = google_user.get("given_name")
            last_name = google_user.get("family_name")

            # Check if user exists by Google ID
            user = await self.db.get_user_by_google_id(google_id)

            if not user:
                # Check by email (might have registered with password first)
                user = await self.db.get_user_by_email(email)

                if user:
                    # Link Google account to existing user
                    await self.db.update_user(user["id"], {"google_id": google_id})
                else:
                    # Create new user
                    user = await self.db.create_user(
                        email=email,
                        google_id=google_id,
                        first_name=first_name,
                        last_name=last_name
                    )

            # Create our JWT token
            jwt_token = self.create_access_token(user["id"])

            return {
                "success": True,
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "first_name": user["first_name"],
                    "last_name": user["last_name"],
                    "google_id": google_id,
                    "plan_type": user["plan_type"],
                    "pinecone_namespace": user["pinecone_namespace"]
                },
                "access_token": jwt_token,
                "token_type": "bearer",
                "expires_in": self.access_token_expire_minutes * 60
            }

        except Exception as e:
            logger.error(f"Error in Google OAuth callback: {e}")
            return {"success": False, "error": str(e)}

    async def verify_google_id_token(self, id_token: str) -> Dict[str, Any]:
        """
        Verify a Google ID token (used by Chrome extension).

        Args:
            id_token: Google ID token from Chrome identity API

        Returns:
            Dict with user info if valid
        """
        try:
            # Verify token with Google
            verify_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"

            async with httpx.AsyncClient() as client:
                response = await client.get(verify_url)

                if response.status_code != 200:
                    return {"success": False, "error": "Invalid ID token"}

                token_info = response.json()

            # Verify audience
            if token_info.get("aud") not in [
                self.google_client_id,
                os.getenv("EXTENSION_GOOGLE_CLIENT_ID")
            ]:
                return {"success": False, "error": "Invalid token audience"}

            return {
                "success": True,
                "google_id": token_info.get("sub"),
                "email": token_info.get("email"),
                "name": token_info.get("name"),
                "picture": token_info.get("picture")
            }

        except Exception as e:
            logger.error(f"Error verifying Google ID token: {e}")
            return {"success": False, "error": str(e)}

    async def authenticate_extension(self, id_token: str) -> Dict[str, Any]:
        """
        Authenticate Chrome extension user with Google ID token.
        Creates user if needed, returns JWT token.

        Args:
            id_token: Google ID token from Chrome identity API

        Returns:
            Dict with user data and JWT token
        """
        if not self.db:
            return {"success": False, "error": "Database service not available"}

        try:
            # Verify the Google ID token
            verify_result = await self.verify_google_id_token(id_token)

            if not verify_result.get("success"):
                return verify_result

            google_id = verify_result["google_id"]
            email = verify_result["email"]
            name = verify_result.get("name", "")

            # Parse first/last name
            name_parts = name.split(" ", 1) if name else ["", ""]
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            # Check if user exists
            user = await self.db.get_user_by_google_id(google_id)

            if not user:
                # Check by email
                user = await self.db.get_user_by_email(email)

                if user:
                    # Link Google account to existing user
                    await self.db.update_user(user["id"], {"google_id": google_id})
                else:
                    # Create new user
                    user = await self.db.create_user(
                        email=email,
                        google_id=google_id,
                        first_name=first_name,
                        last_name=last_name
                    )

            # Generate JWT token
            jwt_token = self.create_access_token(user["id"])

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
                "access_token": jwt_token,
                "token_type": "bearer",
                "expires_in": self.access_token_expire_minutes * 60
            }

        except Exception as e:
            logger.error(f"Error authenticating extension user: {e}")
            return {"success": False, "error": str(e)}

    async def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Get current user from JWT token.

        Args:
            token: JWT access token

        Returns:
            User data if token is valid, None otherwise
        """
        if not self.db:
            return None

        user_id = self.get_user_id_from_token(token)
        if not user_id:
            return None

        return await self.db.get_user_by_id(user_id)


# Singleton instance
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get or create Auth service singleton"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
