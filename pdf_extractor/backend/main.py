from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import BASE_DIR, DEBUG
from backend.database.db import init_db
from backend.api.upload import router as upload_router
from backend.api.files import router as files_router
from backend.api.extraction import router as extraction_router

init_db()

app = FastAPI(
    title="Intelligent PDF Section Extraction API",
    description="Deterministic hierarchical PDF section and subsection extractor.",
    version="1.0.0",
    debug=DEBUG,
)

# Enable CORS for local and web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(upload_router)
app.include_router(files_router)
app.include_router(extraction_router)

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
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "engine": "deterministic_hierarchical_extractor",
        "version": "1.0.0",
    }
