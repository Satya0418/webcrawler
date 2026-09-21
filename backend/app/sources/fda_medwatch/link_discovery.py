"""
FDA MedWatch Link Discovery.
Detects official FDA Product Information and Prescribing Information links
from MedWatch articles, supporting:
- PATH A: Intermediate Product Information Page -> PDF
- PATH B: Direct Full Prescribing Information PDF Link
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from app.sources.fda_medwatch.config import (
    DIRECT_LABEL_PDF_PATTERNS,
    OFFICIAL_FDA_DOMAINS,
    PRODUCT_INFO_LINK_TEXT_PATTERNS,
)
from app.sources.fda_medwatch.models import ProductInfoLink

logger = logging.getLogger(__name__)


class FDAMedWatchLinkDiscovery:
    """Discovers and categorizes links to authoritative FDA product labeling documents."""

    def __init__(self) -> None:
        # Pre-compile text patterns
        self.text_regexes = [
            re.compile(p, re.IGNORECASE) for p in PRODUCT_INFO_LINK_TEXT_PATTERNS
        ]
        self.direct_pdf_regexes = [
            re.compile(p, re.IGNORECASE) for p in DIRECT_LABEL_PDF_PATTERNS
        ]

    def is_official_fda_domain(self, url: str) -> bool:
        """Validates that a URL originates from an official FDA domain."""
        if not url:
            return False
        try:
            parsed = urlparse(url)
            domain = (parsed.netloc or "").lower()
            if ":" in domain:
                domain = domain.split(":")[0]
            # Strip subdomains down or check exact whitelist
            if domain in OFFICIAL_FDA_DOMAINS:
                return True
            if domain.endswith(".fda.gov") or domain.endswith(".fda.hhs.gov"):
                return True
            return False
        except Exception:
            return False

    def is_direct_pdf_url(self, url: str) -> bool:
        """Determines if a URL points directly to an official FDA label PDF."""
        clean_url = url.split("?")[0].split("#")[0].lower()
        if not clean_url.endswith(".pdf"):
            return False
        for reg in self.direct_pdf_regexes:
            if reg.search(url):
                return True
        # Generic check for label PDF on accessdata.fda.gov
        if "accessdata.fda.gov" in url and "/label/" in url and clean_url.endswith(".pdf"):
            return True
        return clean_url.endswith("lbl.pdf")

    def matches_label_link_text(self, text: str) -> bool:
        """Matches anchor text against flexible product information / prescribing information patterns."""
        if not text:
            return False
        clean_text = " ".join(text.strip().split())
        for reg in self.text_regexes:
            if reg.search(clean_text):
                return True
        return False

    def discover_links(
        self,
        html_content: str,
        source_page_url: str,
        target_product: Optional[str] = None,
    ) -> List[ProductInfoLink]:
        """
        Scans HTML for relevant FDA Product Information and Prescribing Information links.
        Returns a deduplicated list of ProductInfoLink objects.
        """
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "lxml")
        discovered: List[ProductInfoLink] = []
        seen_urls = set()

        prod_norm = (target_product or "").strip().lower()

        for a in soup.find_all("a", href=True):
            raw_href = a["href"].strip()
            if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:")):
                continue

            full_url = urljoin(source_page_url, raw_href)
            if not self.is_official_fda_domain(full_url):
                # Reject third-party links
                continue

            link_text = " ".join(a.get_text().strip().split())
            title_attr = a.get("title", "").strip()
            combined_text = f"{link_text} {title_attr}".strip()

            # Path B check: Direct PDF
            if self.is_direct_pdf_url(full_url):
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    discovered.append(
                        ProductInfoLink(
                            url=full_url,
                            link_text=combined_text or "Prescribing Information PDF",
                            is_direct_pdf=True,
                            source_page_url=source_page_url,
                            discovery_type="path_b_direct",
                        )
                    )
                    logger.info("FDA_MEDWATCH_DIRECT_PDF_LINK_DISCOVERED: Found %s ('%s')", full_url, combined_text)
                continue

            # Path A check: Intermediate Product Information Page
            is_text_match = self.matches_label_link_text(combined_text)
            is_url_match = (
                "cder/daf" in full_url.lower() or
                "drugsatfda" in full_url.lower() or
                "product-information" in full_url.lower() or
                "prescribing-information" in full_url.lower()
            )

            # If product is specified, check if link is specifically for that product or general label
            product_relevant = True
            if prod_norm and len(prod_norm) >= 3:
                # If the link text mentions another drug name specifically, avoid cross-matching
                # but if it matches product or is generic "Product Information", it is relevant
                pass

            if is_text_match or is_url_match:
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    discovered.append(
                        ProductInfoLink(
                            url=full_url,
                            link_text=combined_text or "Product Information Page",
                            is_direct_pdf=False,
                            source_page_url=source_page_url,
                            discovery_type="path_a_intermediate",
                        )
                    )
                    logger.info("FDA_MEDWATCH_PRODUCT_LINK_DISCOVERED: Found %s ('%s')", full_url, combined_text)

        # Prioritize Direct PDFs first, then Intermediate pages
        discovered.sort(key=lambda item: 0 if item.is_direct_pdf else 1)
        return discovered
