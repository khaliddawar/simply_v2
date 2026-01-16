"""
Authentication Routes

Supports both legacy authentication (email/password, Google OAuth)
and Authorizer authentication (JWKS-based RS256 token validation).
"""
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import RedirectResponse
from typing import Optional
from pydantic import BaseModel

from app.models.user import (
    UserCreate, UserLogin, UserResponse, TokenResponse,
    GoogleOAuthRequest, GoogleUserDataRequest, PasswordResetRequest
)
from app.services.auth_service import get_auth_service, AuthService
from app.services.authorizer_service import get_authorizer_service
from app.settings import get_settings

router = APIRouter()
security = HTTPBearer()


class GoogleIdTokenRequest(BaseModel):
    """Request body for Google ID token verification"""
    id_token: str


class AuthorizerTokenRequest(BaseModel):
    """Request body for Authorizer token validation"""
    access_token: str


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Extract and validate user ID from JWT token.

    Supports dual authentication:
    1. First tries Authorizer validation (RS256 via JWKS)
    2. Falls back to legacy validation (HS256)
    """
    token = credentials.credentials
    settings = get_settings()

    # Try Authorizer validation first (RS256) if configured
    if settings.authorizer_url:
        authorizer_service = get_authorizer_service()
        payload = authorizer_service.verify_token(token)

        if payload:
            # Token is valid Authorizer token
            authorizer_user_id = payload.get("sub")
            if authorizer_user_id and authorizer_service.db:
                user = await authorizer_service.db.get_user_by_authorizer_id(authorizer_user_id)
                if user:
                    return user["id"]
                # User authenticated with Authorizer but not in TubeVibe yet
                raise HTTPException(
                    status_code=401,
                    detail="User not found in TubeVibe. Please use /api/auth/authorizer/token first."
                )

    # Fallback to legacy validation (HS256)
    auth_service = get_auth_service()
    user_id = auth_service.get_user_id_from_token(token)

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return user_id


# Optional auth dependency for testing without authentication
optional_security = HTTPBearer(auto_error=False)


async def get_current_user_id_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security)
) -> str:
    """
    Extract user ID from token, or return test user ID if allow_no_auth is enabled.
    Used for testing without authentication.

    Supports dual authentication:
    1. First tries Authorizer validation (RS256 via JWKS)
    2. Falls back to legacy validation (HS256)
    """
    settings = get_settings()

    # If allow_no_auth is enabled, return test user ID (valid UUID format)
    if settings.allow_no_auth:
        return "00000000-0000-0000-0000-000000000001"

    # Otherwise require valid token
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    # Try Authorizer validation first (RS256) if configured
    if settings.authorizer_url:
        authorizer_service = get_authorizer_service()
        payload = authorizer_service.verify_token(token)

        if payload:
            # Token is valid Authorizer token
            authorizer_user_id = payload.get("sub")
            if authorizer_user_id and authorizer_service.db:
                user = await authorizer_service.db.get_user_by_authorizer_id(authorizer_user_id)
                if user:
                    return user["id"]
                # User authenticated with Authorizer but not in TubeVibe yet
                raise HTTPException(
                    status_code=401,
                    detail="User not found in TubeVibe. Please use /api/auth/authorizer/token first."
                )

    # Fallback to legacy validation (HS256)
    auth_service = get_auth_service()
    user_id = auth_service.get_user_id_from_token(token)

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return user_id


@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserCreate):
    """
    Register a new user with email and password.

    Creates user in both Authorizer (for unified auth) and TubeVibe database.
    Returns access token and user data on success.
    """
    import httpx
    import logging

    settings = get_settings()
    auth_service = get_auth_service()
    email = user_data.email.lower().strip()

    # If Authorizer is configured, register there first for unified auth
    if settings.authorizer_url:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Sign up via Authorizer GraphQL
                signup_mutation = '''
                mutation Signup($params: SignUpInput!) {
                    signup(params: $params) {
                        message
                        user { id email }
                        access_token
                        id_token
                    }
                }
                '''

                signup_resp = await client.post(
                    f'{settings.authorizer_url}/graphql',
                    headers={'Content-Type': 'application/json'},
                    json={
                        'query': signup_mutation,
                        'variables': {
                            'params': {
                                'email': email,
                                'password': user_data.password,
                                'confirm_password': user_data.password,
                                'given_name': user_data.first_name or email.split('@')[0],
                                'family_name': user_data.last_name or ''
                            }
                        }
                    }
                )

                signup_result = signup_resp.json() if signup_resp.status_code == 200 else {}

                # Check for errors in GraphQL response
                if signup_result.get('errors'):
                    error_msg = signup_result['errors'][0].get('message', 'Registration failed')
                    if 'already exists' in error_msg.lower() or 'already signed up' in error_msg.lower():
                        raise HTTPException(status_code=400, detail="Email already registered. Please login instead.")
                    raise HTTPException(status_code=400, detail=error_msg)

                signup_data = signup_result.get('data', {}).get('signup', {})
                authorizer_user = signup_data.get('user')
                access_token = signup_data.get('access_token')

                if not authorizer_user:
                    raise Exception("Authorizer signup returned no user")

                authorizer_user_id = authorizer_user.get('id')

                # Auto-verify email (Railway blocks SMTP so we can't send verification emails)
                if settings.authorizer_admin_secret:
                    # Admin login first
                    login_mutation = '''
                    mutation AdminLogin($params: AdminLoginInput!) {
                        _admin_login(params: $params) { message }
                    }
                    '''
                    await client.post(
                        f'{settings.authorizer_url}/graphql',
                        headers={'Content-Type': 'application/json'},
                        json={
                            'query': login_mutation,
                            'variables': {'params': {'admin_secret': settings.authorizer_admin_secret}}
                        }
                    )
                    # Verify email
                    update_mutation = '''
                    mutation UpdateUser($params: UpdateUserInput!) {
                        _update_user(params: $params) { id email_verified }
                    }
                    '''
                    await client.post(
                        f'{settings.authorizer_url}/graphql',
                        headers={'Content-Type': 'application/json'},
                        json={
                            'query': update_mutation,
                            'variables': {
                                'params': {
                                    'id': authorizer_user_id,
                                    'email_verified': True
                                }
                            }
                        }
                    )

                # Create or link TubeVibe user
                authorizer_service = get_authorizer_service()
                user = await authorizer_service.get_or_create_tubevibe_user(
                    authorizer_user_id=authorizer_user_id,
                    email=email,
                    given_name=user_data.first_name,
                    family_name=user_data.last_name
                )

                if not user:
                    raise HTTPException(status_code=500, detail="Failed to create user in database")

                # Store password hash locally for legacy fallback
                if auth_service.db:
                    password_hash = auth_service.hash_password(user_data.password)
                    await auth_service.db.update_user(user["id"], {
                        "password_hash": password_hash,
                        "auth_provider": "authorizer"
                    })

                # Use our JWT for API access (more reliable than Authorizer token)
                jwt_token = auth_service.create_access_token(user["id"])

                return TokenResponse(
                    access_token=jwt_token,
                    token_type="bearer",
                    expires_in=auth_service.access_token_expire_minutes * 60,
                    user=UserResponse(
                        id=user["id"],
                        email=user["email"],
                        first_name=user.get("first_name"),
                        last_name=user.get("last_name"),
                        plan_type=user.get("plan_type", "free"),
                        pinecone_namespace=user.get("pinecone_namespace")
                    )
                )

        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Authorizer registration failed, falling back to legacy: {e}")
            # Fall through to legacy registration

    # Legacy registration (fallback if Authorizer not configured or fails)
    result = await auth_service.register_user(
        email=user_data.email,
        password=user_data.password,
        first_name=user_data.first_name,
        last_name=user_data.last_name
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        expires_in=result["expires_in"],
        user=UserResponse(**result["user"])
    )


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    """
    Authenticate user with email and password.

    Tries Authorizer authentication first (unified auth), falls back to legacy.
    Returns access token and user data on success.
    """
    import httpx
    import logging

    settings = get_settings()
    auth_service = get_auth_service()
    email = credentials.email.lower().strip()

    # If Authorizer is configured, try authenticating there first
    if settings.authorizer_url:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Login via Authorizer GraphQL
                login_mutation = '''
                mutation Login($params: LoginInput!) {
                    login(params: $params) {
                        message
                        user { id email given_name family_name }
                        access_token
                        id_token
                    }
                }
                '''

                login_resp = await client.post(
                    f'{settings.authorizer_url}/graphql',
                    headers={'Content-Type': 'application/json'},
                    json={
                        'query': login_mutation,
                        'variables': {
                            'params': {
                                'email': email,
                                'password': credentials.password
                            }
                        }
                    }
                )

                login_result = login_resp.json() if login_resp.status_code == 200 else {}

                # Check for errors in GraphQL response
                if login_result.get('errors'):
                    error_msg = login_result['errors'][0].get('message', 'Login failed')
                    # If user not found in Authorizer, fall through to legacy auth
                    if 'not found' in error_msg.lower() or 'invalid credentials' in error_msg.lower():
                        logging.info(f"User {email} not found in Authorizer, trying legacy auth")
                        raise Exception("User not in Authorizer")
                    raise HTTPException(status_code=401, detail=error_msg)

                login_data = login_result.get('data', {}).get('login', {})
                authorizer_user = login_data.get('user')
                access_token = login_data.get('access_token')

                if authorizer_user and access_token:
                    authorizer_user_id = authorizer_user.get('id')

                    # Get or create TubeVibe user linked to this Authorizer account
                    authorizer_service = get_authorizer_service()
                    user = await authorizer_service.get_or_create_tubevibe_user(
                        authorizer_user_id=authorizer_user_id,
                        email=email,
                        given_name=authorizer_user.get('given_name'),
                        family_name=authorizer_user.get('family_name')
                    )

                    if not user:
                        raise HTTPException(status_code=500, detail="Failed to sync user with database")

                    # Use our JWT for API access
                    jwt_token = auth_service.create_access_token(user["id"])

                    return TokenResponse(
                        access_token=jwt_token,
                        token_type="bearer",
                        expires_in=auth_service.access_token_expire_minutes * 60,
                        user=UserResponse(
                            id=user["id"],
                            email=user["email"],
                            first_name=user.get("first_name"),
                            last_name=user.get("last_name"),
                            plan_type=user.get("plan_type", "free"),
                            pinecone_namespace=user.get("pinecone_namespace")
                        )
                    )
                else:
                    raise Exception("Authorizer login returned no user or token")

        except HTTPException:
            raise
        except Exception as e:
            logging.info(f"Authorizer login failed for {email}, trying legacy: {e}")
            # Fall through to legacy authentication

    # Legacy authentication (fallback if Authorizer not configured or user not found)
    result = await auth_service.login_user(
        email=credentials.email,
        password=credentials.password
    )

    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("error"))

    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        expires_in=result["expires_in"],
        user=UserResponse(**result["user"])
    )


@router.post("/google", response_model=TokenResponse)
async def google_oauth(request: GoogleOAuthRequest):
    """
    Handle Google OAuth callback.

    Exchange authorization code for tokens and create/login user.
    """
    auth_service = get_auth_service()

    result = await auth_service.google_oauth_callback(
        code=request.code,
        redirect_uri=request.redirect_uri
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        expires_in=result["expires_in"],
        user=UserResponse(**result["user"])
    )


@router.post("/google/verify", response_model=TokenResponse)
async def verify_google_token(request: GoogleIdTokenRequest):
    """
    Verify Google ID token and authenticate user (used by Chrome extension).

    The extension uses Chrome's identity API to get an ID token,
    which is verified against Google's servers.
    Returns JWT token for subsequent API calls.
    """
    auth_service = get_auth_service()

    result = await auth_service.authenticate_extension(request.id_token)

    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("error"))

    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        expires_in=result["expires_in"],
        user=UserResponse(**result["user"])
    )


@router.post("/google/extension", response_model=TokenResponse)
async def google_oauth_extension(request: GoogleUserDataRequest):
    """
    Authenticate user with Google user data (used by Chrome extension).

    The extension gets Google user info via OAuth access token,
    then sends the user data here for account creation/login.
    This bypasses the code exchange flow since extensions can't
    securely store client secrets.
    """
    from app.services.email_service import get_email_service

    auth_service = get_auth_service()

    if not auth_service.db:
        raise HTTPException(status_code=500, detail="Database service not available")

    try:
        is_new_user = False

        # Check if user exists by Google ID
        user = await auth_service.db.get_user_by_google_id(request.google_id)

        if not user:
            # Check by email
            user = await auth_service.db.get_user_by_email(request.email)

            if user:
                # Link Google account to existing user
                await auth_service.db.update_user(user["id"], {"google_id": request.google_id})
            else:
                # Create new user
                is_new_user = True
                user = await auth_service.db.create_user(
                    email=request.email,
                    google_id=request.google_id,
                    first_name=request.given_name or "",
                    last_name=request.family_name or ""
                )

        if not user:
            raise HTTPException(status_code=500, detail="Failed to create or retrieve user")

        # Send welcome email for new users (don't block the response)
        if is_new_user:
            try:
                email_service = get_email_service()
                await email_service.send_welcome_email(
                    recipient_email=request.email,
                    first_name=request.given_name
                )
            except Exception as e:
                # Log but don't fail the auth if email fails
                import logging
                logging.getLogger(__name__).warning(f"Failed to send welcome email: {e}")

        # Generate JWT token
        jwt_token = auth_service.create_access_token(user["id"])
        settings = get_settings()

        return TokenResponse(
            access_token=jwt_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                first_name=user.get("first_name"),
                last_name=user.get("last_name"),
                plan_type=user.get("plan_type", "free"),
                pinecone_namespace=user.get("pinecone_namespace")
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.get("/google/login")
async def google_login(redirect_uri: str = None):
    """
    Initiate Google OAuth flow - redirects to Google login page.
    Used by frontend for browser-based authentication.
    """
    from app.settings import get_settings
    settings = get_settings()

    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    # Use provided redirect_uri or default
    callback_uri = f"{settings.api_base_url}/api/auth/google/callback"

    # Build Google OAuth URL
    google_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={settings.google_client_id}&"
        f"redirect_uri={callback_uri}&"
        "response_type=code&"
        "scope=openid%20email%20profile&"
        "access_type=offline"
    )

    # Store the final redirect URI in session/state if provided
    if redirect_uri:
        google_auth_url += f"&state={redirect_uri}"

    return RedirectResponse(url=google_auth_url)


@router.get("/google/callback")
async def google_callback(code: str = None, state: str = None, error: str = None):
    """
    Handle Google OAuth callback - exchanges code for tokens.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    from app.settings import get_settings
    settings = get_settings()

    auth_service = get_auth_service()

    callback_uri = f"{settings.api_base_url}/api/auth/google/callback"

    result = await auth_service.google_oauth_callback(
        code=code,
        redirect_uri=callback_uri
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    # If state contains a redirect URI, redirect there with tokens
    if state:
        redirect_url = f"{state}?access_token={result['access_token']}"
        return RedirectResponse(url=redirect_url)

    # Otherwise return JSON response
    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        expires_in=result["expires_in"],
        user=UserResponse(**result["user"])
    )


# =============================================================================
# Authorizer Authentication Endpoints
# =============================================================================

@router.post("/authorizer/token", response_model=TokenResponse)
async def exchange_authorizer_token(request: AuthorizerTokenRequest):
    """
    Exchange Authorizer access token for TubeVibe user data.

    This endpoint:
    1. Validates the Authorizer JWT via JWKS (RS256)
    2. Gets/creates the TubeVibe user
    3. Returns TubeVibe-specific user data (plan_type, pinecone_namespace)

    The Authorizer token is passed through as-is (we don't issue our own JWT).
    """
    settings = get_settings()

    if not settings.authorizer_url:
        raise HTTPException(
            status_code=501,
            detail="Authorizer authentication not configured"
        )

    authorizer_service = get_authorizer_service()

    # Verify Authorizer token
    payload = authorizer_service.verify_token(request.access_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid Authorizer token")

    # Extract user info from Authorizer claims
    authorizer_user_id = payload.get("sub")
    email = payload.get("email")
    given_name = payload.get("given_name")
    family_name = payload.get("family_name")

    if not authorizer_user_id or not email:
        raise HTTPException(status_code=401, detail="Invalid token claims: missing sub or email")

    # Get or create TubeVibe user
    user = await authorizer_service.get_or_create_tubevibe_user(
        authorizer_user_id=authorizer_user_id,
        email=email,
        given_name=given_name,
        family_name=family_name
    )

    if not user:
        raise HTTPException(status_code=500, detail="Failed to create/retrieve user")

    # Return user with TubeVibe-specific data
    # Note: We return the Authorizer token as the access_token since we use it for subsequent requests
    return TokenResponse(
        access_token=request.access_token,
        token_type="bearer",
        expires_in=1800,  # 30 minutes (Authorizer default)
        user=UserResponse(
            id=user["id"],
            email=user["email"],
            first_name=user.get("first_name"),
            last_name=user.get("last_name"),
            plan_type=user.get("plan_type", "free"),
            pinecone_namespace=user.get("pinecone_namespace")
        )
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(user_id: str = Depends(get_current_user_id)):
    """
    Get current authenticated user's profile.
    """
    auth_service = get_auth_service()

    if not auth_service.db:
        raise HTTPException(status_code=500, detail="Database not available")

    user = await auth_service.db.get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=user["id"],
        email=user["email"],
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        plan_type=user.get("plan_type", "free"),
        pinecone_namespace=user.get("pinecone_namespace")
    )


class ForgotPasswordRequest(BaseModel):
    """Request body for forgot password"""
    email: str


@router.post("/password-reset")
async def request_password_reset(request: PasswordResetRequest):
    """
    Request a password reset email (legacy endpoint).
    """
    return {"message": "If an account exists with this email, a reset link has been sent"}


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """
    Handle forgot password request by generating a new password and sending via Postmark.

    This bypasses Authorizer's SMTP (which doesn't work on Railway) by:
    1. Generating a new secure password
    2. Updating the user's password in Authorizer via admin API
    3. Sending the new credentials via Postmark API
    """
    import secrets
    import string
    import httpx

    settings = get_settings()
    email = request.email.lower().strip()

    # Validate configuration before proceeding
    if not settings.authorizer_url:
        return {"success": False, "error": "Authorizer not configured. Please contact support."}
    if not settings.authorizer_admin_secret:
        return {"success": False, "error": "Authorizer admin secret not configured. Please contact support."}
    if not settings.postmark_api_key:
        return {"success": False, "error": "Email service not configured. Please contact support."}

    # Generate a secure random password
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    new_password = ''.join(secrets.choice(alphabet) for _ in range(12))

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Admin login to Authorizer
            login_mutation = '''
            mutation AdminLogin($params: AdminLoginInput!) {
                _admin_login(params: $params) { message }
            }
            '''
            await client.post(
                f'{settings.authorizer_url}/graphql',
                headers={'Content-Type': 'application/json'},
                json={
                    'query': login_mutation,
                    'variables': {'params': {'admin_secret': settings.authorizer_admin_secret}}
                }
            )

            # Step 2: Check if user exists in Authorizer
            users_query = '''
            query AdminUsers($params: PaginatedInput!) {
                _users(params: $params) {
                    users { id email }
                }
            }
            '''
            users_resp = await client.post(
                f'{settings.authorizer_url}/graphql',
                headers={'Content-Type': 'application/json'},
                json={
                    'query': users_query,
                    'variables': {'params': {'pagination': {'page': 1, 'limit': 1000}}}
                }
            )
            users_result = users_resp.json() if users_resp.status_code == 200 else {}

            # Find user by email
            authorizer_user = None
            if users_result and isinstance(users_result, dict):
                users_data = users_result.get('data') or {}
                users_obj = users_data.get('_users') or {}
                users = users_obj.get('users') or []
            else:
                users = []
            for user in users:
                if user.get('email', '').lower() == email:
                    authorizer_user = user
                    break

            if not authorizer_user:
                # Don't reveal if user exists - return success anyway
                return {"success": True, "message": "If an account exists with this email, new credentials have been sent."}

            # Step 3: Delete and recreate user with new password (Authorizer doesn't allow direct password update)
            # First delete
            delete_mutation = '''
            mutation DeleteUser($params: DeleteUserInput!) {
                _delete_user(params: $params) { message }
            }
            '''
            await client.post(
                f'{settings.authorizer_url}/graphql',
                headers={'Content-Type': 'application/json'},
                json={
                    'query': delete_mutation,
                    'variables': {'params': {'email': email}}
                }
            )

            # Then signup with new password
            signup_mutation = '''
            mutation Signup($params: SignUpInput!) {
                signup(params: $params) {
                    message
                    user { id email }
                }
            }
            '''
            signup_resp = await client.post(
                f'{settings.authorizer_url}/graphql',
                headers={'Content-Type': 'application/json'},
                json={
                    'query': signup_mutation,
                    'variables': {
                        'params': {
                            'email': email,
                            'password': new_password,
                            'confirm_password': new_password
                        }
                    }
                }
            )
            signup_result = signup_resp.json() if signup_resp.status_code == 200 else {}

            new_user_id = None
            if signup_result and isinstance(signup_result, dict):
                signup_data = signup_result.get('data') or {}
                signup_obj = signup_data.get('signup') or {}
                user_obj = signup_obj.get('user')
                if user_obj:
                    new_user_id = user_obj.get('id')

                    # Verify email manually
                    update_mutation = '''
                    mutation UpdateUser($params: UpdateUserInput!) {
                        _update_user(params: $params) { id email_verified }
                    }
                    '''
                    await client.post(
                        f'{settings.authorizer_url}/graphql',
                        headers={'Content-Type': 'application/json'},
                        json={
                            'query': update_mutation,
                            'variables': {
                                'params': {
                                    'id': new_user_id,
                                    'email_verified': True,
                                    'given_name': email.split('@')[0]
                                }
                            }
                        }
                    )

                    # Update TubeVibe database with new Authorizer ID
                    auth_service = get_auth_service()
                    if auth_service.db:
                        await auth_service.db.update_user_by_email(
                            email,
                            {'authorizer_user_id': new_user_id, 'auth_provider': 'authorizer'}
                        )

            # Step 4: Send new credentials via Postmark
            email_response = await client.post(
                'https://api.postmarkapp.com/email',
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-Postmark-Server-Token': settings.postmark_api_key
                },
                json={
                    'From': f'{settings.postmark_sender_name} <{settings.postmark_from_email}>',
                    'To': email,
                    'Subject': 'Your TubeVibe Password Has Been Reset',
                    'HtmlBody': f'''
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2 style="color: #333;">Password Reset - TubeVibe</h2>
    <p>Hi,</p>
    <p>Your password has been reset. Here are your new login credentials:</p>
    <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
        <p><strong>Email:</strong> {email}</p>
        <p><strong>New Password:</strong> {new_password}</p>
    </div>
    <p>Please login with these credentials. We recommend changing your password after logging in.</p>
    <br>
    <p>Best regards,<br>TubeVibe Team</p>
</body>
</html>
                    ''',
                    'TextBody': f'Your TubeVibe password has been reset. Email: {email}, New Password: {new_password}',
                    'MessageStream': 'outbound'
                }
            )

            if email_response.status_code == 200:
                return {"success": True, "message": "New credentials have been sent to your email."}
            else:
                return {"success": False, "error": "Failed to send email. Please try again."}

    except Exception as e:
        # Log error with full traceback for debugging
        import traceback
        error_details = traceback.format_exc()
        print(f"Forgot password error: {e}")
        print(f"Traceback: {error_details}")

        # Check for common configuration issues
        if not settings.authorizer_url:
            return {"success": False, "error": "Authorizer not configured. Please contact support."}
        if not settings.authorizer_admin_secret:
            return {"success": False, "error": "Authorizer admin secret not configured. Please contact support."}
        if not settings.postmark_api_key:
            return {"success": False, "error": "Email service not configured. Please contact support."}

        return {"success": False, "error": f"An error occurred: {str(e)}"}


@router.post("/refresh")
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Refresh an access token.
    """
    auth_service = get_auth_service()

    # Verify current token
    user_id = auth_service.get_user_id_from_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Generate new token
    new_token = auth_service.create_access_token(user_id)

    return {
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": auth_service.access_token_expire_minutes * 60
    }


@router.post("/admin/fix-test-user-videos")
async def fix_test_user_videos(
    user_id: str = Depends(get_current_user_id)
):
    """
    One-time admin endpoint to reassign videos from test user to current user.
    This fixes videos saved with TEST_MODE enabled.

    IMPORTANT: Only run this once, then remove this endpoint.
    """
    from sqlalchemy import select, update, func
    from app.services.database_service import VideoModel
    import uuid

    auth_service = get_auth_service()

    if not auth_service.db:
        raise HTTPException(status_code=500, detail="Database not available")

    TEST_USER_ID = "00000000-0000-0000-0000-000000000001"

    try:
        # Count and update videos using SQLAlchemy
        async with auth_service.db.get_session() as session:
            # Count videos with test user ID
            count_result = await session.execute(
                select(func.count()).select_from(VideoModel).where(
                    VideoModel.user_id == uuid.UUID(TEST_USER_ID)
                )
            )
            test_video_count = count_result.scalar() or 0

            if test_video_count == 0:
                return {
                    "success": True,
                    "message": "No videos found with test user ID",
                    "videos_updated": 0
                }

            # Update videos from test user to current authenticated user
            from datetime import datetime
            await session.execute(
                update(VideoModel)
                .where(VideoModel.user_id == uuid.UUID(TEST_USER_ID))
                .values(user_id=uuid.UUID(user_id), updated_at=datetime.utcnow())
            )

        return {
            "success": True,
            "message": f"Successfully reassigned {test_video_count} videos from test user to your account",
            "videos_updated": test_video_count,
            "new_user_id": user_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fix videos: {str(e)}")


class AdminResetPasswordRequest(BaseModel):
    """Request body for admin password reset"""
    email: str
    new_password: str
    admin_secret: str


@router.post("/admin/reset-password")
async def admin_reset_password(request: AdminResetPasswordRequest):
    """
    TEMPORARY admin endpoint to reset a user's password.
    Requires admin_secret for security.

    IMPORTANT: Remove this endpoint after use.
    """
    import os

    # Simple security check - require a secret
    expected_secret = os.getenv("ADMIN_SECRET", "tubevibe-admin-2024")
    if request.admin_secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    auth_service = get_auth_service()

    if not auth_service.db:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        # Check if user exists
        user = await auth_service.db.get_user_by_email(request.email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Hash new password
        new_password_hash = auth_service.hash_password(request.new_password)

        # Update password in database using update_user method
        await auth_service.db.update_user(user["id"], {"password_hash": new_password_hash})

        return {
            "success": True,
            "message": f"Password reset for {request.email}",
            "user_id": user["id"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset password: {str(e)}")


@router.post("/admin/fix-pinecone-metadata")
async def fix_pinecone_metadata(
    user_id: str = Depends(get_current_user_id)
):
    """
    Re-upload all user's videos to Pinecone with correct user_id metadata.
    This fixes transcripts that were uploaded with TEST_MODE user_id.
    """
    from app.services.pinecone_service import get_pinecone_service
    from app.services.video_service import get_video_service

    auth_service = get_auth_service()
    pinecone_service = get_pinecone_service()
    video_service = get_video_service()

    if not auth_service.db:
        raise HTTPException(status_code=500, detail="Database not available")

    if not pinecone_service.is_initialized():
        raise HTTPException(status_code=500, detail="Pinecone service not initialized")

    try:
        # Get all videos for the current user (without transcripts first for listing)
        videos_result = await video_service.list_videos(user_id, per_page=100)
        if not videos_result.get("success"):
            raise HTTPException(status_code=400, detail=videos_result.get("error"))

        videos = videos_result.get("videos", [])
        updated_count = 0
        skipped_count = 0
        errors = []

        for video in videos:
            try:
                # Fetch each video with transcript included
                video_with_transcript = await video_service.get_video(
                    user_id=user_id,
                    video_id=video["id"],
                    include_transcript=True
                )

                if not video_with_transcript.get("success"):
                    errors.append(f"{video['title']}: Failed to fetch video details")
                    continue

                video_data = video_with_transcript.get("video", {})
                transcript = video_data.get("transcript")

                # Skip videos without transcripts
                if not transcript:
                    skipped_count += 1
                    continue

                # Re-upload to Pinecone with correct user_id and internal video_id
                metadata = {
                    "channel_name": video_data.get("channel_name"),
                    "duration_seconds": video_data.get("duration_seconds"),
                    "group_id": video_data.get("group_id"),
                    "youtube_id": video_data.get("youtube_id")  # Keep youtube_id for reference
                }

                result = await pinecone_service.upload_transcript(
                    user_id=user_id,  # Use the CORRECT user_id
                    video_id=video_data["id"],
                    title=video_data["title"],
                    transcript=transcript,
                    metadata=metadata
                )

                if result.get("success"):
                    # Update the pinecone_file_id in database
                    await video_service.update_video_pinecone_id(
                        video_data["id"],
                        result["file_id"]
                    )
                    updated_count += 1
                else:
                    errors.append(f"{video_data['title']}: {result.get('error')}")

            except Exception as e:
                errors.append(f"{video['title']}: {str(e)}")

        return {
            "success": True,
            "message": f"Re-uploaded {updated_count} transcripts to Pinecone with correct user_id",
            "videos_updated": updated_count,
            "videos_skipped": skipped_count,
            "total_videos": len(videos),
            "errors": errors if errors else None
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fix Pinecone metadata: {str(e)}")
