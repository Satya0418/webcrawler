"""
API routes for admin operations and system monitoring.
"""
import logging
import time
from datetime import datetime
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.database import get_db
from app.models.drug import CrawlRun
from app.crawler.fda_crawler import crawler
from app.scrapers.fda_srlc_scraper import scraper
from app.services.database_service import DatabaseService

logger = logging.getLogger(__name__)

router = APIRouter()


async def run_crawl_task(drug_name: str, crawl_id: int):
    """Background crawl task for admin trigger."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        run = db.get(CrawlRun, crawl_id)
        if not run:
            return
        run.status = "running"
        db.commit()

        html = await crawler.search_drug(drug_name)
        pages_crawled = 1
        records_found = 0
        records_added = 0
        records_changed = 0

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
        run.status = "success"
        run.pages_crawled = pages_crawled
        run.records_found = records_found
        run.records_added = records_added
        run.records_changed = records_changed
        run.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.error(f"Background crawl failed: {e}", exc_info=True)
        db.rollback()
        run = db.get(CrawlRun, crawl_id)
        if run:
            run.status = "failed"
            run.errors = str(e)
            run.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


@router.post("/crawl/fda")
async def trigger_fda_crawl(
    background_tasks: BackgroundTasks,
    drug_name: str = Query("warfarin", description="Drug to crawl or default"),
    db: Session = Depends(get_db),
):
    """
    Trigger an immediate FDA SrLC crawl.
    Logs crawl execution into crawl_runs table.
    """
    crawl_run = CrawlRun(
        source="FDA_SRLC",
        started_at=datetime.utcnow(),
        status="pending",
        pages_requested=1,
    )
    db.add(crawl_run)
    db.commit()
    db.refresh(crawl_run)

    background_tasks.add_task(run_crawl_task, drug_name, crawl_run.id)

    return {
        "message": f"Crawl triggered for '{drug_name}'",
        "crawl_run_id": crawl_run.id,
        "status": "queued",
    }


@router.get("/crawl/status")
async def get_crawl_status(
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """
    Get the status of recent FDA crawl runs.
    """
    runs = db.execute(
        select(CrawlRun).order_by(desc(CrawlRun.started_at)).limit(limit)
    ).scalars().all()

    return {
        "total": len(runs),
        "runs": [
            {
                "id": r.id,
                "source": r.source,
                "status": r.status,
                "started_at": r.started_at,
                "completed_at": r.completed_at,
                "pages_crawled": r.pages_crawled,
                "records_found": r.records_found,
                "records_added": r.records_added,
                "records_changed": r.records_changed,
                "errors": r.errors,
            }
            for r in runs
        ],
    }


@router.get("/source-health")
async def get_source_health():
    """
    Check FDA SrLC source health status, responsiveness, and latency.
    """
    url = "https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/index.cfm"
    start = time.time()
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            latency_ms = round((time.time() - start) * 1000, 2)
            if resp.status_code == 200:
                health = "Healthy"
            elif resp.status_code in (403, 429):
                health = "Warning"
            else:
                health = "Failed"

            return {
                "source": "FDA_SRLC",
                "status": health,
                "http_status": resp.status_code,
                "latency_ms": latency_ms,
                "target_url": url,
                "timestamp": datetime.utcnow().isoformat(),
            }
    except Exception as e:
        latency_ms = round((time.time() - start) * 1000, 2)
        return {
            "source": "FDA_SRLC",
            "status": "Failed",
            "error": str(e),
            "latency_ms": latency_ms,
            "target_url": url,
            "timestamp": datetime.utcnow().isoformat(),
        }
