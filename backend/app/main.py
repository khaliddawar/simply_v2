"""
TubeVibe Library - Main Application Entry Point
"""
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.settings import get_settings
from app.routes import auth, videos, groups, search, payments

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    logger.info(f"Starting {settings.app_name} in {settings.app_env} mode")

    # Initialize database connection
    from app.services.database_service import get_database_service
    try:
        db = await get_database_service()
        logger.info("Database connection initialized")
        app.state.db = db

        # Inject database into auth service
        from app.services.auth_service import get_auth_service
        auth_service = get_auth_service()
        auth_service.set_database(db)
        app.state.auth = auth_service
        logger.info("Auth service configured with database")

        # Inject database into video service
        from app.services.video_service import get_video_service
        video_service = get_video_service()
        video_service.set_database(db)
        app.state.video = video_service
        logger.info("Video service configured with database")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    # Initialize Pinecone service
    from app.services.pinecone_service import get_pinecone_service
    try:
        pinecone = get_pinecone_service()
        if pinecone.is_initialized():
            logger.info("Pinecone service initialized")
        else:
            logger.warning("Pinecone service not initialized - check API key")
        app.state.pinecone = pinecone
    except Exception as e:
        logger.error(f"Failed to initialize Pinecone: {e}")

    yield

    # Shutdown
    logger.info("Shutting down application")

    # Close database connection
    if hasattr(app.state, 'db'):
        await app.state.db.close()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Personal video transcript library with RAG-powered search",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(videos.router, prefix="/api/videos", tags=["Videos"])
app.include_router(groups.router, prefix="/api/groups", tags=["Groups"])
app.include_router(search.router, prefix="/api/search", tags=["Search"])
app.include_router(payments.router, prefix="/api/payments", tags=["Payments"])


@app.get("/health")
async def health_check():
    """Health check endpoint for Railway"""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "environment": settings.app_env,
        "version": "1.0.3"  # Version to verify deployment
    }


@app.get("/api")
async def api_root():
    """API root endpoint"""
    return {
        "message": f"Welcome to {settings.app_name} API",
        "docs": "/docs" if settings.debug else "Disabled in production"
    }


# Serve dashboard static files
# In production (Docker), dashboard is at /app/static/dashboard
# In development, check for local build
dashboard_path = Path(__file__).parent.parent / "static" / "dashboard"
dev_dashboard_path = Path(__file__).parent.parent.parent / "dashboard" / "soft-ui-chat" / "dist"

# Use production path first, fall back to development path
if dashboard_path.exists():
    static_path = dashboard_path
    logger.info(f"Serving dashboard from production path: {dashboard_path}")
elif dev_dashboard_path.exists():
    static_path = dev_dashboard_path
    logger.info(f"Serving dashboard from development path: {dev_dashboard_path}")
else:
    static_path = None
    logger.warning("Dashboard not found - API only mode")

if static_path and (static_path / "assets").exists():
    # Mount static assets (js, css, etc.)
    app.mount("/assets", StaticFiles(directory=str(static_path / "assets")), name="assets")

    @app.get("/")
    async def serve_dashboard():
        """Serve the dashboard index.html"""
        return FileResponse(static_path / "index.html")

    # Catch-all for SPA routing - serve index.html for any non-API routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Handle SPA routing - return index.html for client-side routes"""
        # Don't catch API routes or special endpoints
        if full_path.startswith("api/") or full_path in ["health", "docs", "redoc", "openapi.json"]:
            return {"detail": "Not Found"}

        # Check if it's a static file
        file_path = static_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # Return index.html for SPA routing
        return FileResponse(static_path / "index.html")
else:
    @app.get("/")
    async def root():
        """Root endpoint - no dashboard available"""
        return {
            "message": f"Welcome to {settings.app_name} API",
            "docs": "/docs" if settings.debug else "Disabled in production",
            "note": "Dashboard not found. Build with: cd dashboard/soft-ui-chat && npm run build"
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug
    )
