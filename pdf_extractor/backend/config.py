import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
def _resolve_dir(env_var: str, default_path: Path) -> Path:
    val = os.getenv(env_var)
    if not val:
        return default_path
    p = Path(val)
    return p if p.is_absolute() else (BASE_DIR / p)


UPLOAD_DIR = _resolve_dir("UPLOAD_DIR", BASE_DIR / "uploads")
OUTPUT_DIR = _resolve_dir("OUTPUT_DIR", BASE_DIR / "outputs")
SAMPLE_DIR = _resolve_dir("SAMPLE_DIR", BASE_DIR / "sample_reports")
WATCH_DIR = _resolve_dir("PDF_WATCH_DIR", BASE_DIR / "watch_pdfs")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
WATCH_DIR.mkdir(parents=True, exist_ok=True)

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

