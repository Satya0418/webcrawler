"""
FDA MedWatch Module.
Exposes crawler, adapter, link discovery, document selection, and section extraction.
"""
from app.sources.fda_medwatch.adapter import FDAMedWatchAdapter, medwatch_adapter
from app.sources.fda_medwatch.article_discovery import FDAMedWatchArticleDiscovery
from app.sources.fda_medwatch.article_parser import FDAMedWatchArticleParser
from app.sources.fda_medwatch.crawler import FDAMedWatchCrawler, medwatch_crawler
from app.sources.fda_medwatch.document_discovery import FDAMedWatchDocumentDiscovery
from app.sources.fda_medwatch.link_discovery import FDAMedWatchLinkDiscovery
from app.sources.fda_medwatch.pdf_handler import FDAMedWatchPDFHandler
from app.sources.fda_medwatch.product_information import FDAMedWatchProductInformation
from app.sources.fda_medwatch.search import FDAMedWatchSearch
from app.sources.fda_medwatch.section_extractor import FDAMedWatchSectionExtractor
from app.sources.fda_medwatch.validator import FDAMedWatchValidator
from app.sources.fda_medwatch.version_selector import FDAMedWatchVersionSelector

__all__ = [
    "FDAMedWatchAdapter",
    "medwatch_adapter",
    "FDAMedWatchCrawler",
    "medwatch_crawler",
    "FDAMedWatchArticleDiscovery",
    "FDAMedWatchArticleParser",
    "FDAMedWatchDocumentDiscovery",
    "FDAMedWatchLinkDiscovery",
    "FDAMedWatchPDFHandler",
    "FDAMedWatchProductInformation",
    "FDAMedWatchSearch",
    "FDAMedWatchSectionExtractor",
    "FDAMedWatchValidator",
    "FDAMedWatchVersionSelector",
]
