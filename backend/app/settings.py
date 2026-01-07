"""
TubeVibe Library - Application Settings
"""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    app_name: str = "TubeVibe Library"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://localhost:8000"

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # JWT Authentication
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 10080  # 7 days

    # Google OAuth
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    extension_google_client_id: Optional[str] = None

    # Authorizer Integration
    authorizer_url: Optional[str] = None  # e.g., https://authorizer-tubevibe.up.railway.app
    authorizer_admin_secret: Optional[str] = None
    authorizer_webhook_secret: Optional[str] = None

    # Database
    database_url: str

    # Pinecone
    pinecone_api_key: str
    pinecone_environment: str = "us-east-1"
    pinecone_assistant_name: str = "tubevibe-library"

    # Paddle Billing
    paddle_api_key: Optional[str] = None
    paddle_environment: str = "sandbox"
    paddle_notification_secret: Optional[str] = None
    paddle_premium_price_id: Optional[str] = None
    paddle_enterprise_price_id: Optional[str] = None

    # Email (Postmark)
    postmark_api_key: Optional[str] = None
    postmark_from_email: str = "summary@tubevibe.app"
    postmark_sender_name: str = "TubeVibe"
    postmark_youtube_template_id: Optional[str] = None
    use_postmark_email: bool = False

    # Rate Limiting
    rate_limit_per_minute: int = 60
    rate_limit_per_day: int = 1000

    # Plan Limits
    free_max_videos: int = 10
    free_max_groups: int = 2
    free_monthly_searches: int = 50
    free_summary_enabled: bool = False

    premium_max_videos: int = -1  # Unlimited
    premium_max_groups: int = -1
    premium_monthly_searches: int = -1
    premium_summary_enabled: bool = True

    # CORS
    cors_origins: str = "http://localhost:3000"
    cors_allow_credentials: bool = True

    # Sentry (Optional)
    sentry_dsn: Optional[str] = None

    # LLM Settings (for summarization)
    openai_api_key: Optional[str] = None
    llm_model: str = "gpt-4o-mini"  # Cost-effective model for summarization
    llm_max_tokens: int = 4000

    # Development
    use_mock_pinecone: bool = False
    use_mock_paddle: bool = False
    use_mock_database: bool = False
    allow_no_auth: bool = False

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string"""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    def get_plan_limits(self, plan_type: str) -> dict:
        """Get limits for a specific plan type"""
        if plan_type == "premium":
            return {
                "max_videos": self.premium_max_videos,
                "max_groups": self.premium_max_groups,
                "monthly_searches": self.premium_monthly_searches,
                "summary_enabled": self.premium_summary_enabled
            }
        elif plan_type == "enterprise":
            return {
                "max_videos": -1,
                "max_groups": -1,
                "monthly_searches": -1,
                "summary_enabled": True,
                "api_access": True
            }
        else:  # free
            return {
                "max_videos": self.free_max_videos,
                "max_groups": self.free_max_groups,
                "monthly_searches": self.free_monthly_searches,
                "summary_enabled": self.free_summary_enabled
            }

    class Config:
        env_file = "../.env"  # .env is in project root, not backend folder
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Allow extra environment variables


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
