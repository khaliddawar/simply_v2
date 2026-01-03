# TubeVibe Library - Claude Code Instructions

## Project Overview

TubeVibe Library is a personal YouTube video transcript library that enables users to capture YouTube video transcripts, store them with Pinecone Assistant for RAG-powered search, and retrieve knowledge via natural language queries.

### Core Features
- Chrome Extension for capturing transcripts from YouTube videos
- Personal library to store and organize videos in groups
- RAG-powered semantic search using Pinecone Assistant
- AI-powered video summarization
- Email summaries via Postmark
- Subscription payments via Paddle Billing

## Architecture

```
Chrome Extension  -->  FastAPI Backend (Railway)  -->  Pinecone Assistant
                              |
                              v
                       PostgreSQL (Railway)
```

## Project Structure

```
TubeVibe-Library/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── settings.py        # Pydantic settings (env vars)
│   │   ├── models/            # Pydantic request/response models
│   │   │   ├── user.py
│   │   │   ├── video.py
│   │   │   ├── group.py
│   │   │   └── subscription.py
│   │   ├── routes/            # API endpoint routers
│   │   │   ├── auth.py        # /api/auth/* endpoints
│   │   │   ├── videos.py      # /api/videos/* endpoints
│   │   │   ├── groups.py      # /api/groups/* endpoints
│   │   │   ├── search.py      # /api/search/* endpoints
│   │   │   └── payments.py    # /api/payments/* endpoints
│   │   ├── services/          # Business logic services
│   │   │   ├── auth_service.py
│   │   │   ├── video_service.py
│   │   │   ├── database_service.py
│   │   │   ├── pinecone_service.py
│   │   │   ├── summarization_service.py
│   │   │   └── email_service.py
│   │   └── middleware/        # Custom middleware
│   ├── tests/                 # Backend tests
│   ├── requirements.txt
│   └── Dockerfile
├── extension/                 # Chrome Extension (Manifest V3)
│   ├── manifest.json          # Extension manifest
│   ├── background.js          # Service worker with message handlers
│   ├── content.js             # YouTube page content script
│   ├── contents/
│   │   ├── embedded-popup.js  # Main UI component injected into YouTube
│   │   ├── embedded-transcript.js
│   │   └── popup-transcript-bridge.js
│   ├── utils/
│   │   ├── tokenManager.js    # JWT token handling
│   │   ├── paymentManager.js  # Paddle integration
│   │   ├── supabaseClient.js  # Supabase client (if used)
│   │   └── securityLoader.js
│   ├── assets/               # Icons and images
│   └── styles/               # CSS files
├── frontend/                 # Web app (separate from extension)
├── TubeVibe_Page/           # Marketing/landing page
├── .env                     # Environment variables (project root)
├── .env.template            # Environment template
└── README.md
```

## Backend Details

### Settings Configuration

Settings are loaded from `.env` file at the **project root** (not in `backend/`). The `backend/app/settings.py` uses `pydantic_settings.BaseSettings` with:

```python
class Config:
    env_file = "../.env"  # Relative to backend/app/
```

### Service Pattern - Singletons

All services use the singleton pattern with `get_xxx_service()` functions:

```python
# Example usage
from app.services.video_service import get_video_service
video_service = get_video_service()

# All services follow this pattern:
# - get_auth_service()
# - get_video_service()
# - get_database_service()     # async
# - get_pinecone_service()
# - get_summarization_service()
# - get_email_service()
```

Services requiring database access are injected during app startup in `main.py`:
```python
video_service.set_database(db)
auth_service.set_database(db)
```

### API Routes

| Prefix | Router | Description |
|--------|--------|-------------|
| `/api/auth` | auth.py | Authentication (login, register, Google OAuth) |
| `/api/videos` | videos.py | Video CRUD operations |
| `/api/groups` | groups.py | Group management |
| `/api/search` | search.py | RAG search and summaries |
| `/api/payments` | payments.py | Paddle webhook handling |
| `/health` | main.py | Health check endpoint |

### Key Endpoints

```
POST /api/auth/register      - Register new user
POST /api/auth/login         - Login with email/password
POST /api/auth/google        - Google OAuth authentication
GET  /api/auth/me            - Get current user

POST /api/videos             - Add video with transcript
GET  /api/videos             - List user's videos
DELETE /api/videos/{id}      - Delete video

POST /api/search             - Search knowledge base
POST /api/search/summary     - Generate video summary

POST /api/groups             - Create group
GET  /api/groups             - List groups
```

## Extension Details

### Manifest V3 Structure

The extension uses Chrome Manifest V3 with:
- Service worker (`background.js`) - handles API calls and authentication
- Content scripts - inject UI into YouTube pages
- OAuth2 via `chrome.identity` API

### TEST_MODE Flag

Both `background.js` and `embedded-popup.js` have a `TEST_MODE` constant for development:

```javascript
// Set to true to bypass authentication for testing
const TEST_MODE = true;
const TEST_USER_ID = '00000000-0000-0000-0000-000000000001';
```

**Important**: Set `TEST_MODE = false` for production builds.

### Message Passing

Content scripts communicate with the background service worker via `chrome.runtime.sendMessage()`:

```javascript
// Message types handled in background.js:
- PING                     // Health check
- PROCESS_TRANSCRIPT       // Save video transcript
- USER_LOGIN               // Email/password login
- USER_SIGNUP              // Register new user
- USER_LOGOUT              // Logout
- GOOGLE_AUTH              // Google OAuth flow
- INITIATE_UPGRADE         // Paddle checkout
- GET_SUBSCRIPTION_STATUS  // Check subscription
```

### API_BASE_URL

```javascript
const API_BASE_URL = 'http://localhost:8000';  // Development
// Production: 'https://simply-backend-production.up.railway.app'
```

## Environment Variables

The `.env` file should be in the project root. Key variables:

### Database
```
DATABASE_URL=postgresql://...
```

### Pinecone
```
PINECONE_API_KEY=pcsk_...
PINECONE_ENVIRONMENT=us-east-1
PINECONE_ASSISTANT_NAME=tubevibe-library
```

### OpenAI (for summarization)
```
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

### Authentication
```
JWT_SECRET_KEY=<generate with: openssl rand -hex 32>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=10080
```

### Google OAuth
```
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
EXTENSION_GOOGLE_CLIENT_ID=...  # Separate OAuth client for extension
```

### Email (Postmark)
```
POSTMARK_API_KEY=...
POSTMARK_FROM_EMAIL=summary@tubevibe.app
POSTMARK_YOUTUBE_TEMPLATE_ID=...
USE_POSTMARK_EMAIL=true
```

### Paddle Billing
```
PADDLE_API_KEY=...
PADDLE_ENVIRONMENT=sandbox  # or production
PADDLE_NOTIFICATION_SECRET=...
PADDLE_PREMIUM_PRICE_ID=pri_...
```

### CORS
```
CORS_ORIGINS=http://localhost:3000,https://tubevibe.app
```

## Development Commands

### Backend

```bash
# Navigate to backend
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload

# Run from project root (alternative)
cd backend && uvicorn app.main:app --reload
```

Server runs at: `http://localhost:8000`
API docs: `http://localhost:8000/docs` (only in debug mode)

### Extension

1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select the `extension/` folder

### Tests

```bash
cd backend
pytest tests/ -v
```

## Common Patterns

### Async/Await

The entire backend uses async/await:
```python
async def create_video(...) -> Dict[str, Any]:
    # All database and external API calls are async
    result = await self.db.execute(query)
```

### Error Handling in Routes

```python
from fastapi import HTTPException

if not user:
    raise HTTPException(status_code=401, detail="Not authenticated")
```

### Database Transactions

```python
async with self.pool.acquire() as conn:
    async with conn.transaction():
        await conn.execute(...)
```

## Deployment

### Railway Backend

- Connected to GitHub repository
- Auto-deploys on push to main
- Uses `backend/Dockerfile`
- PostgreSQL service attached

### Extension

- Packaged via `npm run build` or `build-production.bat`
- Submitted to Chrome Web Store
- Production URL: Update `API_BASE_URL` in `background.js`

## Important Notes

1. **Environment file location**: `.env` is at project root, not in `backend/`
2. **TEST_MODE**: Remember to disable for production
3. **OAuth client IDs**: Extension uses different OAuth client than web app
4. **Pinecone Assistant**: Uses file-based RAG, not standard vector index
5. **Rate limiting**: Implemented via `slowapi` in FastAPI
6. **CORS**: Configure allowed origins for production deployment
