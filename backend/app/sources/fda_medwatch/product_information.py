"""
FDA MedWatch Product Information Handler.
Coordinates Path A intermediate page navigation to locate official FDA Label PDFs.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.sources.fda_medwatch.document_discovery import FDAMedWatchDocumentDiscovery
from app.sources.fda_medwatch.models import MedWatchDocumentInfo

logger = logging.getLogger(__name__)


class FDAMedWatchProductInformation:
    """Handles intermediate Product Information pages to retrieve official label documents."""

    def __init__(self, doc_discovery: Optional[FDAMedWatchDocumentDiscovery] = None) -> None:
        self.doc_discovery = doc_discovery or FDAMedWatchDocumentDiscovery()

    def discover_pdfs_from_product_page(
        self,
        html_content: str,
        page_url: str,
    ) -> List[MedWatchDocumentInfo]:
        """
        Parses intermediate Product Information page to discover all official FDA PDFs.
        """
        if not html_content:
            return []

        logger.info("FDA_MEDWATCH_PRODUCT_PAGE_INSPECTION_STARTED: %s", page_url)
        docs = self.doc_discovery.discover_documents(html_content, base_url=page_url)
        logger.info("FDA_MEDWATCH_PRODUCT_PAGE_INSPECTION_COMPLETED: Discovered %d PDFs from %s", len(docs), page_url)
        return docs
