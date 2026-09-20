"""
Version and date comparator for selecting the latest valid Product Information PDF.
"""
from __future__ import annotations

from datetime import datetime
import logging
from typing import List, Optional, Tuple

from app.sources.australia_tga.models import TGAPIDocument

logger = logging.getLogger(__name__)


class TGAVersionSelector:
    """
    Selects the authoritative, latest valid Product Information PDF document
    from candidate documents based on regulatory revision date, document date, and version.
    """

    @classmethod
    def select_latest(cls, documents: List[TGAPIDocument]) -> Optional[TGAPIDocument]:
        """
        Selects the latest valid Product Information document among candidates.

        Strict priority order per regulatory standards:
        1. Explicit revision / amendment date (most recent)
        2. Official Product Information date (most recent)
        3. Official version number (highest numeric value)
        4. Effective date
        5. Retrieved date / timestamp

        Never relies on search order or alphabetical filename order.
        """
        if not documents:
            return None

        if len(documents) == 1:
            return documents[0]

        logger.info("Evaluating %d candidate Product Information documents for latest version", len(documents))

        # Sort documents using priority score tuple
        sorted_docs = sorted(documents, key=cls._compute_priority_key, reverse=True)
        winner = sorted_docs[0]

        logger.info(
            "Selected latest PI document: %s (Rev Date: %s, Doc Date: %s, Version: %s)",
            winner.pdf_url,
            winner.revision_date,
            winner.document_date,
            winner.version_str,
        )
        return winner

    @classmethod
    def _compute_priority_key(cls, doc: TGAPIDocument) -> Tuple[datetime, datetime, float, datetime]:
        """
        Constructs a comparable tuple reflecting the prioritized criteria:
        (revision_date, document_date, version_number, retrieved_date).
        Missing values are mapped to minimum sensible baselines (e.g. datetime.min).
        """
        min_dt = datetime.min

        # 1. Revision / Amendment date
        rev_dt = doc.revision_date or min_dt

        # 2. Document date / publication date
        doc_dt = doc.document_date or doc.effective_date or min_dt

        # 3. Numeric version (e.g. 4.0 > 3.2 > 1.0)
        v_num = doc.version_number if doc.version_number is not None else 0.0

        # 4. Retrieved / fallback date
        ret_dt = doc.retrieved_date or min_dt

        return (rev_dt, doc_dt, v_num, ret_dt)
