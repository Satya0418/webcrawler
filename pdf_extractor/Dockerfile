# Multi-architecture production Dockerfile for PDF Section Extraction Engine
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    WORKERS=2

WORKDIR /app

# Install essential system dependencies:
# - tesseract-ocr for image-based PDFs
# - libgl1 and libglib2.0-0 for PyMuPDF/Pillow image rasterization
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY backend ./backend
COPY frontend ./frontend
COPY sample_reports ./sample_reports
COPY tests ./tests

# Create storage directories
RUN mkdir -p uploads outputs && \
    touch uploads/.gitkeep outputs/.gitkeep

# Expose HTTP port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Launch uvicorn with production worker processes
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS}"]
