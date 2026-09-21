"""
FDA MedWatch Document Discovery.
Inspects intermediate FDA Product Information pages, Drugs@FDA listings,
and label repositories to locate official FDA Prescribing Information PDFs.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from app.sources.fda_medwatch.config import DIRECT_LABEL_PDF_PATTERNS
from app.sources.fda_medwatch.models import MedWatchDocumentInfo

logger = logging.getLogger(__name__)

PDF_YEAR_REGEX = re.compile(r"/label/(\d{4})/", re.IGNORECASE)
SUPPL_REGEX = re.compile(r"s(\d{3,4})lbl\.pdf", re.IGNORECASE)


class FDAMedWatchDocumentDiscovery:
    """Discovers and parses FDA Product Information PDF links and metadata."""

    def __init__(self) -> None:
        self.direct_regexes = [re.compile(p, re.IGNORECASE) for p in DIRECT_LABEL_PDF_PATTERNS]

    def is_label_pdf(self, href: str, text: str) -> bool:
        """Determines if a link points to an FDA label PDF."""
        clean_href = href.split("?")[0].split("#")[0].lower()
        if not clean_href.endswith(".pdf"):
            return False
        if clean_href.endswith("lbl.pdf"):
            return True
        for reg in self.direct_regexes:
            if reg.search(href):
                return True
        clean_text = text.lower()
        if "label" in clean_text or "prescribing" in clean_text or "package insert" in clean_text:
            return True
        return False

    def extract_document_info_from_url(self, pdf_url: str, text: str = "", source_url: str = "") -> MedWatchDocumentInfo:
        """Extracts date, supplement number, and version metadata from the PDF URL and text."""
        doc_date = None
        suppl_num = None
        version = None

        m_year = PDF_YEAR_REGEX.search(pdf_url)
        if m_year:
            doc_date = f"{m_year.group(1)}-01-01"
            version = m_year.group(1)

        m_suppl = SUPPL_REGEX.search(pdf_url)
        if m_suppl:
            suppl_num = f"s{m_suppl.group(1)}"
            version = f"{version}-{suppl_num}" if version else suppl_num

        return MedWatchDocumentInfo(
            found=True,
            url=source_url or pdf_url,
            pdf_url=pdf_url,
            document_title=text.strip() or "FDA Approved Prescribing Information",
            document_date=doc_date,
            version=version,
            supplement_number=suppl_num,
            source_article_url=source_url,
        )

    def discover_documents(self, html_content: str, base_url: str) -> List[MedWatchDocumentInfo]:
        """
        Discovers all official label PDFs from a Product Information page.
        """
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "lxml")
        docs: List[MedWatchDocumentInfo] = []
        seen_pdfs = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue

            full_url = urljoin(base_url, href)
            link_text = " ".join(a.get_text().strip().split())

            if self.is_label_pdf(full_url, link_text):
                if full_url not in seen_pdfs:
                    seen_pdfs.add(full_url)
                    doc_info = self.extract_document_info_from_url(full_url, text=link_text, source_url=base_url)

                    # Look for date in surrounding table row or parent text if not found from URL
                    parent_row = a.find_parent("tr")
                    if parent_row:
                        row_text = parent_row.get_text()
                        m_date = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", row_text)
                        if m_date:
                            doc_info.document_date = m_date.group(1)

                    docs.append(doc_info)
                    logger.info("FDA_MEDWATCH_PDF_FOUND: %s (version: %s, date: %s)", full_url, doc_info.version, doc_info.document_date)

        return docs
