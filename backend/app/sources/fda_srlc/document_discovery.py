"""
Document Discovery for FDA SrLC.
Finds and extracts links to official Approved Drug Label (PDF) documents.
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag

from app.sources.fda_srlc.config import FDA_SRLC_BASE_URL

logger = logging.getLogger(__name__)


class FDASrLCDocumentDiscovery:
    """Discovers official FDA Approved Drug Label (PDF) links in supplement panels."""

    def __init__(self, base_url: str = FDA_SRLC_BASE_URL) -> None:
        self.base_url = base_url

    def discover_label_pdf_url(self, panel_element: Tag) -> Optional[str]:
        """
        Extract the official Approved Drug Label (PDF) link from an accordion panel.

        Args:
            panel_element: BeautifulSoup Tag representing the accordion content <div>.

        Returns:
            Absolute URL string to the label PDF, or None if not found.
        """
        if not panel_element:
            return None

        # 1. Look for <a> with .pdf in href
        pdf_link = panel_element.find("a", href=re.compile(r"\.pdf", re.I))
        if pdf_link and pdf_link.get("href"):
            raw_url = pdf_link["href"].strip()
            full_url = urljoin(f"{self.base_url}/", raw_url)
            logger.info("FDA_SRLC_DOCUMENT_FOUND: Discovered Approved Drug Label PDF: %s", full_url)
            return full_url

        # 2. Look for text mentioning "Approved Drug Label" or "Label"
        label_link = panel_element.find("a", string=re.compile(r"approved\s+drug\s+label|label\s*\(pdf\)", re.I))
        if label_link and label_link.get("href"):
            raw_url = label_link["href"].strip()
            full_url = urljoin(f"{self.base_url}/", raw_url)
            logger.info("FDA_SRLC_DOCUMENT_FOUND: Discovered Label Link: %s", full_url)
            return full_url

        return None
