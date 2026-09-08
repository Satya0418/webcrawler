import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
SAMPLE_DIR = BASE_DIR / "sample_reports"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

# Document processing constants
ENABLE_OCR = os.getenv("ENABLE_OCR", "True").lower() in ("true", "1", "yes")
OCR_CHAR_THRESHOLD = int(os.getenv("OCR_CHAR_THRESHOLD", "40"))  # chars per page
OCR_LANGUAGE = os.getenv("OCR_LANGUAGE", "eng")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
MAX_HEADING_LENGTH = 150
HEADER_MARGIN_RATIO = 0.12  # Top 12%
FOOTER_MARGIN_RATIO = 0.10  # Bottom 10%
