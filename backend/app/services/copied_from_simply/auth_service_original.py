import os
import logging
import json
from typing import Dict, Any, Optional, List
import traceback
import httpx
from datetime import datetime

# Import Supabase client
from supabase import create_client, Client

logger = logging.getLogger("bpt-auth-service")

class AuthService:
    """Service for handling user authentication and authorization using Supabase Auth"""
    
    def __init__(self):
        """Initialize Auth service with Supabase client"""
        self.supabase_url = os.getenv("SUPABASE_URL")
        # Check for key in multiple environment variable names  
        self.supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.supabase_key = (
            os.getenv("SUPABASE_KEY") or 
            os.getenv("SUPABASE_ANON_KEY") or 
            self.supabase_service_key
        )
        self.client = None
        self.initialized = False
        self.use_mock = (os.getenv("USE_MOCK_SUPABASE", "false").lower() == "true")
        
        # Try to initialize the client
        self._initialize_client()
        
    def _initialize_client(self):
        """Initialize the Supabase client"""
        if self.use_mock:
            logger.info("Using mock Auth service")
            self.initialized = True
            return
        
        try:
            if not self.supabase_url or not self.supabase_key:
                logger.error("Supabase URL or key not provided. Set SUPABASE_URL and one of: SUPABASE_KEY, SUPABASE_ANON_KEY, or SUPABASE_SERVICE_ROLE_KEY environment variables.")
                self.initialized = False
                return
            
            # Create Supabase client
            # Client with service role key (admin privileges)
            self.admin_client = create_client(self.supabase_url, self.supabase_key)
            # Maintain backward-compat alias
            self.client = self.admin_client
            # Public client with anon key (used for normal signup/login so Supabase enforces uniqueness)
            anon_key = os.getenv("SUPABASE_ANON_KEY")
            self.public_client = create_client(self.supabase_url, anon_key) if anon_key else self.admin_client
            self.initialized = True
            logger.info("Auth service initialized successfully (admin + public clients)")
            
        except Exception as e:
            logger.error(f"Error initializing Supabase client for Auth service: {str(e)}")
            self.initialized = False
            self.use_mock = True
            logger.warning("Falling back to mock Auth mode due to initialization error")
    
    async def _email_exists_admin(self, email: str) -> bool:
        """Check via Supabase Auth Admin REST endpoint if a user already exists."""
        if not self.supabase_url or not self.supabase_service_key:
            return False  # cannot check
        headers = {
            "apikey": self.supabase_service_key,
            "Authorization": f"Bearer {self.supabase_service_key}"
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.supabase_url}/auth/v1/admin/users", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    # Handle the response format: {"users": [...], "aud": "authenticated"}
                    if isinstance(data, dict) and "users" in data:
                        users_list = data["users"]
                        logger.info(f"Admin API returned {len(users_list)} total users, checking for {email}")
                        # Check if any user has the matching email
                        for user in users_list:
                            if isinstance(user, dict) and user.get("email") == email:
                                logger.info(f"Found existing user: {email} (confirmed: {user.get('email_confirmed_at') is not None})")
                                return True
                        logger.info(f"No user found with email: {email}")
                        return False
                    else:
                        logger.warning(f"Unexpected Admin API response format: {type(data)}")
                        return False
                else:
                    logger.warning(f"Admin API returned status {resp.status_code} for email check")
        except Exception as e:
            logger.warning(f"Admin API email check failed: {e}")
        return False

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user data by email address"""
        if self.use_mock:
            return None
            
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return None
            
        try:
            # Use the Admin REST API to find user by email
            if not self.supabase_url or not self.supabase_service_key:
                return None
                
            headers = {
                "apikey": self.supabase_service_key,
                "Authorization": f"Bearer {self.supabase_service_key}"
            }
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.supabase_url}/auth/v1/admin/users", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and "users" in data:
                        users_list = data["users"]
                        # Find user with matching email
                        for user in users_list:
                            if isinstance(user, dict) and user.get("email") == email:
                                logger.info(f"Found user by email: {email}")
                                return user
                        logger.info(f"No user found with email: {email}")
                        return None
                    else:
                        logger.warning(f"Unexpected Admin API response format: {type(data)}")
                        return None
                else:
                    logger.warning(f"Admin API returned status {resp.status_code} for user lookup")
                    return None
        except Exception as e:
            logger.warning(f"Failed to get user by email: {e}")
            return None

    async def register_user(self, email: str, password: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Register a new user with email and password"""
        if self.use_mock:
            # Return mock response
            return {
                "success": True,
                "user": {
                    "id": "mock-user-id",
                    "email": email,
                    "created_at": datetime.now().isoformat(),
                    "metadata": metadata or {}
                },
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Duplicate-email guard via Admin REST API
            if await self._email_exists_admin(email):
                return {
                    "success": False,
                    "error": "An account with this email already exists. Please try logging in instead.",
                    "error_code": "USER_EXISTS"
                }


            # Register user with Supabase Auth using correct Python syntax
            # The Python client raises exceptions instead of returning error objects
            if metadata:
                response = self.public_client.auth.sign_up({
                    "email": email,
                    "password": password,
                    "options": {
                        "data": metadata,
                        "email_redirect_to": "https://simply-firy.onrender.com/api/auth/verify"
                    }
                })
            else:
                response = self.public_client.auth.sign_up({
                    "email": email,
                    "password": password,
                    "options": {
                        "email_redirect_to": "https://simply-firy.onrender.com/api/auth/verify"
                    }
                })
            
            # Python client response structure is different
            # Check if response has the expected structure
            logger.info(f"Sign up response type: {type(response)}")
            logger.info(f"Sign up response: {response}")
            
            # Check if this is actually an existing user case
            user_obj = response.user if hasattr(response, 'user') else response
            if user_obj and hasattr(user_obj, 'email_confirmed_at') and user_obj.email_confirmed_at is not None:
                logger.warning(f"User {email} already exists and is confirmed - this should be a login, not signup")
                return {
                    "success": False,
                    "error": "An account with this email already exists. Please try logging in instead.",
                    "error_code": "USER_EXISTS"
                }
            
            # Return user data - the Python client should return a response object
            return {
                "success": True,
                "user": response.user if hasattr(response, 'user') else response,
                "session": response.session if hasattr(response, 'session') else None
            }
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Registration error: {error_message}")
            
            # Handle specific Supabase error cases with user-friendly messages
            if "rate limit exceeded" in error_message.lower():
                return {
                    "success": False,
                    "error": "Too many signup attempts. Please try again in a few minutes.",
                    "error_code": "RATE_LIMITED"
                }
            elif "already registered" in error_message.lower() or "user already exists" in error_message.lower() or "email already exists" in error_message.lower() or "already been registered" in error_message.lower():
                return {
                    "success": False,
                    "error": "An account with this email already exists. Please try logging in instead.",
                    "error_code": "USER_EXISTS"
                }
            elif "invalid email" in error_message.lower():
                return {
                    "success": False,
                    "error": "Please provide a valid email address.",
                    "error_code": "INVALID_EMAIL"
                }
            else:
                return {
                    "success": False,
                    "error": f"Registration failed. Please try again later.",
                    "error_code": "UNKNOWN_ERROR",
                    "debug_error": error_message  # Only for debugging
                }
    
    async def login_user(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate a user with email and password"""
        if self.use_mock:
            # Return mock response
            return {
                "success": True,
                "user": {
                    "id": "mock-user-id",
                    "email": email,
                    "created_at": datetime.now().isoformat(),
                    "last_sign_in_at": datetime.now().isoformat()
                },
                "token": "mock-auth-token",
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Login user with Supabase Auth using correct Python syntax
            response = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            # Python client response structure - simple logging
            logger.info(f"Login successful for user: {email}")
            
            # The response is gotrue.types.AuthResponse with user and session attributes
            # Convert to dictionary format for consistent API response
            session_dict = {
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token,
                "expires_in": response.session.expires_in,
                "token_type": response.session.token_type,
                "expires_at": response.session.expires_at
            }
            
            user_dict = {
                "id": response.user.id,
                "email": response.user.email,
                "created_at": response.user.created_at.isoformat() if response.user.created_at else None,
                "updated_at": response.user.updated_at.isoformat() if response.user.updated_at else None,
                "last_sign_in_at": response.user.last_sign_in_at.isoformat() if response.user.last_sign_in_at else None,
                "user_metadata": response.user.user_metadata,
                "app_metadata": response.user.app_metadata,
                "role": response.user.role
            }
            
            return {
                "success": True,
                "user": user_dict,
                "session": session_dict
            }
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Login error: {error_message}")
            
            # Handle specific Supabase error cases with user-friendly messages
            if "rate limit exceeded" in error_message.lower():
                return {
                    "success": False,
                    "error": "Too many login attempts. Please try again in a few minutes.",
                    "error_code": "RATE_LIMITED"
                }
            elif "invalid" in error_message.lower() and ("email" in error_message.lower() or "password" in error_message.lower() or "credentials" in error_message.lower()):
                return {
                    "success": False,
                    "error": "Invalid email or password",
                    "error_code": "INVALID_CREDENTIALS"
                }
            else:
                return {
                    "success": False,
                    "error": f"Authentication failed: {error_message}",
                    "error_code": "AUTH_ERROR"
                }
    
    async def logout_user(self, access_token: str) -> Dict[str, Any]:
        """Log out a user session"""
        if self.use_mock:
            # Return mock response
            return {
                "success": True,
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # 🔧 SAFE FIX: Direct sign_out() without set_session()
            # The set_session() was causing errors because it requires both access_token AND refresh_token
            # For logout, we can call sign_out() directly as per Supabase documentation
            response = self.client.auth.sign_out()
            
            # Return success
            return {
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error logging out user: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def reset_password(self, email: str) -> Dict[str, Any]:
        """Send a password reset email to the user"""
        if self.use_mock:
            # Return mock response
            return {
                "success": True,
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Send password reset email
            response = self.client.auth.reset_password_email(email)
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error sending password reset email: {response.error}")
                return {
                    "success": False,
                    "error": f"Error sending password reset email: {response.error}"
                }
                
            # Return success
            return {
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error sending password reset email: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def verify_token(self, access_token: str) -> Dict[str, Any]:
        """Verify an access token and return user data if valid"""
        if self.use_mock:
            # Return mock response
            return {
                "success": True,
                "user": {
                    "id": "mock-user-id",
                    "email": "mock@example.com",
                    "role": "user"
                },
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Verify token directly with Supabase
            response = self.client.auth.get_user(access_token)
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error verifying token: {response.error}")
                return {
                    "success": False,
                    "error": f"Error verifying token: {response.error}"
                }
                
            # Check if user exists
            if not response.user:
                logger.error("Token verification failed: No user found")
                return {
                    "success": False,
                    "error": "Invalid token: No user found"
                }
                
            # Convert user object to dictionary for consistent API response
            user_dict = {
                "id": response.user.id,
                "email": response.user.email,
                "created_at": response.user.created_at.isoformat() if response.user.created_at else None,
                "updated_at": response.user.updated_at.isoformat() if response.user.updated_at else None,
                "last_sign_in_at": response.user.last_sign_in_at.isoformat() if response.user.last_sign_in_at else None,
                "user_metadata": response.user.user_metadata,
                "app_metadata": response.user.app_metadata,
                "role": response.user.role
            }
                
            # Return user data
            return {
                "success": True,
                "user": user_dict
            }
            
        except Exception as e:
            logger.error(f"Error verifying token: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh an access token using a refresh token"""
        if self.use_mock:
            # Return mock response
            return {
                "success": True,
                "token": "mock-new-auth-token",
                "refresh_token": "mock-new-refresh-token",
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Refresh the token
            response = self.client.auth.refresh_session(refresh_token)
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error refreshing token: {response.error}")
                return {
                    "success": False,
                    "error": f"Error refreshing token: {response.error}"
                }
                
            # Return new tokens
            return {
                "success": True,
                "session": response.session
            }
            
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def update_user_metadata(self, user_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Update user metadata"""
        if self.use_mock:
            # Return mock response
            return {
                "success": True,
                "user": {
                    "id": user_id,
                    "metadata": metadata
                },
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Update user metadata
            response = self.client.auth.admin.update_user_by_id(
                user_id,
                {"user_metadata": metadata}
            )
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error updating user metadata: {response.error}")
                return {
                    "success": False,
                    "error": f"Error updating user metadata: {response.error}"
                }
                
            # Return updated user
            return {
                "success": True,
                "user": response.user
            }
            
        except Exception as e:
            logger.error(f"Error updating user metadata: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_user_by_id(self, user_id: str) -> Dict[str, Any]:
        """Get user by ID"""
        if self.use_mock:
            # Return mock response
            return {
                "success": True,
                "user": {
                    "id": user_id,
                    "email": f"user-{user_id}@example.com",
                    "created_at": datetime.now().isoformat(),
                    "user_metadata": {
                        "first_name": "Mock",
                        "last_name": "User",
                        "role": "user"
                    }
                },
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Get user from Supabase Admin API
            response = self.client.auth.admin.get_user_by_id(user_id)
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error getting user by ID: {response.error}")
                return {
                    "success": False,
                    "error": f"Error getting user by ID: {response.error}"
                }
                
            # Get user profile from database
            profile_response = self.client.table("user_profiles").select("*").eq("id", user_id).execute()
            profile_data = profile_response.data[0] if profile_response.data else {}
            
            # Combine user and profile data
            user_data = response.user
            user_data["profile"] = profile_data
            
            # Return user data
            return {
                "success": True,
                "user": user_data
            }
            
        except Exception as e:
            logger.error(f"Error getting user by ID: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def update_user_role(self, user_id: str, role: str) -> Dict[str, Any]:
        """Update user role"""
        if self.use_mock:
            # Return mock response
            return {
                "success": True,
                "user": {
                    "id": user_id,
                    "user_metadata": {
                        "role": role
                    }
                },
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Get current user data first
            user_result = await self.get_user_by_id(user_id)
            
            if not user_result["success"]:
                return user_result
                
            user_data = user_result["user"]
            metadata = user_data.get("user_metadata", {})
            
            # Update role in metadata
            metadata["role"] = role
            
            # Update user metadata
            response = self.client.auth.admin.update_user_by_id(
                user_id,
                {"user_metadata": metadata}
            )
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error updating user role: {response.error}")
                return {
                    "success": False,
                    "error": f"Error updating user role: {response.error}"
                }
            
            # Also update user_profiles table
            profile_response = self.client.table("user_profiles").update({"role": role}).eq("id", user_id).execute()
            
            # Return updated user data
            return {
                "success": True,
                "user": response.user
            }
            
        except Exception as e:
            logger.error(f"Error updating user role: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def list_users(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """List all users"""
        if self.use_mock:
            # Return mock response
            return {
                "success": True,
                "users": [
                    {
                        "id": "mock-user-1",
                        "email": "user1@example.com",
                        "created_at": datetime.now().isoformat(),
                        "user_metadata": {
                            "first_name": "Test",
                            "last_name": "User",
                            "role": "user"
                        }
                    },
                    {
                        "id": "mock-user-2",
                        "email": "user2@example.com",
                        "created_at": datetime.now().isoformat(),
                        "user_metadata": {
                            "first_name": "Another",
                            "last_name": "User",
                            "role": "editor"
                        }
                    }
                ],
                "total": 2,
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Get users from user_profiles table joined with auth.users
            # Note: This requires a custom Supabase function to get both auth users and profiles
            # For now, we'll get profiles and then fetch user data
            
            # Get user profiles
            profile_response = self.client.table("user_profiles").select("*").range(offset, offset + limit - 1).execute()
            profiles = profile_response.data
            
            # Get count of all profiles
            count_response = self.client.table("user_profiles").select("count", count="exact").execute()
            total = count_response.count if hasattr(count_response, "count") else len(profiles)
            
            # Fetch user data for each profile
            users = []
            for profile in profiles:
                user_id = profile.get("id")
                user_result = await self.get_user_by_id(user_id)
                if user_result["success"]:
                    user = user_result["user"]
                    user["profile"] = profile
                    users.append(user)
            
            # Return users with pagination info
            return {
                "success": True,
                "users": users,
                "total": total,
                "limit": limit,
                "offset": offset
            }
            
        except Exception as e:
            logger.error(f"Error listing users: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def change_password(self, user_id: str, current_password: str, new_password: str) -> Dict[str, Any]:
        """Change user password"""
        if self.use_mock:
            # Return mock response
            return {
                "success": True,
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Supabase doesn't have a direct API for changing password with current password verification
            # We need to verify the current password by trying to sign in, then update the password
            
            # Get user email first
            user_result = await self.get_user_by_id(user_id)
            if not user_result["success"]:
                return user_result
                
            user_email = user_result["user"].get("email")
            
            # Verify current password by signing in
            verify_result = await self.login_user(user_email, current_password)
            if not verify_result["success"]:
                return {
                    "success": False,
                    "error": "Current password is incorrect"
                }
            
            # Update password
            response = self.client.auth.admin.update_user_by_id(
                user_id,
                {"password": new_password}
            )
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error changing password: {response.error}")
                return {
                    "success": False,
                    "error": f"Error changing password: {response.error}"
                }
                
            # Return success
            return {
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error changing password: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def is_initialized(self) -> bool:
        """Check if the Auth service is initialized"""
        return self.initialized or self.use_mock 

    async def get_google_oauth_url(self) -> Dict[str, Any]:
        """Get Google OAuth URL for Chrome extension"""
        if self.use_mock:
            return {
                "success": True,
                "url": "https://accounts.google.com/oauth/mock-url",
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Generate Google OAuth URL using Supabase
            response = self.client.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": f"{self.supabase_url}/auth/v1/callback",
                    "scopes": "email profile"
                }
            })
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error generating Google OAuth URL: {response.error}")
                return {
                    "success": False,
                    "error": f"Error generating Google OAuth URL: {response.error}"
                }
                
            return {
                "success": True,
                "url": response.url
            }
            
        except Exception as e:
            logger.error(f"Error generating Google OAuth URL: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def exchange_google_code(self, code: str) -> Dict[str, Any]:
        """Exchange Google OAuth authorization code for tokens"""
        if self.use_mock:
            return {
                "success": True,
                "session": {
                    "access_token": "mock-google-access-token",
                    "refresh_token": "mock-google-refresh-token",
                    "expires_in": 3600
                },
                "user": {
                    "id": "mock-google-user-id",
                    "email": "user@gmail.com",
                    "user_metadata": {
                        "provider": "google",
                        "first_name": "John",
                        "last_name": "Doe"
                    }
                },
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Exchange authorization code for session using Supabase
            response = self.client.auth.exchange_code_for_session(code)
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error exchanging Google code: {response.error}")
                return {
                    "success": False,
                    "error": f"Error exchanging Google code: {response.error}"
                }
                
            # Extract session and user data
            session_dict = {
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token,
                "expires_in": response.session.expires_in,
                "token_type": response.session.token_type,
                "user": response.session.user
            }
            
            user_dict = {
                "id": response.session.user.id,
                "email": response.session.user.email,
                "user_metadata": response.session.user.user_metadata,
                "app_metadata": response.session.user.app_metadata,
                "created_at": response.session.user.created_at,
                "last_sign_in_at": response.session.user.last_sign_in_at
            }
            
            return {
                "success": True,
                "session": session_dict,
                "user": user_dict
            }
            
        except Exception as e:
            logger.error(f"Error exchanging Google code: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def confirm_signup(self, token: str) -> Dict[str, Any]:
        """Confirm user signup with email confirmation token"""
        if self.use_mock:
            return {
                "success": True,
                "user": {
                    "id": "mock-confirmed-user-id",
                    "email": "confirmed@example.com",
                    "email_confirmed_at": datetime.now().isoformat()
                },
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Confirm signup using Supabase
            response = self.client.auth.verify_otp({
                "token": token,
                "type": "signup"
            })
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error confirming signup: {response.error}")
                return {
                    "success": False,
                    "error": f"Email confirmation failed: {response.error}"
                }
            
            logger.info("Email confirmation successful")
            
            return {
                "success": True,
                "user": {
                    "id": response.user.id if response.user else None,
                    "email": response.user.email if response.user else None,
                    "email_confirmed_at": response.user.email_confirmed_at if response.user else None
                }
            }
            
        except Exception as e:
            logger.error(f"Error confirming signup: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def confirm_email_change(self, token: str) -> Dict[str, Any]:
        """Confirm email change with confirmation token"""
        if self.use_mock:
            return {
                "success": True,
                "user": {
                    "id": "mock-user-id",
                    "email": "newemail@example.com",
                    "email_confirmed_at": datetime.now().isoformat()
                },
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Confirm email change using Supabase
            response = self.client.auth.verify_otp({
                "token": token,
                "type": "email_change"
            })
            
            # Check for errors
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error confirming email change: {response.error}")
                return {
                    "success": False,
                    "error": f"Email change confirmation failed: {response.error}"
                }
            
            logger.info("Email change confirmation successful")
            
            return {
                "success": True,
                "user": {
                    "id": response.user.id if response.user else None,
                    "email": response.user.email if response.user else None,
                    "email_confirmed_at": response.user.email_confirmed_at if response.user else None
                }
            }
            
        except Exception as e:
            logger.error(f"Error confirming email change: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def reset_password_confirm(self, token: str, new_password: str) -> Dict[str, Any]:
        """Confirm password reset with token and set new password"""
        if self.use_mock:
            return {
                "success": True,
                "message": "Password reset successfully (mock mode)",
                "is_mock": True
            }
        
        if not self.initialized:
            self._initialize_client()
            
        if not self.initialized:
            return {
                "success": False,
                "error": "Auth service not initialized"
            }
            
        try:
            # Confirm password reset using Supabase
            response = self.client.auth.verify_otp({
                "token": token,
                "type": "recovery"
            })
            
            # Check for errors in verification
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error verifying reset token: {response.error}")
                return {
                    "success": False,
                    "error": f"Invalid or expired reset token: {response.error}"
                }
            
            # If verification successful, update the password
            if response.session:
                # Set the session temporarily to update password
                self.client.auth.set_session(response.session.access_token, response.session.refresh_token)
                
                # Update password
                password_response = self.client.auth.update_user({
                    "password": new_password
                })
                
                # Check for password update errors
                if hasattr(password_response, 'error') and password_response.error is not None:
                    logger.error(f"Error updating password: {password_response.error}")
                    return {
                        "success": False,
                        "error": f"Failed to update password: {password_response.error}"
                    }
                
                logger.info("Password reset confirmation successful")
                
                return {
                    "success": True,
                    "message": "Password reset successfully"
                }
            else:
                return {
                    "success": False,
                    "error": "No valid session returned from token verification"
                }
            
        except Exception as e:
            logger.error(f"Error confirming password reset: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            } 