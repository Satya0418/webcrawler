"""
Australia Therapeutic Goods Administration (TGA) Adapter.

Coordinates search, live crawling, database persistence, and safety labeling change
tracking for medicines regulated by the Australian TGA.
"""
from __future__ import annotations

import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.drug import Drug
from app.services.database_service import DatabaseService
from app.services.normalization import NormalizationService
from app.sources.australia_tga.tga_crawler import AustraliaTGACrawler, tga_crawler

logger = logging.getLogger(__name__)

SOURCE_ID = "AUSTRALIA_TGA"


class AustraliaTGAAdapter:
    """Adapter for Australia TGA medicine safety discovery and persistence."""

    def __init__(self, crawler: Optional[AustraliaTGACrawler] = None) -> None:
        self.crawler = crawler or tga_crawler

    async def search(
        self,
        query: str,
        db: Session,
        force_refresh: bool = False,
    ) -> List[Drug]:
        """
        Search for an Australian medicine by name, ingredient, or AUST R / ARTG ID.

        If local results exist and force_refresh is False, returns local cached records.
        Otherwise executes live crawl of https://www.tga.gov.au/search?keywords=...
        and persists structured results into the database.
        """
        q = (query or "").strip()
        if not q or len(q) < 2:
            return []

        # Check local DB if not force refresh
        if not force_refresh:
            local_drugs = DatabaseService.search_drugs(db, q, source=SOURCE_ID)
            if local_drugs:
                logger.info("Found %d cached Australian TGA drug records for '%s'", len(local_drugs), q)
                return local_drugs

        # Run live TGA search
        try:
            candidates = await self.crawler.search_medicine(q)
            logger.info("TGA crawler returned %d candidate items for '%s'", len(candidates), q)

            for cand in candidates:
                drug, is_new = DatabaseService.insert_or_update_drug(db, cand)

                # Save associated safety alerts and product information changes
                for change in cand.get("safety_changes", []):
                    DatabaseService.save_safety_change(db, drug.id, change)

            db.commit()
        except Exception as exc:
            logger.error("Error during Australia TGA search/persistence for '%s': %s", q, exc, exc_info=True)
            db.rollback()

        return DatabaseService.search_drugs(db, q, source=SOURCE_ID)


# Global adapter instance
tga_adapter = AustraliaTGAAdapter()
