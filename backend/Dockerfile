# TubeVibe Library Backend - Dockerfile
# Multi-stage build: Node.js for dashboard, Python for backend

# Stage 1: Build the dashboard
FROM node:20-alpine AS dashboard-builder

WORKDIR /dashboard

# Copy dashboard source
COPY dashboard/soft-ui-chat/package*.json ./
RUN npm ci

COPY dashboard/soft-ui-chat/ ./

# Set production API URL (will use relative path since served from same origin)
ENV VITE_API_URL=""

# Build dashboard
RUN npm run build


# Stage 2: Python backend with dashboard
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .

# Copy built dashboard from first stage
COPY --from=dashboard-builder /dashboard/dist /app/static/dashboard

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
