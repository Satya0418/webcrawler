"""
FDA MedWatch Crawler Backward-Compatibility Module.
Re-exports FDAMedWatchCrawler, medwatch_crawler, and constants from the modular architecture.
"""
from app.sources.fda_medwatch.config import (
    MEDWATCH_PORTAL_URL,
    MEDWATCH_REPORT_URL,
    MEDWATCH_RSS_URL,
    OPENFDA_ENFORCEMENT_URL,
    OPENFDA_EVENT_URL,
    OPENFDA_LABEL_URL,
    SOURCE_ID,
)
from app.sources.fda_medwatch.crawler import (
    FDAMedWatchCrawler,
    MEDWATCH_CURATED_REGISTRY,
    medwatch_crawler,
)

__all__ = [
    "FDAMedWatchCrawler",
    "medwatch_crawler",
    "MEDWATCH_CURATED_REGISTRY",
    "MEDWATCH_PORTAL_URL",
    "MEDWATCH_REPORT_URL",
    "MEDWATCH_RSS_URL",
    "OPENFDA_ENFORCEMENT_URL",
    "OPENFDA_EVENT_URL",
    "OPENFDA_LABEL_URL",
    "SOURCE_ID",
]
