"""
Date parser and chronological logic for FDA SrLC.
Enforces DATE-FIRST logic and prevents historical date mixing.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def parse_fda_date(date_str: Optional[Any]) -> Optional[datetime]:
    """
    Parse a string or datetime to a standard datetime object.
    Handles ISO, FDA MM/DD/YYYY, M/D/YYYY, textual dates ('June 25, 2026', '25-Jun-2026'),
    and timestamps, stripping supplement notes like '(SUPPL-50)'.
    """
    if not date_str:
        return None
    if isinstance(date_str, datetime):
        return date_str

    raw = str(date_str).strip()
    if not raw:
        return None

    # Search for date pattern anywhere in string
    date_regex = re.compile(
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}|"
        r"\d{1,2}[-\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-\s]\d{2,4})",
        re.IGNORECASE,
    )
    m = date_regex.search(raw)
    target = m.group(1).strip() if m else raw

    # Strip supplement notes if present: e.g. "06/25/2026(SUPPL-25)" or "06/25/2026 (SUPPL-25)"
    target_clean = re.sub(r"\(SUPPL[^\)]*\)", "", target, flags=re.IGNORECASE).strip()
    date_part = target_clean.split(" ")[0].split("T")[0].strip()

    # Standard numeric formats
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%d-%B-%Y", "%b-%d-%Y", "%B-%d-%Y"):
        try:
            dt = datetime.strptime(date_part, fmt)
            return dt
        except ValueError:
            pass

    # Textual formats on target_clean
    for fmt in (
        "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
        "%d %B %Y", "%d %b %Y", "%d-%b-%Y", "%d-%B-%Y"
    ):
        try:
            dt = datetime.strptime(target_clean, fmt)
            return dt
        except ValueError:
            pass

    # Fallback to dateutil if available
    try:
        import dateutil.parser
        return dateutil.parser.parse(target_clean)
    except Exception:
        pass

    return None


def format_fda_date_to_report(date_val: Optional[Any]) -> Optional[str]:
    """
    Convert FDA dates to standard medical report format: '05-Dec-2025' or '25-Jun-2026'.
    """
    dt = parse_fda_date(date_val)
    if dt:
        return dt.strftime("%d-%b-%Y")
    return str(date_val) if date_val else None


def extract_supplement_id(raw_str: str) -> Optional[str]:
    """Extract supplement identifier such as 'SUPPL-50' from header string."""
    if not raw_str:
        return None
    match = re.search(r"\((SUPPL-[^\)]+)\)", raw_str, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"\b(SUPPL-\d+)\b", raw_str, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def select_latest_date_and_records(
    records: List[Any],
    date_extractor_func=None,
) -> Tuple[Optional[datetime], List[Any]]:
    """
    DATE-FIRST LOGIC:
    1. Parse date for every record.
    2. Convert into normalized datetime objects.
    3. Sort descending.
    4. Identify the latest date.
    5. Return that latest date and ALL records belonging strictly to that latest date.
    Never returns records from older historical dates.
    """
    if not records:
        return None, []

    records_with_dates: List[Tuple[datetime, Any]] = []

    for r in records:
        dt = None
        if date_extractor_func:
            dt = date_extractor_func(r)
        elif hasattr(r, "date_obj") and r.date_obj:
            dt = r.date_obj
        elif isinstance(r, dict):
            dt = parse_fda_date(r.get("source_date") or r.get("date") or r.get("supplement_date"))
        elif hasattr(r, "supplement_date"):
            dt = parse_fda_date(r.supplement_date)

        if dt:
            records_with_dates.append((dt, r))
            logger.debug("FDA_SRLC_DATE_PARSED: Parsed date %s for record", dt.strftime("%Y-%m-%d"))

    if not records_with_dates:
        logger.warning("FDA_SRLC_DATE_PARSED: No valid dates found among %d records", len(records))
        return None, []

    # Sort descending by datetime
    records_with_dates.sort(key=lambda x: x[0], reverse=True)

    # Latest date is the first entry's date (normalized to day boundary)
    latest_dt = records_with_dates[0][0]
    latest_date_norm = latest_dt.date()

    # Collect all records that match the latest date
    matching_records = [
        r for dt, r in records_with_dates if dt.date() == latest_date_norm
    ]

    logger.info(
        "FDA_SRLC_LATEST_DATE_SELECTED: Selected latest date %s with %d matching records",
        latest_date_norm.isoformat(),
        len(matching_records),
    )

    return latest_dt, matching_records
