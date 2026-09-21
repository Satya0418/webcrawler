"""
FDA MedWatch Version & Date Selector.
Determines the latest valid official FDA document based on:
1. Official document date / revision date
2. FDA supplement number (e.g. s001 > s000)
3. FDA URL approval year (e.g. 2025 > 2023)
Enforces strict historical data isolation: NEVER mix content across versions.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, List, Optional, Tuple

from app.sources.fda_medwatch.models import MedWatchDocumentInfo

logger = logging.getLogger(__name__)

DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y/%m/%d",
    "%Y",
]

YEAR_REGEX = re.compile(r"/label/(\d{4})/", re.IGNORECASE)
SUPPL_REGEX = re.compile(r"s(\d{3,4})lbl\.pdf", re.IGNORECASE)


class FDAMedWatchVersionSelector:
    """Selects the latest official FDA prescribing information document chronologically."""

    @staticmethod
    def parse_date(date_str: Optional[str]) -> Optional[datetime]:
        """Parses a date string into a datetime object."""
        if not date_str:
            return None
        clean = date_str.strip()
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(clean, fmt)
            except ValueError:
                continue
        # Check if 4-digit year is present
        m = re.search(r"\b(19\d\d|20\d\d)\b", clean)
        if m:
            return datetime(int(m.group(1)), 1, 1)
        return None

    @classmethod
    def calculate_document_sort_key(cls, doc: MedWatchDocumentInfo) -> Tuple[datetime, int, str]:
        """
        Computes a deterministic chronological sort key for an FDA document:
        (datetime, supplement_int, url)
        """
        # 1. Date
        dt = cls.parse_date(doc.document_date)
        if not dt and doc.pdf_url:
            m_yr = YEAR_REGEX.search(doc.pdf_url)
            if m_yr:
                dt = datetime(int(m_yr.group(1)), 1, 1)
        if not dt:
            dt = datetime(1900, 1, 1)

        # 2. Supplement number (e.g. s001 -> 1)
        suppl_val = 0
        if doc.supplement_number:
            m_s = re.search(r"\d+", doc.supplement_number)
            if m_s:
                suppl_val = int(m_s.group(0))
        elif doc.pdf_url:
            m_s = SUPPL_REGEX.search(doc.pdf_url)
            if m_s:
                suppl_val = int(m_s.group(1))

        # 3. URL string tie-breaker
        return (dt, suppl_val, doc.pdf_url or "")

    @classmethod
    def select_latest_document(
        cls, docs: List[MedWatchDocumentInfo]
    ) -> Tuple[Optional[MedWatchDocumentInfo], List[MedWatchDocumentInfo]]:
        """
        Selects the latest valid official document from a list of discovered documents.
        Returns:
            Tuple of (latest_document, list_of_older_historical_documents)
        """
        if not docs:
            return None, []

        # Deduplicate documents by PDF URL
        seen_urls = set()
        unique_docs: List[MedWatchDocumentInfo] = []
        for d in docs:
            clean_url = (d.pdf_url or "").strip().lower()
            if clean_url and clean_url not in seen_urls:
                seen_urls.add(clean_url)
                unique_docs.append(d)

        if not unique_docs:
            return None, []

        # Sort descending by chronological sort key
        sorted_docs = sorted(unique_docs, key=cls.calculate_document_sort_key, reverse=True)

        latest_doc = sorted_docs[0]
        historical_docs = sorted_docs[1:]

        logger.info(
            "FDA_MEDWATCH_VERSION_SELECTED: Latest valid document is %s (date: %s, version: %s). %d historical versions preserved.",
            latest_doc.pdf_url,
            latest_doc.document_date,
            latest_doc.version,
            len(historical_docs),
        )

        return latest_doc, historical_docs
