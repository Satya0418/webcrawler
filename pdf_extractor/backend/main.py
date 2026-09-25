import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import BASE_DIR, DEBUG
from backend.database.db import init_db, check_db_health, DB_DIALECT
from backend.services.scanner_service import scanner_service

# Routers
from backend.api.upload import router as upload_router
from backend.api.files import router as files_router
from backend.api.extraction import router as extraction_router
from backend.api.products import router as products_router

logger = logging.getLogger("pdf_extractor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager:
    Initializes database schema and starts automated 30-minute background folder scanner.
    """
    logger.info("Initializing PDF Section Extraction System...")
    init_db()
    scanner_service.start()
    yield
    logger.info("Shutting down PDF Section Extraction System...")
    await scanner_service.stop()


app = FastAPI(
    title="Intelligent PDF Section Extraction & Product API",
    description=(
        "Production-grade deterministic PDF section extractor and automated 30-minute "
        "folder scanner with instant Section 16 retrieval for client websites."
    ),
    version="1.1.0",
    debug=DEBUG,
    lifespan=lifespan,
)

# Enable CORS for cross-origin client website access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(products_router)     # /api/v1/products/... & /api/v1/scanner/...
app.include_router(upload_router)       # /api/upload
app.include_router(files_router)        # /api/files/...
app.include_router(extraction_router)   # /api/extract/...

# Mount frontend directory for static assets
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def serve_index():
    """Serves the main extraction dashboard UI."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "status": "online",
        "service": "Intelligent PDF Section Extraction System",
        "docs": "/docs",
        "client_api": "/api/v1/products/section-16",
    }


@app.get("/api/health")
async def health_check():
    """Comprehensive system, database, and background scanner health check."""
    db_health = check_db_health()
    scanner_info = scanner_service.get_status()
    
    overall_status = "healthy" if db_health.get("connected") else "degraded"
    
    return {
        "status": overall_status,
        "engine": "deterministic_hierarchical_extractor",
        "database": {
            "status": db_health.get("status"),
            "dialect": DB_DIALECT,
            "connected": db_health.get("connected"),
        },
        "background_scanner": {
            "status": scanner_info.get("status"),
            "watch_directory": scanner_info.get("watch_directory"),
            "interval_minutes": scanner_info.get("scan_interval_minutes"),
            "target_section": scanner_info.get("target_section"),
            "total_products_indexed": scanner_info.get("total_products_indexed"),
            "last_scan": scanner_info.get("last_scan_time"),
            "next_scan": scanner_info.get("next_scan_time"),
        },
        "version": "1.1.0",
    }
