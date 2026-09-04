"""
Celery background worker for asynchronous and periodic FDA SrLC crawling.
"""
import asyncio
import logging
from datetime import datetime
from celery import Celery
from celery.schedules import crontab

from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Celery app
celery_app = Celery(
    "medicine_safety_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

# Scheduled tasks configuration
celery_app.conf.beat_schedule = {
    "periodic-fda-safety-check": {
        "task": "app.workers.fda_worker.scheduled_fda_sync",
        # Run daily at 02:00 AM UTC
        "schedule": crontab(hour=2, minute=0),
    },
}


def _run_crawl_sync(drug_name: str) -> dict:
    """Synchronous wrapper for FDA crawl."""
    from app.database import SessionLocal
    from app.crawler.fda_crawler import crawler
    from app.scrapers.fda_srlc_scraper import scraper
    from app.services.database_service import DatabaseService
    from app.models.drug import CrawlRun

    db = SessionLocal()
    crawl_run = CrawlRun(
        source="FDA_SRLC",
        started_at=datetime.utcnow(),
        status="running",
        pages_requested=1,
    )
    db.add(crawl_run)
    db.commit()
    db.refresh(crawl_run)

    async def _async_crawl():
        pages_crawled = 0
        records_found = 0
        records_added = 0
        records_changed = 0

        html = await crawler.search_drug(drug_name)
        pages_crawled += 1

        if html:
            results = scraper.parse_search_results(html)
            records_found = len(results)

            for item in results[:5]:
                drug, is_new = DatabaseService.insert_or_update_drug(db, item)
                if is_new:
                    records_added += 1

                detail_url = item.get("detail_url")
                if detail_url:
                    pages_crawled += 1
                    detail_html = await crawler.get_detail_page(detail_url)
                    if detail_html:
                        detail = scraper.parse_detail_page(detail_html, source_url=detail_url)
                        if detail:
                            for chg in detail.get("safety_changes", []):
                                _, changed = DatabaseService.save_safety_change(db, drug.id, chg)
                                if changed:
                                    records_changed += 1

        db.commit()
        return {
            "pages_crawled": pages_crawled,
            "records_found": records_found,
            "records_added": records_added,
            "records_changed": records_changed,
        }

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        stats = loop.run_until_complete(_async_crawl())
        loop.close()

        crawl_run.status = "success"
        crawl_run.pages_crawled = stats["pages_crawled"]
        crawl_run.records_found = stats["records_found"]
        crawl_run.records_added = stats["records_added"]
        crawl_run.records_changed = stats["records_changed"]
        crawl_run.completed_at = datetime.utcnow()
        db.commit()
        return stats
    except Exception as e:
        logger.error(f"Worker crawl failed for '{drug_name}': {e}", exc_info=True)
        db.rollback()
        crawl_run.status = "failed"
        crawl_run.errors = str(e)
        crawl_run.completed_at = datetime.utcnow()
        db.commit()
        return {"error": str(e)}
    finally:
        db.close()


@celery_app.task(name="app.workers.fda_worker.crawl_drug_task")
def crawl_drug_task(drug_name: str):
    """Celery task to crawl a specific drug."""
    logger.info(f"[Celery] Crawling FDA for drug: {drug_name}")
    return _run_crawl_sync(drug_name)


@celery_app.task(name="app.workers.fda_worker.scheduled_fda_sync")
def scheduled_fda_sync():
    """Periodic task crawling common drugs and checking for updates."""
    from app.database import SessionLocal
    from app.models.drug import Drug

    db = SessionLocal()
    tracked_drugs = db.query(Drug.display_name).limit(20).all()
    db.close()

    drug_names = [d[0] for d in tracked_drugs] if tracked_drugs else ["warfarin", "metformin", "lisinopril"]

    results = {}
    for name in drug_names:
        logger.info(f"[Scheduled Beat] Checking updates for {name}")
        results[name] = _run_crawl_sync(name)

    return results
