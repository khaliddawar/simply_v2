# TubeVibe Library - Dockerfile
# Multi-stage build: Node.js for dashboard, Python for backend

# ============================================
# Stage 1: Build the React Dashboard
# ============================================
FROM node:20-alpine AS dashboard-builder

WORKDIR /dashboard

# Copy package files first for better caching
COPY dashboard/soft-ui-chat/package*.json ./
RUN npm ci

# Copy dashboard source
COPY dashboard/soft-ui-chat/ ./

# Set production API URL (empty = relative path since served from same origin)
ENV VITE_API_URL=""

# Build dashboard
RUN npm run build

# ============================================
# Stage 2: Python Backend with Dashboard
# ============================================
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

# Copy backend application code
COPY backend/app ./app

# Copy start script and make executable
COPY backend/start.sh ./start.sh
RUN chmod +x ./start.sh

# Copy built dashboard from first stage
COPY --from=dashboard-builder /dashboard/dist ./static/dashboard

# Expose port (Railway uses dynamic PORT)
EXPOSE 8000

# Run the application using start script
CMD ["./start.sh"]
