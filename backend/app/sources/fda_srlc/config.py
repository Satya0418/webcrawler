"""
Configuration for FDA Drug Safety-related Labeling Changes (SrLC).
"""
from pathlib import Path

# Base URLs
FDA_SRLC_BASE_URL = "https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges"
FDA_SRLC_SEARCH_URL = f"{FDA_SRLC_BASE_URL}/index.cfm?event=searchResult.page"
FDA_SRLC_DETAIL_URL = f"{FDA_SRLC_BASE_URL}/index.cfm?event=searchdetail.page"

# Timeouts & Retries
DEFAULT_TIMEOUT = 25.0
CONNECT_TIMEOUT = 10.0
MAX_RETRIES = 3
BACKOFF_FACTOR = 1.5

# Browser-like headers to avoid 403 blocks and ensure stable connections
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{FDA_SRLC_BASE_URL}/index.cfm",
    "Connection": "close",
    "Upgrade-Insecure-Requests": "1",
}

# FDA Prescribing Information Standard Sections (21 CFR 201.56 & 201.57)
SECTION_WARNINGS_PRECAUTIONS = "5"
SECTION_ADVERSE_REACTIONS = "6"
SECTION_USE_IN_SPECIFIC_POPULATIONS = "8"

# PDF Extractor Configuration
PDF_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "pdf_cache"
PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
