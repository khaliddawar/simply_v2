from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
import time
import re

# Add app directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

# Import services and models
from app.services.auth_service import AuthService
from app.models.user import (
    UserCreate, 
    UserLogin, 
    UserResponse, 
    TokenResponse, 
    ResetPassword, 
    ChangePassword,
    UpdateUser,
    UpdateUserRole
)
from app.middleware.auth_middleware import get_current_user, get_admin_user, RoleChecker
from app.settings import ALLOW_TEST_EMAILS

logger = logging.getLogger("bpt-auth-routes")

# Initialize router
router = APIRouter(prefix="/auth", tags=["authentication"])

# Initialize security scheme
security = HTTPBearer()

# Role checkers
require_admin = RoleChecker(["admin"])
require_editor = RoleChecker(["admin", "editor"])

def validate_email_for_production(email: str) -> bool:
    """
    Strict email validation to prevent bounces and maintain deliverability.
    Rejects common test patterns and invalid formats.
    """
    # Convert to lowercase for checking
    email_lower = email.lower()
    
    # In development mode, allow test emails if explicitly enabled
    if ALLOW_TEST_EMAILS:
        # Still do basic format validation but allow test patterns
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(email_pattern, email))
    
    # Reject common test patterns that cause bounces
    test_patterns = [
        'test@',
        'example@',
        'fake@',
        'dummy@',
        'invalid@',
        'noreply@',
        'donotreply@',
        '@test.',
        '@example.',
        '@fake.',
        '@dummy.',
        '@invalid.',
        'test+',
        'example+',
        '.test',
        '.example'
    ]
    
    for pattern in test_patterns:
        if pattern in email_lower:
            return False
    
    # Basic RFC 5322 compliant email regex
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False
    
    # Additional checks for common invalid patterns
    if email_lower.endswith('.test') or email_lower.endswith('.example'):
        return False
    
    # Check for consecutive dots
    if '..' in email:
        return False
    
    # Check for valid TLD (basic check)
    domain = email.split('@')[1] if '@' in email else ''
    if not domain or '.' not in domain:
        return False
    
    tld = domain.split('.')[-1]
    if len(tld) < 2 or not tld.isalpha():
        return False
    
    return True

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """
    Register a new user with strict email validation
    """
    logger.info(f"Registering new user with email: {user_data.email}")
    
    # Validate email to prevent bounces
    if not validate_email_for_production(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid email address. Test emails and invalid formats are not accepted."
        )
    
    # Convert pydantic model to dict
    user_dict = user_data.dict()
    password = user_dict.pop("password")
    
    # Create auth service instance
    auth_service = AuthService()
    
    try:
        # Register user
        result = await auth_service.register_user(
            email=user_data.email,
            password=password,
            metadata=user_dict
        )
        
        logger.info(f"Auth service result: {result}")
        
        if not result.get("success"):
            error_msg = result.get("error", "Unknown error during registration")
            logger.error(f"Registration failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Registration failed: {error_msg}"
            )
        
        # Extract user data
        user_data_obj = result.get("user", {})
        session_data = result.get("session", {})
        
        logger.info(f"User data object: {user_data_obj}")
        logger.info(f"Session data: {session_data}")
        
        # Handle case where user needs email verification
        if not user_data_obj:
            # User created but needs verification - return minimal response
            return {
                "id": "pending_verification",
                "email": user_data.email,
                "first_name": user_data.first_name,
                "last_name": user_data.last_name,
                "role": "user",
                "company": user_data.company,
                "created_at": None,
                "last_sign_in_at": None,
                "requires_verification": True
            }
        
        # Handle different possible response structures from Supabase Python client
        user_id = None
        user_email = user_data.email
        user_metadata = {}
        created_at = None
        last_sign_in_at = None
        
        # Try different ways to access user data based on Python client structure
        if isinstance(user_data_obj, dict):
            user_id = user_data_obj.get("id")
            user_email = user_data_obj.get("email", user_data.email)
            user_metadata = user_data_obj.get("user_metadata", {}) or user_data_obj.get("raw_user_meta_data", {})
            created_at = user_data_obj.get("created_at")
            last_sign_in_at = user_data_obj.get("last_sign_in_at")
        elif hasattr(user_data_obj, 'id'):
            # Handle object-like response
            user_id = getattr(user_data_obj, 'id', None)
            user_email = getattr(user_data_obj, 'email', user_data.email)
            user_metadata = getattr(user_data_obj, 'user_metadata', {}) or getattr(user_data_obj, 'raw_user_meta_data', {})
            created_at = getattr(user_data_obj, 'created_at', None)
            last_sign_in_at = getattr(user_data_obj, 'last_sign_in_at', None)
        
        # Return user response
        return {
            "id": user_id or "pending_verification",
            "email": user_email,
            "first_name": user_metadata.get("first_name") or user_data.first_name,
            "last_name": user_metadata.get("last_name") or user_data.last_name,
            "role": user_metadata.get("role", "user"),
            "company": user_metadata.get("company") or user_data.company,
            "created_at": created_at,
            "last_sign_in_at": last_sign_in_at,
            "requires_verification": session_data is None
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error during registration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during registration"
        )

@router.post("/login", response_model=TokenResponse)
async def login(user_data: UserLogin):
    """
    Authenticate a user and get access token
    """
    logger.info(f"Login attempt for user: {user_data.email}")
    
    # Create auth service instance
    auth_service = AuthService()
    
    # Login user
    result = await auth_service.login_user(
        email=user_data.email,
        password=user_data.password
    )
    
    if not result.get("success"):
        error_msg = result.get("error", "Unknown error during login")
        logger.warning(f"Login failed for {user_data.email}: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {error_msg}"
        )
    
    # Get session data
    session = result.get("session")
    
    if not session:
        logger.error("No session returned from login")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to login: No session returned"
        )
    
    # Handle Session object (has attributes) or dict
    if hasattr(session, 'access_token'):
        # It's a Session object with attributes
        return {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "token_type": "bearer",
            "expires_in": getattr(session, 'expires_in', 3600)
        }
    else:
        # It's a dictionary
        return {
            "access_token": session.get("access_token"),
            "refresh_token": session.get("refresh_token"),
            "token_type": "bearer",
            "expires_in": session.get("expires_in", 3600)
        }

@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Log out a user session
    """
    # Get token
    token = credentials.credentials
    
    # Create auth service instance
    auth_service = AuthService()
    
    # Logout
    result = await auth_service.logout_user(token)
    
    if not result.get("success"):
        error_msg = result.get("error", "Unknown error during logout")
        logger.error(f"Logout failed: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Logout failed: {error_msg}"
        )
    
    return {"message": "Successfully logged out"}

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Refresh an access token using a refresh token
    """
    # Get refresh token
    refresh_token = credentials.credentials
    
    # Create auth service instance
    auth_service = AuthService()
    
    # Refresh token
    result = await auth_service.refresh_token(refresh_token)
    
    if not result.get("success"):
        error_msg = result.get("error", "Unknown error during token refresh")
        logger.error(f"Token refresh failed: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token refresh failed: {error_msg}"
        )
    
    # Get session data
    session = result.get("session")
    
    if not session:
        logger.error("No session returned from login")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to login: No session returned"
        )
    
    # Handle Session object (has attributes) or dict
    if hasattr(session, 'access_token'):
        # It's a Session object with attributes
        return {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "token_type": "bearer",
            "expires_in": getattr(session, 'expires_in', 3600)
        }
    else:
        # It's a dictionary
        return {
            "access_token": session.get("access_token"),
            "refresh_token": session.get("refresh_token"),
            "token_type": "bearer",
            "expires_in": session.get("expires_in", 3600)
        }

@router.get("/verify", response_class=HTMLResponse)
async def verify_email(request: Request):
    """
    Handle email verification redirect from Supabase.
    This handles both successful confirmations and errors (including expired tokens).
    """
    # Get query parameters from Supabase
    access_token = request.query_params.get("access_token")
    refresh_token = request.query_params.get("refresh_token")
    token_type = request.query_params.get("token_type")
    expires_in = request.query_params.get("expires_in")
    
    # Check for confirmation token (for email confirmation)
    token = request.query_params.get("token")
    confirmation_type = request.query_params.get("type")
    
    # Return a page that handles both success and error cases via JavaScript
    # This is necessary because Supabase sends errors in URL fragments (#) which
    # are not accessible server-side
    return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Email Verification - TubeVibe</title>
            <style>
            body {{ 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                max-width: 600px; 
                margin: 50px auto; 
                padding: 20px; 
                background-color: #f8f9fa;
            }}
            .container {{
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .error {{ 
                color: #d32f2f; 
                background: #ffebee; 
                padding: 20px; 
                border-radius: 8px; 
                border-left: 4px solid #d32f2f;
            }}
            .success {{ 
                color: #2e7d32; 
                background: #e8f5e9; 
                padding: 20px; 
                border-radius: 8px; 
                border-left: 4px solid #2e7d32;
            }}
            .loading {{
                color: #1976d2;
                background: #e3f2fd;
                padding: 20px;
                border-radius: 8px;
                border-left: 4px solid #1976d2;
            }}
            .instructions {{ 
                background: #f5f5f5; 
                padding: 20px; 
                border-radius: 8px; 
                margin-top: 20px; 
            }}
            h1 {{ color: #333; margin-bottom: 20px; }}
            .spinner {{
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 3px solid #f3f3f3;
                border-top: 3px solid #1976d2;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-right: 10px;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            </style>
        </head>
        <body>
        <div class="container">
            <h1>Email Verification</h1>
            <div id="status" class="loading">
                <div class="spinner"></div>
                Processing your email verification...
            </div>
        </div>

        <script>
            // Function to get URL fragment parameters
            function getFragmentParams() {{
                const fragment = window.location.hash.substring(1);
                const params = new URLSearchParams(fragment);
                return params;
            }}
            
            // Function to get URL query parameters  
            function getQueryParams() {{
                return new URLSearchParams(window.location.search);
            }}
            
            // Check for errors in URL fragment (from Supabase)
            const fragmentParams = getFragmentParams();
            const queryParams = getQueryParams();
            
            const error = fragmentParams.get('error');
            const errorDescription = fragmentParams.get('error_description');
            const accessToken = queryParams.get('access_token') || fragmentParams.get('access_token');
            const token = queryParams.get('token');
            
            setTimeout(() => {{
                const statusDiv = document.getElementById('status');
                
                if (error) {{
                    // Handle various error cases
                    let errorMessage = 'An error occurred during email verification.';
                    let errorDetail = '';
                    
                    if (error === 'access_denied') {{
                        if (errorDescription && errorDescription.includes('expired')) {{
                            errorMessage = 'Verification Link Expired';
                            errorDetail = 'Your email verification link has expired. Please sign up again to receive a new verification email.';
                        }} else {{
                            errorMessage = 'Verification Failed';
                            errorDetail = 'The verification link is invalid or has been used already.';
                        }}
                    }}
                    
                    statusDiv.className = 'error';
                    statusDiv.innerHTML = `
                        <h3>${{errorMessage}}</h3>
                        <p>${{errorDetail}}</p>
                        <p><strong>What to do next:</strong></p>
                        <ul>
                            <li>Go back to your TubeVibe extension</li>
                            <li>Try signing up again with your email</li>
                            <li>Check your email for a new verification link</li>
                        </ul>
                    `;
                }} else if (accessToken || token) {{
                    // Success case
                    statusDiv.className = 'success';
                    statusDiv.innerHTML = `
                        <h3>Email Verified Successfully! 🎉</h3>
                    <p>Your email has been verified. You can now sign in to your TubeVibe account.</p>
                <div class="instructions">
                            <h4>Next Steps:</h4>
                    <ol>
                        <li>Go back to YouTube</li>
                        <li>Open the TubeVibe extension sidebar</li>
                        <li>Click "Sign In" and use your credentials</li>
                        <li>Start generating AI summaries!</li>
                    </ol>
                </div>
                    `;
                }} else {{
                    // Unknown state
                    statusDiv.className = 'error';
                    statusDiv.innerHTML = `
                        <h3>Verification Status Unknown</h3>
                        <p>We couldn't determine the status of your email verification.</p>
                        <p>Please try signing in to your TubeVibe account, or contact support if you continue to have issues.</p>
                    `;
                }}
            }}, 1000);
        </script>
            </body>
            </html>
            """
            

@router.post("/password-reset")
async def request_password_reset(reset_data: ResetPassword):
    """
    Request a password reset email
    """
    logger.info(f"Password reset requested for: {reset_data.email}")
    
    # Create auth service instance
    auth_service = AuthService()
    
    # Send reset email
    result = await auth_service.reset_password(reset_data.email)
    
    if not result.get("success"):
        error_msg = result.get("error", "Unknown error during password reset request")
        logger.error(f"Password reset request failed: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password reset request failed: {error_msg}"
        )
    
    return {"message": "Password reset email sent successfully"}

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get information about the currently authenticated user
    """
    from app.services.supabase_client import get_supabase_client
    
    # Extract user metadata
    user_metadata = user.get("user_metadata", {})
    user_id = user.get("id")
    
    # Get user plan from user_profiles table
    plan_type = "free"  # Default
    subscription_status = "active"  # Default
    try:
        supabase = get_supabase_client()
        profile_resp = supabase.table("user_profiles").select("plan_type, subscription_status").eq("user_id", user_id).single().execute()
        if profile_resp.data:
            plan_type = profile_resp.data.get("plan_type", "free")
            subscription_status = profile_resp.data.get("subscription_status", "active")
    except Exception as e:
        logger.warning(f"Could not fetch user plan for {user_id}: {e}")
    
    # Return user response with plan information
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "first_name": user_metadata.get("first_name"),
        "last_name": user_metadata.get("last_name"),
        "role": user_metadata.get("role", "user"),
        "company": user_metadata.get("company"),
        "plan": plan_type,  # Add plan information for extension
        "subscription_status": subscription_status,  # Add subscription status
        "created_at": user.get("created_at"),
        "last_sign_in_at": user.get("last_sign_in_at")
    }

@router.put("/me", response_model=UserResponse)
async def update_current_user(
    update_data: UpdateUser,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Update the current user's profile information
    """
    user_id = user.get("id")
    logger.info(f"Updating profile for user ID: {user_id}")
    
    # Get existing metadata
    user_metadata = user.get("user_metadata", {})
    
    # Update metadata with new values
    update_dict = update_data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        if value is not None:
            user_metadata[key] = value
    
    # Create auth service instance
    auth_service = AuthService()
    
    # Update user
    result = await auth_service.update_user_metadata(user_id, user_metadata)
    
    if not result.get("success"):
        error_msg = result.get("error", "Unknown error during profile update")
        logger.error(f"Profile update failed for user {user_id}: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Profile update failed: {error_msg}"
        )
    
    # Get updated user
    updated_user = result.get("user", {})
    updated_metadata = updated_user.get("user_metadata", {})
    
    # Return updated user response
    return {
        "id": updated_user.get("id"),
        "email": updated_user.get("email"),
        "first_name": updated_metadata.get("first_name"),
        "last_name": updated_metadata.get("last_name"),
        "role": updated_metadata.get("role", "user"),
        "company": updated_metadata.get("company"),
        "created_at": updated_user.get("created_at"),
        "last_sign_in_at": updated_user.get("last_sign_in_at")
    }

@router.post("/change-password")
async def change_password(
    password_data: ChangePassword,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Change the current user's password
    """
    user_id = user.get("id")
    logger.info(f"Changing password for user ID: {user_id}")
    
    # Create auth service instance
    auth_service = AuthService()
    
    # Implement password change logic with Supabase
    result = await auth_service.change_password(
        user_id=user_id,
        current_password=password_data.current_password,
        new_password=password_data.new_password
    )
    
    if not result.get("success"):
        error_msg = result.get("error", "Unknown error during password change")
        logger.error(f"Password change failed for user {user_id}: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password change failed: {error_msg}"
        )
    
    return {"message": "Password changed successfully"}

@router.put("/users/{user_id}/role", dependencies=[Depends(require_admin)])
async def update_user_role(
    user_id: str,
    role_data: UpdateUserRole,
    admin_user: Dict[str, Any] = Depends(get_admin_user)
):
    """
    Update a user's role (admin only)
    """
    logger.info(f"Updating role for user ID: {user_id} to {role_data.role}")
    
    # Create auth service instance
    auth_service = AuthService()
    
    # Get user data and update role
    result = await auth_service.update_user_role(
        user_id=user_id,
        role=role_data.role
    )
    
    if not result.get("success"):
        error_msg = result.get("error", "Unknown error updating user role")
        logger.error(f"Role update failed for user {user_id}: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role update failed: {error_msg}"
        )
    
    return {
        "message": f"User role updated to {role_data.role}",
        "user_id": user_id,
        "role": role_data.role
    }

@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users(
    admin_user: Dict[str, Any] = Depends(get_admin_user),
    limit: int = 100,
    offset: int = 0
):
    """
    List all users (admin only)
    """
    logger.info(f"Listing users: limit={limit}, offset={offset}")
    
    # Create auth service instance
    auth_service = AuthService()
    
    # Get users from AuthService
    result = await auth_service.list_users(limit=limit, offset=offset)
    
    if not result.get("success"):
        error_msg = result.get("error", "Unknown error listing users")
        logger.error(f"Error listing users: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing users: {error_msg}"
        )
    
    # Format user data for response
    users = []
    for user_data in result.get("users", []):
        # Extract metadata
        metadata = user_data.get("user_metadata", {})
        profile = user_data.get("profile", {})
        
        # Combine data
        users.append({
            "id": user_data.get("id"),
            "email": user_data.get("email"),
            "first_name": metadata.get("first_name") or profile.get("first_name"),
            "last_name": metadata.get("last_name") or profile.get("last_name"),
            "role": metadata.get("role") or profile.get("role", "user"),
            "company": metadata.get("company") or profile.get("company"),
            "created_at": user_data.get("created_at"),
            "last_sign_in_at": user_data.get("last_sign_in_at")
        })
    
    return {
        "users": users,
        "total": result.get("total", len(users)),
        "limit": limit,
        "offset": offset
    }

@router.get("/google/url")
async def get_google_oauth_url():
    """
    Get Google OAuth URL for Chrome extension
    """
    # Create auth service instance
    auth_service = AuthService()
    
    # Get Google OAuth URL
    result = await auth_service.get_google_oauth_url()
    
    if not result.get("success"):
        error_msg = result.get("error", "Failed to get Google OAuth URL")
        logger.error(f"Google OAuth URL generation failed: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get Google OAuth URL: {error_msg}"
        )
    
    return {"url": result.get("url")}

@router.post("/google/callback", response_model=TokenResponse)
async def handle_google_oauth_callback(request: Request):
    """
    Handle Google OAuth callback for Chrome extension
    """
    try:
        # Get request data
        data = await request.json()
        code = data.get("code")
        
        if not code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Authorization code is required"
            )
        
        # Create auth service instance
        auth_service = AuthService()
        
        # Exchange code for tokens
        result = await auth_service.exchange_google_code(code)
        
        if not result.get("success"):
            error_msg = result.get("error", "Failed to exchange authorization code")
            logger.error(f"Google OAuth token exchange failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Token exchange failed: {error_msg}"
            )
        
        # Get session data
        session = result.get("session")
        
        if not session:
            logger.error("No session returned from token exchange")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange token: No session returned"
            )
        
        # Handle Session object (has attributes) or dict
        if hasattr(session, 'access_token'):
            # It's a Session object with attributes
            return {
                "access_token": session.access_token,
                "refresh_token": session.refresh_token,
                "token_type": "bearer",
                "expires_in": getattr(session, 'expires_in', 3600)
            }
        else:
            # It's a dictionary
            return {
                "access_token": session.get("access_token"),
                "refresh_token": session.get("refresh_token"),
                "token_type": "bearer",
                "expires_in": session.get("expires_in", 3600)
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Google OAuth callback: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during authentication"
        )

@router.post("/google")
async def authenticate_google_user(request: Request):
    """
    Handle Google authentication from Chrome extension
    Accepts Google user data and creates/updates user account
    """
    try:
        # Get request data
        data = await request.json()
        logger.info(f"Google auth request for email: {data.get('email', 'unknown')}")
        
        # Extract required fields
        google_id = data.get('google_id')
        email = data.get('email')
        name = data.get('name', '')
        given_name = data.get('given_name', '')
        family_name = data.get('family_name', '')
        picture = data.get('picture', '')
        
        if not google_id or not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required Google user data (google_id, email)"
            )
        
        # Create auth service instance
        auth_service = AuthService()
        
        # Create or find user with Google data
        user_metadata = {
            "google_id": google_id,
            "email": email,
            "full_name": name,
            "first_name": given_name,
            "last_name": family_name,
            "picture": picture,
            "provider": "google"
        }
        
        # Try to find existing user by email first
        existing_user = await auth_service.get_user_by_email(email)
        
        if existing_user:
            # User exists, return their data
            logger.info(f"Existing Google user found: {email}")
            return {
                "success": True,
                "user": existing_user,
                "message": "Successfully authenticated with Google"
            }
        else:
            # Create new user
            logger.info(f"Creating new Google user: {email}")
            
            # Generate a temporary password (won't be used for Google auth)
            import secrets
            temp_password = secrets.token_urlsafe(32)
            
            result = await auth_service.register_user(
                email=email,
                password=temp_password,
                metadata=user_metadata
            )
            
            if result.get("success"):
                return {
                    "success": True,
                    "user": result.get("user"),
                    "message": "Successfully created Google account"
                }
            else:
                logger.error(f"Failed to create Google user: {result.get('error')}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result.get("error", "Failed to create user account")
                )
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Google authentication: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during Google authentication"
        )

@router.get("/confirm", response_class=HTMLResponse)
async def confirm_email(token: str, type: str = "signup"):
    """
    Handle email confirmation from Supabase
    This endpoint is called when users click confirmation links in their email
    """
    try:
        logger.info(f"Processing email confirmation: type={type}, token={'***' + token[-8:] if len(token) > 8 else '***'}")
        
        # Create auth service instance
        auth_service = AuthService()
        
        # Verify the confirmation token with Supabase
        if type == "signup":
            result = await auth_service.confirm_signup(token)
        elif type == "email_change":
            result = await auth_service.confirm_email_change(token)
        else:
            logger.warning(f"Unknown confirmation type: {type}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid confirmation type"
            )
        
        if not result.get("success"):
            error_msg = result.get("error", "Confirmation failed")
            logger.error(f"Email confirmation failed: {error_msg}")
            
            # Return error page
            return HTMLResponse(content=f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>TubeVibe - Confirmation Failed</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        margin: 0;
                        padding: 40px 20px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        min-height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }}
                    .container {{
                        background: white;
                        padding: 40px;
                        border-radius: 12px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                        text-align: center;
                        max-width: 500px;
                        width: 100%;
                    }}
                    .error-icon {{
                        font-size: 48px;
                        color: #e74c3c;
                        margin-bottom: 20px;
                    }}
                    h1 {{
                        color: #2c3e50;
                        margin-bottom: 16px;
                        font-size: 24px;
                    }}
                    p {{
                        color: #7f8c8d;
                        line-height: 1.6;
                        margin-bottom: 30px;
                    }}
                    .btn {{
                        display: inline-block;
                        background: #3498db;
                        color: white;
                        padding: 12px 24px;
                        text-decoration: none;
                        border-radius: 6px;
                        font-weight: 500;
                        transition: background 0.3s;
                    }}
                    .btn:hover {{
                        background: #2980b9;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="error-icon">❌</div>
                    <h1>Confirmation Failed</h1>
                    <p>We couldn't confirm your email address. The confirmation link may have expired or already been used.</p>
                    <p><strong>Error:</strong> {error_msg}</p>
                    <a href="chrome-extension://ncgjkoodfmokaclkiofnnkihimdejjfm/popup.html" class="btn">Open TubeVibe Extension</a>
                </div>
            </body>
            </html>
            """, status_code=400)
        
        logger.info("Email confirmation successful")
        
        # Return success page
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>TubeVibe - Email Confirmed!</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 40px 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 12px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                    text-align: center;
                    max-width: 500px;
                    width: 100%;
                }}
                .success-icon {{
                    font-size: 48px;
                    color: #27ae60;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #2c3e50;
                    margin-bottom: 16px;
                    font-size: 24px;
                }}
                p {{
                    color: #7f8c8d;
                    line-height: 1.6;
                    margin-bottom: 30px;
                }}
                .btn {{
                    display: inline-block;
                    background: #27ae60;
                    color: white;
                    padding: 12px 24px;
                    text-decoration: none;
                    border-radius: 6px;
                    font-weight: 500;
                    transition: background 0.3s;
                    margin: 0 10px 10px 0;
                }}
                .btn:hover {{
                    background: #229954;
                }}
                .btn-secondary {{
                    background: #3498db;
                }}
                .btn-secondary:hover {{
                    background: #2980b9;
                }}
                .logo {{
                    width: 64px;
                    height: 64px;
                    margin: 0 auto 20px;
                    background: linear-gradient(45deg, #667eea, #764ba2);
                    border-radius: 12px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-weight: bold;
                    font-size: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="logo">TV</div>
                <div class="success-icon">✅</div>
                <h1>Email Confirmed Successfully!</h1>
                <p>Welcome to TubeVibe! Your email has been verified and your account is now active.</p>
                <p>Start getting AI-powered summaries of YouTube videos right in your browser.</p>
                <a href="chrome-extension://ncgjkoodfmokaclkiofnnkihimdejjfm/popup.html" class="btn">Open TubeVibe Extension</a>
                <a href="https://chrome.google.com/webstore/detail/tubevibe/ncgjkoodfmokaclkiofnnkihimdejjfm" class="btn btn-secondary">Install Extension</a>
            </div>
        </body>
        </html>
        """)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in email confirmation: {str(e)}")
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>TubeVibe - Error</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 40px 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 12px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                    text-align: center;
                    max-width: 500px;
                    width: 100%;
                }}
                .error-icon {{
                    font-size: 48px;
                    color: #e74c3c;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #2c3e50;
                    margin-bottom: 16px;
                    font-size: 24px;
                }}
                p {{
                    color: #7f8c8d;
                    line-height: 1.6;
                    margin-bottom: 30px;
                }}
                .btn {{
                    display: inline-block;
                    background: #3498db;
                    color: white;
                    padding: 12px 24px;
                    text-decoration: none;
                    border-radius: 6px;
                    font-weight: 500;
                    transition: background 0.3s;
                }}
                .btn:hover {{
                    background: #2980b9;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error-icon">⚠️</div>
                <h1>Something Went Wrong</h1>
                <p>We encountered an unexpected error while processing your request. Please try again later.</p>
                <a href="chrome-extension://ncgjkoodfmokaclkiofnnkihimdejjfm/popup.html" class="btn">Open TubeVibe Extension</a>
            </div>
        </body>
        </html>
        """, status_code=500)

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(token: str):
    """
    Handle password reset from Supabase
    Shows a form for users to enter their new password
    """
    try:
        logger.info(f"Processing password reset request: token={'***' + token[-8:] if len(token) > 8 else '***'}")
        
        # Return password reset form
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>TubeVibe - Reset Password</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 40px 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 12px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                    text-align: center;
                    max-width: 400px;
                    width: 100%;
                }}
                .logo {{
                    width: 64px;
                    height: 64px;
                    margin: 0 auto 20px;
                    background: linear-gradient(45deg, #667eea, #764ba2);
                    border-radius: 12px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-weight: bold;
                    font-size: 20px;
                }}
                h1 {{
                    color: #2c3e50;
                    margin-bottom: 16px;
                    font-size: 24px;
                }}
                p {{
                    color: #7f8c8d;
                    line-height: 1.6;
                    margin-bottom: 30px;
                }}
                .form-group {{
                    margin-bottom: 20px;
                    text-align: left;
                }}
                label {{
                    display: block;
                    margin-bottom: 5px;
                    color: #2c3e50;
                    font-weight: 500;
                }}
                input[type="password"] {{
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #ecf0f1;
                    border-radius: 6px;
                    font-size: 16px;
                    transition: border-color 0.3s;
                    box-sizing: border-box;
                }}
                input[type="password"]:focus {{
                    outline: none;
                    border-color: #3498db;
                }}
                .btn {{
                    width: 100%;
                    background: #27ae60;
                    color: white;
                    padding: 12px 24px;
                    border: none;
                    border-radius: 6px;
                    font-weight: 500;
                    font-size: 16px;
                    cursor: pointer;
                    transition: background 0.3s;
                }}
                .btn:hover {{
                    background: #229954;
                }}
                .btn:disabled {{
                    background: #bdc3c7;
                    cursor: not-allowed;
                }}
                .error {{
                    color: #e74c3c;
                    margin-top: 10px;
                    display: none;
                }}
                .success {{
                    color: #27ae60;
                    margin-top: 10px;
                    display: none;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="logo">TV</div>
                <h1>Reset Your Password</h1>
                <p>Enter your new password below to complete the reset process.</p>
                
                <form id="resetForm">
                    <div class="form-group">
                        <label for="password">New Password</label>
                        <input type="password" id="password" name="password" required minlength="8" 
                               placeholder="Enter your new password">
                    </div>
                    <div class="form-group">
                        <label for="confirmPassword">Confirm Password</label>
                        <input type="password" id="confirmPassword" name="confirmPassword" required 
                               placeholder="Confirm your new password">
                    </div>
                    <button type="submit" class="btn" id="submitBtn">Reset Password</button>
                    <div class="error" id="errorMsg"></div>
                    <div class="success" id="successMsg"></div>
                </form>
            </div>
            
            <script>
                document.getElementById('resetForm').addEventListener('submit', async function(e) {{
                    e.preventDefault();
                    
                    const password = document.getElementById('password').value;
                    const confirmPassword = document.getElementById('confirmPassword').value;
                    const submitBtn = document.getElementById('submitBtn');
                    const errorMsg = document.getElementById('errorMsg');
                    const successMsg = document.getElementById('successMsg');
                    
                    // Hide previous messages
                    errorMsg.style.display = 'none';
                    successMsg.style.display = 'none';
                    
                    // Validate passwords match
                    if (password !== confirmPassword) {{
                        errorMsg.textContent = 'Passwords do not match';
                        errorMsg.style.display = 'block';
                        return;
                    }}
                    
                    // Validate password strength
                    if (password.length < 8) {{
                        errorMsg.textContent = 'Password must be at least 8 characters long';
                        errorMsg.style.display = 'block';
                        return;
                    }}
                    
                    // Disable button and show loading
                    submitBtn.disabled = true;
                    submitBtn.textContent = 'Resetting...';
                    
                    try {{
                        const response = await fetch('/api/auth/reset-password-confirm', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                            }},
                            body: JSON.stringify({{
                                token: '{token}',
                                password: password
                            }})
                        }});
                        
                        const result = await response.json();
                        
                        if (response.ok) {{
                            successMsg.textContent = 'Password reset successfully! You can now sign in with your new password.';
                            successMsg.style.display = 'block';
                            submitBtn.textContent = 'Success!';
                            
                            // Redirect after 3 seconds
                            setTimeout(() => {{
                                window.location.href = 'chrome-extension://ncgjkoodfmokaclkiofnnkihimdejjfm/popup.html';
                            }}, 3000);
                        }} else {{
                            errorMsg.textContent = result.detail || 'Failed to reset password. Please try again.';
                            errorMsg.style.display = 'block';
                            submitBtn.disabled = false;
                            submitBtn.textContent = 'Reset Password';
                        }}
                    }} catch (error) {{
                        errorMsg.textContent = 'Network error. Please check your connection and try again.';
                        errorMsg.style.display = 'block';
                        submitBtn.disabled = false;
                        submitBtn.textContent = 'Reset Password';
                    }}
                }});
            </script>
        </body>
        </html>
        """)
        
    except Exception as e:
        logger.error(f"Unexpected error in password reset page: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )

@router.post("/reset-password-confirm")
async def reset_password_confirm(request: Request):
    """
    Handle password reset confirmation
    Called by the JavaScript form on the reset password page
    """
    try:
        data = await request.json()
        token = data.get("token")
        new_password = data.get("password")
        
        if not token or not new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token and password are required"
            )
        
        logger.info(f"Processing password reset confirmation: token={'***' + token[-8:] if len(token) > 8 else '***'}")
        
        # Create auth service instance
        auth_service = AuthService()
        
        # Reset password with Supabase
        result = await auth_service.reset_password_confirm(token, new_password)
        
        if not result.get("success"):
            error_msg = result.get("error", "Password reset failed")
            logger.error(f"Password reset confirmation failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        
        logger.info("Password reset confirmation successful")
        
        return {
            "success": True,
            "message": "Password reset successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in password reset confirmation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during password reset"
        ) 