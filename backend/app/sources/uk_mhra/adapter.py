"""
UK MHRA Drug Safety Update Adapter.

Coordinates search, live discovery, database persistence, and safety update
tracking for medicines regulated by the UK MHRA:
https://www.gov.uk/drug-safety-update
"""
from __future__ import annotations

import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.drug import Drug
from app.services.database_service import DatabaseService
from app.sources.uk_mhra.mhra_crawler import UKMHRACrawler, mhra_crawler

logger = logging.getLogger(__name__)

SOURCE_ID = "UK_MHRA"


class UKMHRAAdapter:
    """Adapter for UK MHRA Drug Safety Update discovery and persistence."""

    def __init__(self, crawler: Optional[UKMHRACrawler] = None) -> None:
        self.crawler = crawler or mhra_crawler

    async def search(
        self,
        query: str,
        db: Session,
        force_refresh: bool = False,
    ) -> List[Drug]:
        """
        Search for a medicine in UK MHRA Drug Safety Update by name or active ingredient.

        If local results exist and force_refresh is False, returns local cached records.
        Otherwise executes live search against GOV.UK Drug Safety Update index,
        and persists structured results into the database.
        """
        q = (query or "").strip()
        if not q or len(q) < 2:
            return []

        # Check local DB if not force refresh
        if not force_refresh:
            local_drugs = DatabaseService.search_drugs(db, q, source=SOURCE_ID)
            if local_drugs:
                logger.info("Found %d cached UK MHRA drug records for '%s'", len(local_drugs), q)
                return local_drugs

        # Run live MHRA search
        try:
            candidates = await self.crawler.search_medicine(q)
            logger.info("UK MHRA crawler returned %d candidate items for '%s'", len(candidates), q)

            for cand in candidates:
                cand["source"] = SOURCE_ID
                drug, is_new = DatabaseService.insert_or_update_drug(db, cand)

                # Save associated safety updates and clinical advice
                for change in cand.get("safety_changes", []):
                    change["source"] = SOURCE_ID
                    DatabaseService.save_safety_change(db, drug.id, change)

            db.commit()
        except Exception as exc:
            logger.error("Error during UK MHRA search/persistence for '%s': %s", q, exc, exc_info=True)
            db.rollback()

        return DatabaseService.search_drugs(db, q, source=SOURCE_ID)


# Global adapter instance
mhra_adapter = UKMHRAAdapter()
