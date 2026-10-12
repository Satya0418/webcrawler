# ==============================================================================
# Production Dockerfile for Medicine Safety Web Crawler & Scraper Backend
# Multi-architecture: Linux amd64 & arm64 (Apple Silicon / AWS Graviton)
# ==============================================================================
FROM python:3.11-slim-bookworm

# Prevent Python from writing .pyc files and buffer stdout/stderr for real-time logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8001 \
    WORKERS=2

WORKDIR /app

# Install system runtime dependencies:
# - curl: Container healthcheck probe and network debugging
# - libxml2, libxslt1.1: XML / HTML parsing support for lxml & BeautifulSoup
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libxml2 \
    libxslt1.1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user and group for security compliance
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -d /app -s /bin/bash appuser

# Install Python dependencies first for optimal Docker layer caching
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Create runtime storage directories with proper permissions
RUN mkdir -p /app/data /app/data/pdf_cache && \
    chown -R appuser:appuser /app

# Copy application source code
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser scripts ./scripts
COPY --chown=appuser:appuser tests ./tests

# Switch to non-root user for security
USER appuser

# Expose HTTP port (default 8001)
EXPOSE 8001

# Container healthcheck targeting the API health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8001}/api/health || exit 1

# Launch production server with configurable port, worker processes, and reverse-proxy header support
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001} --workers ${WORKERS:-2} --proxy-headers --forwarded-allow-ips='*'"]
