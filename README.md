# TubeVibe Library

A personal YouTube video transcript library that enables users to capture YouTube video transcripts, store them with Pinecone Assistant for RAG-powered search, and retrieve knowledge via natural language queries.

## Features

### Core Features
- **Save YouTube Transcripts** - Extract and save video transcripts to your personal library via Chrome extension
- **RAG-Powered Search** - Ask questions and get AI-powered answers from your saved videos using Pinecone Assistant
- **AI Video Summaries** - Generate structured summaries using Topic Detection + Chain of Density (GPT-4o-mini)
- **Email Summaries** - Send video summaries to any email address via Postmark
- **Video Organization** - Organize videos into custom groups with color coding

### Chrome Extension
- **Embedded Popup** - Seamless UI embedded directly on YouTube watch pages
- **One-Click Saving** - Save transcripts with a single click
- **Instant Summaries** - Generate AI summaries without leaving YouTube
- **Chat Interface** - Ask questions about any video in your library
- **TEST_MODE** - Development mode for testing without authentication

### Subscription Plans
- **Free Plan** - 10 videos, 2 groups, 50 searches/month
- **Premium Plan** - Unlimited videos, groups, and searches + AI summaries ($9.99/month)
- **Enterprise Plan** - Everything in Premium + API access, team collaboration ($29.99/month)

## Tech Stack

### Backend
| Component | Technology |
|-----------|------------|
| Framework | FastAPI (Python 3.11+) |
| Database | PostgreSQL (Railway) |
| ORM | SQLAlchemy (async) + asyncpg |
| Vector Store/RAG | Pinecone Assistant |
| LLM | OpenAI GPT-4o-mini |
| Email | Postmark |
| Payments | Paddle Billing |
| Auth | JWT + Google OAuth |

### Chrome Extension
| Component | Technology |
|-----------|------------|
| Manifest | Chrome Manifest V3 |
| Language | Vanilla JavaScript |
| Auth | Google Identity API |
| Payments | Paddle.js |

### Infrastructure
| Service | Provider |
|---------|----------|
| Backend Hosting | Railway |
| Database | Railway PostgreSQL |
| Vector Database | Pinecone (Standard) |
| Email | Postmark |
| Payments | Paddle |

## Architecture

```
+------------------+     +-------------------+     +------------------+
|                  |     |                   |     |                  |
|  Chrome          |---->|  FastAPI Backend  |---->|  PostgreSQL      |
|  Extension       |     |  (Railway)        |     |  (Railway)       |
|                  |     |                   |     |                  |
+------------------+     +--------+----------+     +------------------+
                                  |
                                  v
         +------------------------+------------------------+
         |                        |                        |
         v                        v                        v
+------------------+     +------------------+     +------------------+
|                  |     |                  |     |                  |
|  Pinecone        |     |  OpenAI          |     |  Postmark        |
|  Assistant       |     |  GPT-4o-mini     |     |  Email           |
|  (RAG)           |     |  (Summaries)     |     |                  |
+------------------+     +------------------+     +------------------+
```

## Project Structure

```
tubevibe-library/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application entry point
│   │   ├── settings.py          # Configuration and environment variables
│   │   ├── models/              # Pydantic models
│   │   │   ├── user.py          # User authentication models
│   │   │   ├── video.py         # Video and transcript models
│   │   │   ├── group.py         # Group organization models
│   │   │   └── subscription.py  # Payment/subscription models
│   │   ├── routes/              # API endpoints
│   │   │   ├── auth.py          # Authentication routes
│   │   │   ├── videos.py        # Video CRUD + summaries
│   │   │   ├── groups.py        # Group management
│   │   │   ├── search.py        # RAG search and chat
│   │   │   └── payments.py      # Paddle billing
│   │   ├── services/            # Business logic
│   │   │   ├── auth_service.py          # JWT, Google OAuth
│   │   │   ├── database_service.py      # PostgreSQL operations
│   │   │   ├── pinecone_service.py      # Pinecone Assistant
│   │   │   ├── summarization_service.py # Topic Detection + CoD
│   │   │   ├── email_service.py         # Postmark integration
│   │   │   └── video_service.py         # Video operations
│   │   └── middleware/          # Auth middleware
│   ├── tests/                   # Test files
│   ├── scripts/                 # Utility scripts
│   ├── requirements.txt         # Python dependencies
│   └── Dockerfile               # Container configuration
├── extension/
│   ├── manifest.json            # Chrome extension manifest (V3)
│   ├── background.js            # Service worker
│   ├── content.js               # YouTube page injection
│   ├── contents/
│   │   └── embedded-popup.js    # Embedded popup UI
│   ├── utils/
│   │   ├── tokenManager.js      # JWT token management
│   │   ├── paymentManager.js    # Paddle integration
│   │   └── securityLoader.js    # Security utilities
│   ├── assets/                  # Icons and images
│   ├── styles/                  # CSS stylesheets
│   └── config/                  # Configuration files
├── frontend/                    # Web application (optional)
├── TubeVibe_Page/              # Landing page
├── .env.template               # Environment variables template
├── project_plan_taskwise.md    # Detailed project plan
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ (for extension development)
- PostgreSQL database (Railway recommended)
- Pinecone account (Standard plan)
- Google Cloud Console project (for OAuth)
- OpenAI API key
- Postmark account (for email)
- Paddle account (for payments)

### Backend Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/TubeVibe-Library.git
   cd TubeVibe-Library
   ```

2. **Create virtual environment**
   ```bash
   cd backend
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp ../.env.template .env
   # Edit .env with your credentials
   ```

5. **Run development server**
   ```bash
   uvicorn app.main:app --reload
   ```

   The API will be available at `http://localhost:8000`
   - API Documentation: `http://localhost:8000/docs`
   - ReDoc: `http://localhost:8000/redoc`

### Chrome Extension Setup

1. **Navigate to extension directory**
   ```bash
   cd extension
   ```

2. **Configure the extension**
   - Update `config/` with your API endpoints
   - Set your Google OAuth client ID in `manifest.json`

3. **Load in Chrome**
   - Open Chrome and go to `chrome://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked"
   - Select the `extension/` directory

4. **Test the extension**
   - Navigate to any YouTube video
   - The TubeVibe popup should appear on the page

### Running Tests

```bash
cd backend
pytest tests/ -v
```

## Environment Variables

Copy `.env.template` to `.env` and configure the following:

### Required Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Secret key for JWT tokens (generate with `openssl rand -hex 32`) |
| `PINECONE_API_KEY` | Pinecone API key |
| `PINECONE_ASSISTANT_NAME` | Name of your Pinecone Assistant |
| `OPENAI_API_KEY` | OpenAI API key for summarization |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_ENV` | Environment (development/staging/production) | development |
| `DEBUG` | Enable debug mode | true |
| `POSTMARK_API_KEY` | Postmark API key for emails | - |
| `PADDLE_API_KEY` | Paddle API key for payments | - |
| `PADDLE_ENVIRONMENT` | Paddle environment (sandbox/production) | sandbox |
| `CORS_ORIGINS` | Allowed CORS origins | localhost |
| `ALLOW_NO_AUTH` | Skip auth for testing | false |

See [.env.template](.env.template) for the complete list.

## API Endpoints

### Authentication (`/api/auth`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/register` | Register new user with email/password |
| POST | `/login` | Login with email/password |
| POST | `/google` | Google OAuth (authorization code flow) |
| POST | `/google/verify` | Verify Google ID token (Chrome extension) |
| GET | `/google/login` | Initiate Google OAuth redirect |
| GET | `/google/callback` | Google OAuth callback handler |
| GET | `/me` | Get current user profile |
| POST | `/refresh` | Refresh access token |

### Videos (`/api/videos`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/` | Add video with transcript to library |
| GET | `/` | List user's videos (paginated) |
| GET | `/{video_id}` | Get specific video by ID |
| DELETE | `/{video_id}` | Delete video from library |
| PUT | `/{video_id}/group` | Move video to different group |
| GET | `/{video_id}/summary` | Generate AI summary (Topic Detection + CoD) |
| POST | `/{video_id}/email-summary` | Email video summary via Postmark |

### Groups (`/api/groups`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/` | Create new group |
| GET | `/` | List all groups |
| GET | `/{group_id}` | Get specific group |
| PUT | `/{group_id}` | Update group details |
| DELETE | `/{group_id}` | Delete group (videos become ungrouped) |

### Search (`/api/search`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/` | Search knowledge base (RAG) |
| POST | `/chat` | Multi-turn chat with conversation history |
| POST | `/summary` | Generate summary using Pinecone context |

### Payments (`/api/payments`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/checkout` | Create Paddle checkout session |
| GET | `/subscription` | Get current subscription status |
| POST | `/cancel` | Cancel subscription |
| POST | `/webhook` | Paddle webhook handler |
| GET | `/plans` | Get available subscription plans |

### Health (`/health`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check endpoint |

## Development Guide

### Development Mode (TEST_MODE)

For local development without full authentication:

1. Set `ALLOW_NO_AUTH=true` in your `.env` file
2. The API will accept requests without valid JWT tokens
3. A test user ID will be used for all operations

### Adding New Features

1. **Create model** in `backend/app/models/`
2. **Create service** in `backend/app/services/`
3. **Create routes** in `backend/app/routes/`
4. **Register router** in `backend/app/main.py`

### Extension Development

1. Make changes to extension files
2. Go to `chrome://extensions/`
3. Click the refresh icon on your extension
4. Test changes on YouTube

### Summarization Pipeline

The summarization uses a two-step process:

1. **Topic Detection** - Identifies distinct sections/topics in the transcript
2. **Chain of Density (CoD)** - Generates increasingly dense summaries for each section
3. **Executive Summary** - Combines section summaries with key takeaways

## Deployment

### Railway Backend

1. Connect GitHub repository to Railway
2. Add PostgreSQL service
3. Set environment variables in Railway dashboard
4. Deploy

### Chrome Extension

1. Create production build:
   ```bash
   cd extension
   ./build-production.bat  # Windows
   ```

2. Submit to Chrome Web Store:
   - Go to [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)
   - Upload the extension package
   - Fill in store listing details
   - Submit for review

## Cost Estimates

| Service | Monthly Cost |
|---------|-------------|
| Pinecone Standard | $50-100 |
| Railway Backend | $5-20 |
| Railway PostgreSQL | $5 |
| OpenAI API | $5-20 (usage-based) |
| Postmark | $10+ (usage-based) |
| **Total** | **$75-155** |

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

Proprietary - All rights reserved

## Links

- [Project Plan](project_plan_taskwise.md)
- [Pinecone Assistant Docs](https://docs.pinecone.io/guides/assistant/understanding-assistant)
- [Railway Docs](https://docs.railway.com/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Chrome Extensions Docs](https://developer.chrome.com/docs/extensions/)
