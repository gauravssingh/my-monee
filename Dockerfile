# ==============================================================================
# MyMonee Multi-Stage Dockerfile (Portable Production Runtime)
# ==============================================================================

# --- Stage 1: Build React Frontend ---
FROM node:20-alpine AS frontend-builder
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- Stage 2: Python 3.12 Slim Runtime ---
FROM python:3.12-slim AS runner

# Install system dependencies (curl for container healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and group (UID/GID 1000)
RUN groupadd -g 1000 mymonee && \
    useradd -u 1000 -g mymonee -m -s /bin/bash mymonee

WORKDIR /app

# Install Python application dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Copy application source code
COPY src/ /app/src/
COPY config/ /app/config/

# Copy compiled frontend from Stage 1
COPY --from=frontend-builder /web/dist /app/web/dist

# Setup data and config directory mount points with proper ownership
RUN mkdir -p /data /config && \
    chown -R mymonee:mymonee /data /config /app

# Switch to non-root user
USER mymonee

# Container environment configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MYMONEE_DATA_DIR=/data \
    MYMONEE_CONFIG_DIR=/config \
    MYMONEE_APP_HOST=0.0.0.0 \
    MYMONEE_APP_PORT=8477 \
    MYMONEE_SCHEDULER_ENABLED=true

EXPOSE 8477

# Container healthcheck using the lightweight readiness probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8477/health/ready || exit 1

# Default command launches FastAPI server with graceful SIGTERM handling
CMD ["python", "-m", "expense_tracker"]
