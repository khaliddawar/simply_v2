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

from app.settings import get_settings

if TYPE_CHECKING:
    from app.services.database_service import DatabaseService

logger = logging.getLogger(__name__)

# Google endpoints used to check a Google OAuth access token.
# The token goes to tokeninfo in the POST body and to userinfo in the
# Authorization header, never in a URL: httpx logs every request URL at INFO
# level, and a logged token could be used to sign in as its owner.
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_HTTP_TIMEOUT_SECONDS = 10.0


def allowed_google_client_ids(settings) -> set:
    """OAuth client IDs whose Google access tokens we accept.

    Unset or blank values are dropped, so an empty setting can never match.
    """
    candidates = (
        settings.google_client_id,
        settings.extension_google_client_id,
        settings.first_party_google_client_id,
    )
    return {
        value.strip()
        for value in candidates
        if isinstance(value, str) and value.strip()
    }


def _is_true(value: Any) -> bool:
    """Google sends email_verified as the boolean true (userinfo) or the
    string "true" (tokeninfo). Anything else, including 1, counts as false."""
    if value is True:
        return True
    return isinstance(value, str) and value.strip().lower() == "true"


def _nonblank_str(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


class AuthService:
    """Service for handling user authentication"""

    def __init__(self):
        """Initialize Auth service"""
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        # JWT settings.
        # The signing key comes only from the required Settings.jwt_secret_key
        # field (env JWT_SECRET_KEY). There is deliberately no fallback: a
        # built-in default would be readable in this public repo, so anyone
        # could forge tokens whenever the variable was missing. A missing or
        # blank value now stops the app instead.
        self.secret_key = get_settings().jwt_secret_key
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
                logger.warning(f"Login attempt for non-existent email: {email}")
                return {"success": False, "error": "No account found with this email. Please register first."}

            # Verify password
            if not user.get("password_hash"):
                logger.info(f"User {email} has no password (Google OAuth user)")
                return {"success": False, "error": "This account uses Google Sign-In. Please login with Google."}

            if not self.verify_password(password, user["password_hash"]):
                logger.warning(f"Invalid password attempt for: {email}")
                return {"success": False, "error": "Incorrect password. Please try again."}

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

            if not isinstance(google_user, dict):
                return {
                    "success": False,
                    "error": "Failed to get user info from Google"
                }

            # Extract user data from Google response
            google_id = _nonblank_str(google_user.get("id"))
            email = _nonblank_str(google_user.get("email"))
            first_name = google_user.get("given_name")
            last_name = google_user.get("family_name")

            # The email links this sign-in to an existing account below, so
            # it must be one Google has verified belongs to this user.
            if not google_id or not email or not _is_true(google_user.get("verified_email")):
                logger.warning("Google OAuth callback refused: no verified email in Google's answer")
                return {
                    "success": False,
                    "error": "Google did not confirm this account's email address"
                }

            # Check if user exists by Google ID
            user = await self.db.get_user_by_google_id(google_id)
            is_new_user = False

            if not user:
                # Check by email (might have registered with password first)
                user = await self.db.get_user_by_email(email)

                if user:
                    # Link Google account to existing user
                    await self.db.update_user(user["id"], {"google_id": google_id})
                else:
                    # Create new user
                    is_new_user = True
                    user = await self.db.create_user(
                        email=email,
                        google_id=google_id,
                        first_name=first_name,
                        last_name=last_name
                    )

            # Send welcome email for new users
            if is_new_user:
                try:
                    from app.services.email_service import get_email_service
                    email_service = get_email_service()
                    await email_service.send_welcome_email(
                        recipient_email=email,
                        first_name=first_name
                    )
                except Exception as e:
                    logger.warning(f"Failed to send welcome email: {e}")

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

    async def verify_google_access_token(
        self,
        access_token: Optional[str],
        allowed_client_ids: Optional[set] = None,
    ) -> Dict[str, Any]:
        """
        Ask Google who a Google OAuth access token belongs to.

        Used by POST /api/auth/google/extension (dashboard and extension).
        Nothing the caller says about itself is trusted: the account id and
        email returned here come only from Google's answers.

        1. POST the token (in the body, never the URL) to tokeninfo. Require
           HTTP 200, a JSON object, and aud or azp equal to one of our
           client IDs, so a token issued to some other app is refused.
        2. GET userinfo with the token as a Bearer header. Require HTTP 200,
           a JSON object, the same sub as tokeninfo, an email, and
           email_verified true. If tokeninfo also gave an email, it must
           match.

        Any timeout, connection error, non-200 answer, non-JSON body or
        missing field returns success False. This function writes nothing.

        Returns:
            {"success": True, "google_id", "email", "given_name",
             "family_name", "name", "picture"} or
            {"success": False, "error": <message safe to show the user>}
        """
        refused = {
            "success": False,
            "error": "Google sign-in could not be verified. Please sign in again."
        }

        token = _nonblank_str(access_token)
        if not token:
            return refused

        if allowed_client_ids is None:
            allowed_client_ids = allowed_google_client_ids(get_settings())
        if not allowed_client_ids:
            logger.error(
                "Google sign-in refused: no Google OAuth client ID is configured"
            )
            return refused

        try:
            async with httpx.AsyncClient(timeout=GOOGLE_HTTP_TIMEOUT_SECONDS) as client:
                token_response = await client.post(
                    GOOGLE_TOKENINFO_URL,
                    data={"access_token": token},
                )
                if token_response.status_code != 200:
                    logger.warning(
                        f"Google sign-in refused: tokeninfo answered {token_response.status_code}"
                    )
                    return refused

                token_info = token_response.json()
                if not isinstance(token_info, dict):
                    logger.warning("Google sign-in refused: tokeninfo answer is not an object")
                    return refused

                audiences = {
                    value for value in (token_info.get("aud"), token_info.get("azp"))
                    if isinstance(value, str)
                }
                if not audiences & allowed_client_ids:
                    logger.warning(
                        "Google sign-in refused: token was issued to a client ID we do not accept"
                    )
                    return refused

                token_sub = _nonblank_str(token_info.get("sub"))
                if not token_sub:
                    logger.warning("Google sign-in refused: tokeninfo gave no sub")
                    return refused

                if "email_verified" in token_info and not _is_true(token_info.get("email_verified")):
                    logger.warning("Google sign-in refused: tokeninfo says the email is not verified")
                    return refused

                userinfo_response = await client.get(
                    GOOGLE_USERINFO_URL,
                    headers={"Authorization": f"Bearer {token}"},
                )
                if userinfo_response.status_code != 200:
                    logger.warning(
                        f"Google sign-in refused: userinfo answered {userinfo_response.status_code}"
                    )
                    return refused

                user_info = userinfo_response.json()
                if not isinstance(user_info, dict):
                    logger.warning("Google sign-in refused: userinfo answer is not an object")
                    return refused

        except Exception as e:
            # Timeouts, connection errors and non-JSON bodies all land here.
            # Log only the error type: nothing here should carry the token,
            # but there is no reason to risk it.
            logger.warning(f"Google sign-in refused: {type(e).__name__} while checking the token")
            return refused

        user_sub = _nonblank_str(user_info.get("sub"))
        if not user_sub or user_sub != token_sub:
            logger.warning("Google sign-in refused: tokeninfo and userinfo disagree on sub")
            return refused

        email = _nonblank_str(user_info.get("email"))
        if not email:
            logger.warning("Google sign-in refused: userinfo gave no email")
            return refused
        email = email.lower()

        if not _is_true(user_info.get("email_verified")):
            logger.warning("Google sign-in refused: Google has not verified this email")
            return refused

        token_email = token_info.get("email")
        if token_email is not None:
            if not isinstance(token_email, str) or token_email.strip().lower() != email:
                logger.warning("Google sign-in refused: tokeninfo and userinfo disagree on email")
                return refused

        return {
            "success": True,
            "google_id": user_sub,
            "email": email,
            "given_name": user_info.get("given_name"),
            "family_name": user_info.get("family_name"),
            "name": user_info.get("name"),
            "picture": user_info.get("picture"),
        }

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
