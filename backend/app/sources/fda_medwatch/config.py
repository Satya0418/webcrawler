"""
FDA MedWatch Configuration.
Defines endpoints, timeouts, whitelists, caching paths, and regex patterns
for FDA MedWatch safety discovery and prescribing information extraction.
"""
from __future__ import annotations

import os
from pathlib import Path

SOURCE_ID = "FDA_MEDWATCH"
SOURCE_NAME = "FDA MedWatch"

# Official FDA MedWatch and Drugs@FDA URLs
MEDWATCH_PORTAL_URL = "https://www.fda.gov/safety/medwatch-fda-safety-information-and-adverse-event-reporting-program"
MEDWATCH_SAFETY_INFO_URL = "https://www.fda.gov/safety/medwatch-fda-safety-information-and-adverse-event-reporting-program/medical-product-safety-information"
MEDWATCH_RSS_URL = "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/medwatch/rss.xml"
DRUG_SAFETY_COMMUNICATIONS_URL = "https://www.fda.gov/drugs/drug-safety-and-availability/drug-safety-communications"
RECALLS_URL = "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts"
DRUGS_AT_FDA_OVERVIEW_URL = "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo="
MEDWATCH_REPORT_URL = "https://www.accessdata.fda.gov/scripts/medwatch/index.cfm?action=reporting.home"

# OpenFDA endpoints for supplemental adverse events and recall indexing
OPENFDA_EVENT_URL = "https://api.fda.gov/drug/event.json"
OPENFDA_ENFORCEMENT_URL = "https://api.fda.gov/drug/enforcement.json"
OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"

# Whitelisted official FDA domains for document discovery
OFFICIAL_FDA_DOMAINS = {
    "www.fda.gov",
    "fda.gov",
    "accessdata.fda.gov",
    "api.fda.gov",
    "search.usa.gov",
}

# Network settings
DEFAULT_HEADERS = {
    "User-Agent": "curl/8.7.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
}
DEFAULT_TIMEOUT = 12.0
CONNECT_TIMEOUT = 5.0
PDF_DOWNLOAD_TIMEOUT = 30.0
MAX_RETRIES = 3
BACKOFF_FACTOR = 1.5

# PDF Cache directory
_APP_ROOT = Path(__file__).resolve().parents[2]  # app
PDF_CACHE_DIR = _APP_ROOT / "data" / "pdf_cache"
PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Standard FDA Prescribing Information Sections
SECTION_ADVERSE_REACTIONS = "6"
SECTION_WARNINGS_PRECAUTIONS = "5"
SECTION_USE_IN_SPECIFIC_POPULATIONS = "8"
SECTION_PREGNANCY = "8.1"

# Standard error / not found messages
NOT_FOUND_IN_DOC_MSG = "NOT FOUND IN THIS PRODUCT INFORMATION DOCUMENT"
NO_OFFICIAL_PRODUCT_LABEL_FOUND = "PRODUCT_INFORMATION_DOCUMENT_NOT_FOUND"

# Direct prescribing information link patterns (Path B)
DIRECT_LABEL_PDF_PATTERNS = [
    r"accessdata\.fda\.gov/drugsatfda_docs/label/\d{4}/[A-Za-z0-9]+lbl\.pdf",
    r"accessdata\.fda\.gov/drugsatfda_docs/label/.*\.pdf",
    r"fda\.gov/.*lbl\.pdf",
]

# Product information intermediate link patterns (Path A)
PRODUCT_INFO_LINK_TEXT_PATTERNS = [
    r"\bproduct\s+information\b",
    r"\bprescribing\s+information\b",
    r"\bfull\s+prescribing\s+information\b",
    r"\bview\s+full\s+prescribing\s+information\b",
    r"\bfda-?approved\s+labeling\b",
    r"\bapproved\s+labeling\b",
    r"\bpackage\s+insert\b",
    r"\blabel(?:ing)?\b",
    r"\bfull\s+label\b",
    r"\bproduct\s+labeling\b",
]
