"""
FDA MedWatch Adapter.

Coordinates search, live discovery, database persistence, and safety
adverse event / recall tracking for medicines monitored under FDA MedWatch:
https://www.fda.gov/safety/medwatch-fda-safety-information-and-adverse-event-reporting-program
"""
from __future__ import annotations

import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.drug import Drug
from app.services.database_service import DatabaseService
from app.sources.fda_medwatch.medwatch_crawler import FDAMedWatchCrawler, medwatch_crawler

logger = logging.getLogger(__name__)

SOURCE_ID = "FDA_MEDWATCH"


class FDAMedWatchAdapter:
    """Adapter for FDA MedWatch safety discovery, FAERS events, and recalls."""

    def __init__(self, crawler: Optional[FDAMedWatchCrawler] = None) -> None:
        self.crawler = crawler or medwatch_crawler

    async def search(
        self,
        query: str,
        db: Session,
        force_refresh: bool = False,
    ) -> List[Drug]:
        """
        Search for a medicine in FDA MedWatch by name, active ingredient, or report ID.

        If local results exist and force_refresh is False, returns local cached records.
        Otherwise executes live search against MedWatch RSS feed, FAERS, and openFDA,
        and persists structured results into the database.
        """
        q = (query or "").strip()
        if not q or len(q) < 2:
            return []

        # Check local DB if not force refresh
        if not force_refresh:
            local_drugs = DatabaseService.search_drugs(db, q, source=SOURCE_ID)
            if local_drugs:
                logger.info("Found %d cached FDA MedWatch drug records for '%s'", len(local_drugs), q)
                return local_drugs

        # Run live MedWatch search
        try:
            candidates = await self.crawler.search_medicine(q)
            logger.info("FDA MedWatch crawler returned %d candidate items for '%s'", len(candidates), q)

            for cand in candidates:
                cand["source"] = SOURCE_ID
                drug, is_new = DatabaseService.insert_or_update_drug(db, cand)

                # Save associated safety alerts, recalls, and FAERS events
                for change in cand.get("safety_changes", []):
                    change["source"] = SOURCE_ID
                    DatabaseService.save_safety_change(db, drug.id, change)

            db.commit()
        except Exception as exc:
            logger.error("Error during FDA MedWatch search/persistence for '%s': %s", q, exc, exc_info=True)
            db.rollback()

        return DatabaseService.search_drugs(db, q, source=SOURCE_ID)


# Global adapter instance
medwatch_adapter = FDAMedWatchAdapter()
