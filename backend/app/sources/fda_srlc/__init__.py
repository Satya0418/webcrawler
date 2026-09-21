"""
FDA Drug Safety-related Labeling Changes (SrLC) Source Package.
Conforms to the Hybrid Crawler Architecture.
"""
from app.sources.fda_srlc.adapter import FDASrLCAdapter, fda_srlc_adapter
from app.sources.fda_srlc.crawler import FDASrLCCrawler, fda_srlc_crawler
from app.sources.fda_srlc.date_parser import format_fda_date_to_report, parse_fda_date
from app.sources.fda_srlc.extractor import FDASrLCExtractor
from app.sources.fda_srlc.models import (
    FDASafetySections,
    FDASectionResult,
    FDASrLCStructuredResult,
)

__all__ = [
    "FDASrLCAdapter",
    "fda_srlc_adapter",
    "FDASrLCCrawler",
    "fda_srlc_crawler",
    "FDASrLCExtractor",
    "FDASrLCStructuredResult",
    "FDASafetySections",
    "FDASectionResult",
    "parse_fda_date",
    "format_fda_date_to_report",
]
