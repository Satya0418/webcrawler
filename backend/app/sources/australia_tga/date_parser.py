"""
Date and version parser for Australia TGA documents and metadata.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple


class TGADateParser:
    """Extracts and normalizes document dates and versions from TGA pages and PDFs."""

    # Common date formats found in Australian regulatory texts
    DATE_FORMATS = [
        "%d %B %Y",       # 18 February 2026
        "%d %b %Y",       # 18 Feb 2026
        "%Y-%m-%d",       # 2026-02-18
        "%Y%m%dT%H%M%S",  # 20260721T120035 (TGA eBS Domino format)
        "%Y%m%d",         # 20260721
        "%d/%m/%Y",       # 18/02/2026
        "%d-%m-%Y",       # 18-02-2026
        "%B %d, %Y",      # February 18, 2026
        "%b %d, %Y",      # Feb 18, 2026
        "%B %Y",          # February 2026
        "%b %Y",          # Feb 2026
        "%Y/%m/%d",       # 2026/02/18
    ]

    # Regex patterns for explicit regulatory amendment/revision phrases
    AMENDMENT_REGEX = re.compile(
        r"(?:date\s+of\s+(?:most\s+recent\s+)?amendment|date\s+of\s+revision(?:\s+of\s+the\s+text)?|last\s+amended|revised(?:\s+on)?|amended(?:\s+on)?)\s*[:\-]?\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{4})",
        re.IGNORECASE
    )

    APPROVAL_REGEX = re.compile(
        r"(?:date\s+of\s+first\s+approval|first\s+approved|approval\s+date)\s*[:\-]?\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{4})",
        re.IGNORECASE
    )

    # Version patterns like "Version 4.0", "v2.1", "Rev 3", "Ver. 1.0", "v1.0"
    VERSION_REGEX = re.compile(
        r"\b(?:version|ver\.?|v|rev\.?|revision)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)*)\b",
        re.IGNORECASE
    )

    @classmethod
    def parse_date(cls, date_str: Optional[str]) -> Optional[datetime]:
        """Parses a date string into a datetime object."""
        if not date_str or not isinstance(date_str, str):
            return None

        # Clean string
        cleaned = date_str.strip()
        cleaned = re.sub(r"[^\w\s/.-]", "", cleaned).strip()
        if not cleaned:
            return None

        for fmt in cls.DATE_FORMATS:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue

        # Try regex search for embedded date pattern if full match failed
        m = re.search(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})", date_str)
        if m:
            for fmt in ("%d %B %Y", "%d %b %Y"):
                try:
                    return datetime.strptime(m.group(1), fmt)
                except ValueError:
                    pass

        m_iso = re.search(r"(\d{4}-\d{2}-\d{2})", date_str)
        if m_iso:
            try:
                return datetime.strptime(m_iso.group(1), "%Y-%m-%d")
            except ValueError:
                pass

        return None

    @classmethod
    def extract_amendment_date(cls, text: str) -> Optional[datetime]:
        """Looks for 'Date of most recent amendment' or 'Date of revision' inside document text."""
        if not text:
            return None
        m = cls.AMENDMENT_REGEX.search(text)
        if m:
            return cls.parse_date(m.group(1))
        return None

    @classmethod
    def extract_approval_date(cls, text: str) -> Optional[datetime]:
        """Looks for 'Date of first approval' inside document text."""
        if not text:
            return None
        m = cls.APPROVAL_REGEX.search(text)
        if m:
            return cls.parse_date(m.group(1))
        return None

    @classmethod
    def parse_version(cls, version_str: Optional[str]) -> Tuple[Optional[str], Optional[float]]:
        """
        Parses version string, returning canonical string representation and numeric float.
        Example: 'Version 2.1' -> ('Version 2.1', 2.1)
        """
        if not version_str or not isinstance(version_str, str):
            return None, None

        m = cls.VERSION_REGEX.search(version_str)
        if m:
            v_num_str = m.group(1)
            try:
                v_float = float(v_num_str) if "." in v_num_str else float(int(v_num_str))
                return f"Version {v_num_str}", v_float
            except ValueError:
                return f"Version {v_num_str}", None

        # Direct number like "2.0"
        m_num = re.match(r"^([0-9]+(?:\.[0-9]+)*)$", version_str.strip())
        if m_num:
            v_num_str = m_num.group(1)
            try:
                v_float = float(v_num_str) if "." in v_num_str else float(int(v_num_str))
                return f"Version {v_num_str}", v_float
            except ValueError:
                return f"Version {v_num_str}", None

        return version_str.strip(), None
