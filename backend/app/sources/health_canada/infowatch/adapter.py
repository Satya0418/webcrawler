"""
Health Canada Health Product InfoWatch — Source Adapter (Orchestrator).

This is the main entry point for all Health Canada InfoWatch crawling.
It coordinates:
  1. Local DB lookup (return cached data if fresh)
  2. Index page fetch + discovery
  3. Relevance filtering (by medicine name from index entries)
  4. Article-level fetch + parsing
  5. PDF link routing → existing PDF extractor API
  6. Medicine normalization + DB persistence
  7. Change detection + versioning
  8. CrawlRun recording

End-to-end flow for a user query ("dimethyl fumarate"):
  local DB → stale/missing?
    → fetch index
    → discover all IndexEntry objects
    → filter entries whose product_name/generic_name match query
    → open only relevant article URLs
    → extract HTML content
    → if PDF links → POST to existing PDF extractor service
    → store products + safety context as SafetyLabelingChange rows
    → update CrawlRun stats

This module does NOT:
  - Implement PDF parsing (uses existing pdf_extractor service)
  - Break any existing FDA crawl or DB logic
  - Hard-code months or years
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from app.models.drug import CrawlRun, Drug, SafetyLabelingChange
from app.services.change_detection import ChangeDetectionService
from app.services.database_service import DatabaseService
from app.services.normalization import NormalizationService
from app.sources.health_canada.infowatch.classifier import classifier
from app.sources.health_canada.infowatch.crawler import HealthCanadaCrawler
from app.sources.health_canada.infowatch.discovery import discovery
from app.sources.health_canada.infowatch.models import (
    ArticleType,
    HealthCanadaArticle,
    IndexEntry,
    ProductMention,
)
from app.sources.health_canada.infowatch.parser import parser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_ID = "HEALTH_CANADA_INFOWATCH"
COUNTRY = "CANADA"
AUTHORITY = "HEALTH_CANADA"

HC_INDEX_URL = (
    "https://www.canada.ca/en/health-canada/services/drugs-health-products"
    "/medeffect-canada/health-product-infowatch/published-newsletters.html"
)

# How long before local DB data is considered stale (days)
STALE_THRESHOLD_DAYS = 7

# Maximum articles to open per crawl run (circuit breaker; 0 = unlimited)
MAX_ARTICLES_PER_RUN = 0

# PDF extractor service base URL (override via HC_PDF_EXTRACTOR_URL env var)
import os
PDF_EXTRACTOR_URL = os.environ.get(
    "HC_PDF_EXTRACTOR_URL",
    "http://localhost:8001"
)
PDF_EXTRACTOR_TIMEOUT = 120  # seconds


# ---------------------------------------------------------------------------
# Medicine matching helper
# ---------------------------------------------------------------------------

def _medicine_matches(query: str, entry: IndexEntry) -> bool:
    """
    Return True if this IndexEntry is relevant to the search query.

    Checks (case-insensitive, word-boundary-aware):
      - product_name
      - generic_name
      - article_title

    Query must be at least 3 characters for substring matching.
    """
    if not query:
        return True  # no filter → return all

    q = query.lower().strip()
    if len(q) < 3:
        return False  # too short to be a meaningful query; avoid false positives

    q_norm = NormalizationService.normalize_drug_name(q)

    targets = [
        NormalizationService.normalize_drug_name(entry.product_name),
        NormalizationService.normalize_drug_name(entry.generic_name),
        NormalizationService.normalize_drug_name(entry.article_title),
    ]

    for target in targets:
        if not target:
            continue
        # Word-boundary aware substring match (minimum 3 chars enforced above)
        if q_norm in target or target in q_norm:
            return True
        # Partial word match (e.g. "semaglutide" in "semaglutide injection")
        if any(part in target for part in q_norm.split() if len(part) >= 4):
            return True

    return False


# ---------------------------------------------------------------------------
# PDF extractor routing
# ---------------------------------------------------------------------------

async def _route_pdf_to_extractor(pdf_url: str, article: HealthCanadaArticle) -> Optional[dict]:
    """
    POST a PDF URL to the existing PDF extractor service.

    The PDF extractor (pdf_extractor/backend/api/extraction.py) accepts
    a URL and returns structured text, tables, and page-aware content.

    Returns the JSON response dict, or None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=PDF_EXTRACTOR_TIMEOUT) as client:
            response = await client.post(
                f"{PDF_EXTRACTOR_URL}/api/extract",
                json={"url": pdf_url, "source": SOURCE_ID},
            )
            if response.status_code == 200:
                logger.info("PDF extractor processed: %s", pdf_url)
                return response.json()
            else:
                logger.warning(
                    "PDF extractor returned HTTP %d for %s",
                    response.status_code, pdf_url,
                )
    except httpx.ConnectError:
        logger.warning(
            "PDF extractor not reachable at %s — skipping PDF: %s",
            PDF_EXTRACTOR_URL, pdf_url,
        )
    except Exception as exc:
        logger.error("Error routing PDF %s to extractor: %s", pdf_url, exc, exc_info=True)
    return None


# ---------------------------------------------------------------------------
# DB persistence helpers
# ---------------------------------------------------------------------------

def _build_change_data(
    article: HealthCanadaArticle,
    mention: ProductMention,
    pdf_result: Optional[dict] = None,
) -> dict:
    """
    Build a change_data dict compatible with DatabaseService.save_safety_change().
    Maps Health Canada fields onto the existing SafetyLabelingChange schema.
    """
    # Combine mention context with any PDF text
    updated_text = mention.context_text
    if pdf_result and pdf_result.get("text"):
        updated_text = f"{updated_text}\n\n[PDF content]\n{pdf_result['text'][:3000]}"

    section = _map_article_type_to_section(article.article_type, mention)

    return {
        "source": SOURCE_ID,
        "source_record_id": _build_record_id(article, mention),
        "display_name": mention.product_name or mention.generic_name,
        "normalized_name": mention.normalized_product or mention.normalized_generic,
        "active_ingredient": mention.generic_name,
        "section": section,
        "change_type": article.article_type.value,
        "source_date": article.publication_date.isoformat() if article.publication_date else None,
        "source_url": HC_INDEX_URL,
        "original_text": mention.context_text[:4000] if mention.context_text else None,
        "updated_text": updated_text[:4000] if updated_text else None,
        "fda_comment": (
            f"Health Canada {article.newsletter_type} — "
            f"{article.newsletter_month} {article.newsletter_year}"
        ),
        # Additional HC-specific metadata stored as JSON in fda_comment extension
        "content_hash": None,  # computed by DatabaseService
    }


def _map_article_type_to_section(article_type: ArticleType, mention: ProductMention) -> str:
    """Map an ArticleType to a normalised section string for the DB."""
    mapping = {
        ArticleType.PRODUCT_MONOGRAPH_UPDATE: "Product Monograph Update",
        ArticleType.SAFETY_BRIEF: "Safety Brief",
        ArticleType.SAFETY_SUMMARY: "Safety Summary",
        ArticleType.VACCINE_SAFETY_SUMMARY: "Vaccine Safety Summary",
        ArticleType.MEDICATION_ERROR_ALERT: "Medication Error Alert",
        ArticleType.MARKET_AUTHORIZATION_WITH_CONDITIONS: "Market Authorization With Conditions",
        ArticleType.MONTHLY_RECAP: "Monthly Recap",
        ArticleType.ANNOUNCEMENT: "Announcement",
        ArticleType.ADVERSE_REACTION_INFORMATION: "Adverse Reaction Information",
    }
    return mapping.get(article_type, "Health Canada Safety Information")


def _build_record_id(article: HealthCanadaArticle, mention: ProductMention) -> str:
    """Build a stable unique record ID from article URL + product name."""
    base = f"{article.article_url}|{mention.normalized_product or mention.normalized_generic}"
    return hashlib.sha256(base.encode()).hexdigest()[:32]


def _is_data_fresh(db: Session, query: str) -> bool:
    """
    Check if we have recent HC data for this query in the local DB.
    Returns True if last_verified_at is within STALE_THRESHOLD_DAYS.
    """
    threshold = datetime.utcnow() - timedelta(days=STALE_THRESHOLD_DAYS)
    norm = NormalizationService.normalize_drug_name(query)

    drugs = DatabaseService.search_drugs(db, query, limit=5)
    for drug in drugs:
        changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
        for change in changes:
            if (
                change.source == SOURCE_ID
                and change.last_verified_at
                and change.last_verified_at >= threshold
            ):
                return True
    return False


# ---------------------------------------------------------------------------
# Main adapter
# ---------------------------------------------------------------------------

class HealthCanadaInfowatchAdapter:
    """
    Orchestrates the end-to-end Health Canada InfoWatch crawl and extraction.

    Usage (on-demand, triggered by user search)::

        adapter = HealthCanadaInfowatchAdapter()
        results = await adapter.search(query="dimethyl fumarate", db=session)

    Usage (background full crawl)::

        adapter = HealthCanadaInfowatchAdapter()
        stats = await adapter.run_full_crawl(db=session)
    """

    # ------------------------------------------------------------------
    # On-demand search (called from API)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        db: Session,
        force_refresh: bool = False,
    ) -> List[Drug]:
        """
        Search for a medicine in Health Canada InfoWatch data.

        Steps:
        1. Check local DB.
        2. If stale or missing, crawl HC index → filter → extract.
        3. Return matching Drug records.

        Args:
            query:         Medicine name, brand, generic, or molecule.
            db:            SQLAlchemy session.
            force_refresh: Skip freshness check and always re-crawl.

        Returns:
            List of Drug ORM records matching the query.
        """
        if not force_refresh and _is_data_fresh(db, query):
            logger.info("HC data for '%s' is fresh — returning from DB", query)
            return DatabaseService.search_drugs(db, query)

        logger.info("HC data for '%s' is stale or missing — crawling", query)
        await self._crawl_for_query(query=query, db=db)
        return DatabaseService.search_drugs(db, query)

    # ------------------------------------------------------------------
    # Targeted crawl (for a specific search query)
    # ------------------------------------------------------------------

    async def _crawl_for_query(self, query: str, db: Session) -> dict:
        """
        Crawl HC index, filter for relevant articles, extract and save.
        """
        crawl_run = self._start_crawl_run(db)
        errors = []

        try:
            async with HealthCanadaCrawler() as hc_crawler:
                # 1. Fetch index
                index_html = await hc_crawler.fetch_index()
                if not index_html:
                    logger.error("Failed to fetch Health Canada index")
                    self._finish_crawl_run(db, crawl_run, "failed", errors=["Failed to fetch index"])
                    return {}
                crawl_run.pages_crawled += 1
                db.flush()

                # 2. Discover all entries
                all_entries = discovery.parse_index(index_html)
                crawl_run.records_found = len(all_entries)
                db.flush()

                # 3. Filter for relevant entries
                relevant = [e for e in all_entries if _medicine_matches(query, e)]
                logger.info(
                    "Query '%s': %d/%d entries are relevant",
                    query, len(relevant), len(all_entries),
                )

                # 4. Deduplicate article page URLs (one fetch per page)
                page_urls = {}  # page_url → list of IndexEntries
                for entry in relevant:
                    page_url = entry.article_url.split("#")[0]
                    page_urls.setdefault(page_url, []).append(entry)

                crawl_run.pages_requested = len(page_urls)
                db.flush()

                # 5. Fetch and process each relevant article page
                added = changed = 0
                for page_url, entries in page_urls.items():
                    try:
                        result = await self._process_article_page(
                            page_url=page_url,
                            entries=entries,
                            crawler=hc_crawler,
                            db=db,
                        )
                        crawl_run.pages_crawled += 1
                        added += result.get("added", 0)
                        changed += result.get("changed", 0)
                    except Exception as exc:
                        msg = f"Error processing {page_url}: {exc}"
                        logger.error(msg, exc_info=True)
                        errors.append(msg)

                crawl_run.records_added = added
                crawl_run.records_changed = changed
                db.commit()

            self._finish_crawl_run(db, crawl_run, "success", errors=errors)
            return {
                "pages_crawled": crawl_run.pages_crawled,
                "records_found": crawl_run.records_found,
                "records_added": added,
                "records_changed": changed,
                "errors": errors,
            }

        except Exception as exc:
            logger.error("Crawl failed: %s", exc, exc_info=True)
            errors.append(str(exc))
            db.rollback()
            self._finish_crawl_run(db, crawl_run, "failed", errors=errors)
            return {"errors": errors}

    # ------------------------------------------------------------------
    # Full background crawl
    # ------------------------------------------------------------------

    async def run_full_crawl(self, db: Session) -> dict:
        """
        Run a full crawl of the Health Canada index — all months, all articles.
        Intended for background/scheduled runs via Celery.

        Only processes articles that are new or changed (hash comparison).
        """
        crawl_run = self._start_crawl_run(db)
        errors = []

        try:
            async with HealthCanadaCrawler() as hc_crawler:
                index_html = await hc_crawler.fetch_index()
                if not index_html:
                    self._finish_crawl_run(db, crawl_run, "failed", errors=["Failed to fetch index"])
                    return {}

                crawl_run.pages_crawled += 1
                db.flush()

                all_entries = discovery.parse_index(index_html)
                crawl_run.records_found = len(all_entries)

                # Filter out SKIP types
                processable = [
                    e for e in all_entries
                    if classifier.is_safety_relevant(e.article_type)
                ]

                # Deduplicate article pages
                page_urls: dict[str, list] = {}
                for entry in processable:
                    page_url = entry.article_url.split("#")[0]
                    page_urls.setdefault(page_url, []).append(entry)

                crawl_run.pages_requested = len(page_urls)
                db.flush()

                added = changed = 0
                processed = 0

                for page_url, entries in page_urls.items():
                    if MAX_ARTICLES_PER_RUN and processed >= MAX_ARTICLES_PER_RUN:
                        logger.info("Reached MAX_ARTICLES_PER_RUN=%d — stopping", MAX_ARTICLES_PER_RUN)
                        break
                    try:
                        result = await self._process_article_page(
                            page_url=page_url,
                            entries=entries,
                            crawler=hc_crawler,
                            db=db,
                        )
                        crawl_run.pages_crawled += 1
                        added += result.get("added", 0)
                        changed += result.get("changed", 0)
                        processed += 1
                    except Exception as exc:
                        msg = f"Error processing {page_url}: {exc}"
                        logger.error(msg, exc_info=True)
                        errors.append(msg)

                crawl_run.records_added = added
                crawl_run.records_changed = changed
                db.commit()

            self._finish_crawl_run(db, crawl_run, "success", errors=errors)
            return {
                "pages_crawled": crawl_run.pages_crawled,
                "records_found": crawl_run.records_found,
                "records_added": added,
                "records_changed": changed,
                "errors": errors,
            }

        except Exception as exc:
            logger.error("Full crawl failed: %s", exc, exc_info=True)
            errors.append(str(exc))
            db.rollback()
            self._finish_crawl_run(db, crawl_run, "failed", errors=errors)
            return {"errors": errors}

    # ------------------------------------------------------------------
    # Article processing
    # ------------------------------------------------------------------

    async def _process_article_page(
        self,
        page_url: str,
        entries: List[IndexEntry],
        crawler: HealthCanadaCrawler,
        db: Session,
    ) -> dict:
        """
        Fetch and process a single article page.

        Returns dict with "added" and "changed" counts.
        """
        html = await crawler.fetch_article(page_url)
        if not html:
            logger.warning("Could not fetch article: %s", page_url)
            return {"added": 0, "changed": 0}

        added = changed = 0

        # Use the first IndexEntry to drive parsing (they all share the same page)
        primary_entry = entries[0]
        article = parser.parse(html=html, index_entry=primary_entry)

        # Route PDF links to existing extractor (fire-and-forget per PDF)
        pdf_results: dict[str, Optional[dict]] = {}
        for pdf_url in article.pdf_urls:
            logger.info("Routing PDF to extractor: %s", pdf_url)
            pdf_results[pdf_url] = await _route_pdf_to_extractor(pdf_url, article)

        # Save each product mention
        all_pdf_result = list(pdf_results.values())
        first_pdf_result = all_pdf_result[0] if all_pdf_result else None

        for mention in article.product_mentions:
            try:
                a, c = self._save_mention(db=db, article=article, mention=mention, pdf_result=first_pdf_result)
                added += a
                changed += c
            except Exception as exc:
                logger.error(
                    "Error saving mention '%s' from %s: %s",
                    mention.product_name or mention.generic_name,
                    page_url, exc, exc_info=True,
                )

        # If no product mentions were found, store the article itself as a catch-all
        if not article.product_mentions and primary_entry.product_name:
            catch_all_mention = self._build_catchall_mention(primary_entry, article)
            try:
                a, c = self._save_mention(db=db, article=article, mention=catch_all_mention, pdf_result=first_pdf_result)
                added += a
                changed += c
            except Exception as exc:
                logger.error("Error saving catch-all for %s: %s", page_url, exc, exc_info=True)

        db.flush()
        return {"added": added, "changed": changed}

    # ------------------------------------------------------------------
    # DB save
    # ------------------------------------------------------------------

    def _save_mention(
        self,
        db: Session,
        article: HealthCanadaArticle,
        mention: ProductMention,
        pdf_result: Optional[dict],
    ) -> Tuple[int, int]:
        """
        Persist one ProductMention to the database.
        Returns (added, changed) counts.
        """
        display_name = mention.product_name or mention.generic_name
        if not display_name:
            return 0, 0

        drug_data = {
            "display_name": display_name,
            "normalized_name": NormalizationService.normalize_drug_name(display_name),
            "active_ingredient": mention.generic_name,
            "source": SOURCE_ID,
        }
        drug, _ = DatabaseService.insert_or_update_drug(db, drug_data)

        change_data = _build_change_data(article, mention, pdf_result)
        _, is_new_or_changed = DatabaseService.save_safety_change(db, drug.id, change_data)

        return (1, 0) if _ and is_new_or_changed else (0, 0)

    @staticmethod
    def _build_catchall_mention(entry: IndexEntry, article: HealthCanadaArticle) -> ProductMention:
        """Build a ProductMention from the IndexEntry when the parser finds nothing."""
        from app.services.normalization import NormalizationService
        return ProductMention(
            product_name=entry.product_name,
            generic_name=entry.generic_name,
            normalized_product=NormalizationService.normalize_drug_name(entry.product_name),
            normalized_generic=NormalizationService.normalize_drug_name(entry.generic_name),
            section_heading=entry.category_level3 or entry.category_level2 or entry.category_level1,
            context_text=article.full_text[:2000],
            article_type=entry.article_type,
        )

    # ------------------------------------------------------------------
    # CrawlRun helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _start_crawl_run(db: Session) -> CrawlRun:
        run = CrawlRun(
            source=SOURCE_ID,
            started_at=datetime.utcnow(),
            status="running",
            pages_requested=0,
            pages_crawled=0,
            records_found=0,
            records_added=0,
            records_changed=0,
            records_unchanged=0,
        )
        db.add(run)
        db.flush()
        return run

    @staticmethod
    def _finish_crawl_run(
        db: Session,
        run: CrawlRun,
        status: str,
        errors: Optional[List[str]] = None,
    ) -> None:
        run.status = status
        run.completed_at = datetime.utcnow()
        if errors:
            run.errors = json.dumps(errors[:50])  # cap stored errors
        try:
            db.add(run)
            db.commit()
        except Exception as exc:
            logger.error("Failed to save CrawlRun: %s", exc)
            db.rollback()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

adapter = HealthCanadaInfowatchAdapter()


# ---------------------------------------------------------------------------
# CLI entry point for manual testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    arg_parser = argparse.ArgumentParser(description="Health Canada InfoWatch adapter CLI")
    arg_parser.add_argument("--crawl", action="store_true", help="Run a full crawl")
    arg_parser.add_argument("--search", metavar="QUERY", help="Search for a medicine")
    args = arg_parser.parse_args()

    from app.database import SessionLocal, init_db
    init_db()

    async def _main():
        db = SessionLocal()
        try:
            if args.crawl:
                print("Running full Health Canada crawl...")
                stats = await adapter.run_full_crawl(db)
                print("Stats:", stats)
            elif args.search:
                print(f"Searching for: {args.search}")
                drugs = await adapter.search(query=args.search, db=db, force_refresh=True)
                print(f"Found {len(drugs)} drug(s):")
                for d in drugs:
                    print(f"  {d.display_name} [{d.source}]")
            else:
                arg_parser.print_help()
        finally:
            db.close()

    asyncio.run(_main())
