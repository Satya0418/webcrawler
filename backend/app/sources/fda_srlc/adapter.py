"""
FDA Drug Safety-related Labeling Changes (SrLC) Adapter.

Coordinates search, live crawling, database persistence, and safety labeling change
tracking for medicines regulated by the US FDA Center for Drug Evaluation and Research (CDER).
"""
from __future__ import annotations

import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.drug import Drug
from app.services.database_service import DatabaseService
from app.sources.fda_srlc.crawler import FDASrLCCrawler, fda_srlc_crawler

logger = logging.getLogger(__name__)

SOURCE_ID = "FDA_SRLC"


class FDASrLCAdapter:
    """Adapter for FDA SrLC discovery, structured extraction, and persistence."""

    def __init__(self, crawler: Optional[FDASrLCCrawler] = None) -> None:
        self.crawler = crawler or fda_srlc_crawler

    async def search(
        self,
        query: str,
        db: Session,
        force_refresh: bool = False,
    ) -> List[Drug]:
        """
        Search for an FDA-regulated drug by name or active ingredient.

        If local results exist with safety changes and force_refresh is False,
        returns cached records immediately.
        Otherwise executes live crawl, applies Date-First and Section Prioritization,
        persisting structured results into the database.
        """
        q = (query or "").strip()
        if not q or len(q) < 2:
            return []

        # Check local DB if not force refresh
        local_drugs = DatabaseService.search_drugs(db, q, source=SOURCE_ID)
        has_data = any(
            bool(DatabaseService.get_safety_changes_by_drug_id(db, d.id))
            for d in local_drugs
        )
        if has_data and not force_refresh:
            logger.info("Found %d cached FDA SrLC records with safety data for '%s'", len(local_drugs), q)
            return local_drugs

        # Run live FDA SrLC search & extraction
        try:
            candidates = await self.crawler.search_medicine(q)
            logger.info("FDA SrLC crawler returned %d candidate items for '%s'", len(candidates), q)

            for cand in candidates:
                drug, is_new = DatabaseService.insert_or_update_drug(db, cand)

                # Save associated safety changes (Adverse Reactions, Warnings, Pregnancy)
                for change in cand.get("safety_changes", []):
                    DatabaseService.save_safety_change(db, drug.id, change)

            db.commit()
        except Exception as exc:
            logger.error("Error during FDA SrLC search/persistence for '%s': %s", q, exc, exc_info=True)
            db.rollback()

        return DatabaseService.search_drugs(db, q, source=SOURCE_ID)


# Global adapter instance
fda_srlc_adapter = FDASrLCAdapter()
