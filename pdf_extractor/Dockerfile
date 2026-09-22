# ==============================================================================
# Production Dockerfile for Intelligent PDF Section Extraction Engine
# Multi-architecture: Linux amd64 & arm64 (Apple Silicon / AWS Graviton)
# ==============================================================================
FROM python:3.11-slim-bookworm

# Prevent Python from writing .pyc files and buffer stdout/stderr for real-time logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    WORKERS=2 \
    ENABLE_OCR=true \
    OCR_LANGUAGE=eng

WORKDIR /app

# Install system runtime dependencies:
# - tesseract-ocr & tesseract-ocr-eng: Optical Character Recognition for scanned PDFs
# - poppler-utils: PDF utility suite (pdftoppm, pdfinfo, pdftotext)
# - libgl1, libglib2.0-0, libgomp1: Graphics, C-bindings & OpenMP runtimes for PyMuPDF/Pillow
# - fonts-dejavu-core: Standard TrueType fonts for PDF generation & font metrics
# - curl: Container healthcheck probe
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    fonts-dejavu-core \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user and group for security compliance
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -d /app -s /bin/bash appuser

# Install Python dependencies first for optimal Docker layer caching
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Create runtime storage directories and database file with proper permissions
RUN mkdir -p /app/uploads /app/outputs /app/sample_reports /app/data && \
    touch /app/uploads/.gitkeep /app/outputs/.gitkeep && \
    chown -R appuser:appuser /app

# Copy application source code
COPY --chown=appuser:appuser backend ./backend
COPY --chown=appuser:appuser frontend ./frontend
COPY --chown=appuser:appuser sample_reports ./sample_reports
COPY --chown=appuser:appuser tests ./tests

# Switch to non-root user for security
USER appuser

# Expose HTTP port (can be overridden at runtime via $PORT)
EXPOSE 8000

# Container healthcheck targeting the API health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

# Launch production server with configurable port and worker processes
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WORKERS:-2}"]
