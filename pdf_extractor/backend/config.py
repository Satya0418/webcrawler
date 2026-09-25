import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env if present
load_dotenv(BASE_DIR / ".env")

def _resolve_dir(env_var: str, default_path: Path) -> Path:
    val = os.getenv(env_var)
    if not val:
        return default_path
    p = Path(val).expanduser()
    return p if p.is_absolute() else (BASE_DIR / p)


def get_watch_directories() -> list[Path]:
    """Returns list of resolved directories to watch for PDF ingestion."""
    raw = os.getenv("PDF_WATCH_DIR", "")
    dirs: list[Path] = []
    if raw:
        for part in raw.replace(";", ",").split(","):
            part = part.strip()
            if part:
                p = Path(part).expanduser()
                resolved = p if p.is_absolute() else (BASE_DIR / p)
                dirs.append(resolved)
    if not dirs:
        dirs.append(BASE_DIR / "watch_pdfs")
    
    # Automatically include ~/Desktop/Medical if present on the local machine
    desktop_med = Path("/Users/satya/Desktop/Medical")
    if desktop_med.exists() and desktop_med not in dirs:
        dirs.append(desktop_med)

    # Automatically include uploads directory
    uploads_dir = BASE_DIR / "uploads"
    if uploads_dir not in dirs:
        dirs.append(uploads_dir)

    # Automatically include web crawler's PDF cache if present
    crawler_cache = BASE_DIR.parent / "backend" / "data" / "pdf_cache"
    if crawler_cache.exists() and crawler_cache not in dirs:
        dirs.append(crawler_cache)

    for d in dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    return dirs


UPLOAD_DIR = _resolve_dir("UPLOAD_DIR", BASE_DIR / "uploads")
OUTPUT_DIR = _resolve_dir("OUTPUT_DIR", BASE_DIR / "outputs")
SAMPLE_DIR = _resolve_dir("SAMPLE_DIR", BASE_DIR / "sample_reports")

WATCH_DIRS = get_watch_directories()
WATCH_DIR = WATCH_DIRS[0]

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

# Database configuration (PostgreSQL production ready with SQLite local fallback)
DATABASE_URL = os.getenv("DATABASE_URL", "")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "pdf_extractor")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

# Construct default PostgreSQL URL if credentials provided and no explicit DATABASE_URL
if not DATABASE_URL and os.getenv("USE_POSTGRES", "false").lower() in ("true", "1", "yes"):
    DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Automated background scanner configuration
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "30"))
SCAN_ON_STARTUP = os.getenv("SCAN_ON_STARTUP", "True").lower() in ("true", "1", "yes")
DEFAULT_TARGET_SECTION = os.getenv("DEFAULT_TARGET_SECTION", "16")

# Client API Security (optional API key header validation)
API_KEY = os.getenv("API_KEY", "")

# Document processing constants
ENABLE_OCR = os.getenv("ENABLE_OCR", "True").lower() in ("true", "1", "yes")
OCR_CHAR_THRESHOLD = int(os.getenv("OCR_CHAR_THRESHOLD", "40"))  # chars per page
OCR_LANGUAGE = os.getenv("OCR_LANGUAGE", "eng")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
MAX_HEADING_LENGTH = 150
HEADER_MARGIN_RATIO = 0.12  # Top 12%
FOOTER_MARGIN_RATIO = 0.10  # Bottom 10%

