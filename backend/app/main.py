"""
Main application factory and entry point for the Medicine Safety Backend API.
Provides REST API endpoints and clean web rendering views for drug safety data.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import init_db, get_db
from app.api import drugs, safety_changes, admin
from app.services.database_service import DatabaseService
from app.crawler.fda_crawler import crawler
from app.scrapers.fda_srlc_scraper import scraper, parse_fda_date
from app.sources.health_canada.infowatch.adapter import adapter as hc_adapter
from app.sources.australia_tga.adapter import tga_adapter
from app.sources.fda_medwatch.adapter import medwatch_adapter
from app.sources.uk_mhra.adapter import mhra_adapter
from app.ui import render_homepage_html, render_drug_detail_html, export_drug_csv, export_drug_json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown events."""
    logger.info("Starting up Medicine Safety Backend")
    init_db()
    yield
    logger.info("Shutting down Medicine Safety Backend")


# Create FastAPI app
app = FastAPI(
    title="Medicine Safety API",
    description="FDA Drug Safety-related Labeling Changes (SrLC) and Health Canada InfoWatch Backend",
    version="1.0.0",
    lifespan=lifespan,
    redoc_url=None,  # Disabled ReDoc as requested
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(drugs.router, prefix="/api/drugs", tags=["drugs"])
app.include_router(safety_changes.router, prefix="/api/safety-changes", tags=["safety"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])


# Web Interface Routes
@app.get("/", response_class=HTMLResponse)
async def homepage(
    q: Optional[str] = Query(None),
    source: Optional[str] = Query("ALL"),
    db: Session = Depends(get_db),
):
    """
    Unified Medicine Safety Search and Results page.
    Supports Health Canada InfoWatch and US FDA SrLC.
    """
    source_clean = (source or "ALL").strip().upper()
    if not q or not q.strip():
        return render_homepage_html(source=source_clean)

    query_clean = q.strip()

    # Run Health Canada and FDA live crawls concurrently
    tasks = []

    async def _crawl_hc():
        try:
            logger.info("Executing Health Canada live search for '%s'", query_clean)
            await hc_adapter.search(query=query_clean, db=db, force_refresh=True)
        except Exception as exc:
            logger.error("Health Canada search crawl error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()

    async def _crawl_fda():
        try:
            logger.info("Executing FDA search for '%s'", query_clean)
            html_resp = await crawler.search_drug(query_clean)
            if html_resp:
                search_res = scraper.parse_search_results(html_resp)
                for item in search_res[:3]:
                    drug, is_new = DatabaseService.insert_or_update_drug(db, item)
                    d_url = item.get("detail_url")

                    needs_crawl = is_new
                    if not needs_crawl and d_url:
                        existing = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
                        if not existing:
                            needs_crawl = True
                        elif item.get("source_date"):
                            cand_dt = parse_fda_date(item.get("source_date"))
                            local_dt = parse_fda_date(existing[0].source_date)
                            if cand_dt and local_dt and cand_dt > local_dt:
                                needs_crawl = True

                    if needs_crawl and d_url:
                        crawler.visited_urls.discard(d_url)
                        detail_html = await crawler.get_detail_page(d_url)
                        if detail_html:
                            detail_data = scraper.parse_detail_page(detail_html, source_url=d_url)
                            if detail_data:
                                if not drug.active_ingredient and detail_data.get("active_ingredient"):
                                    drug.active_ingredient = detail_data["active_ingredient"]
                                if not drug.application_number and detail_data.get("application_number"):
                                    drug.application_number = detail_data["application_number"]
                                for chg in detail_data.get("safety_changes", []):
                                    DatabaseService.save_safety_change(db, drug.id, chg)
                db.commit()
        except Exception as e:
            logger.error(f"FDA search crawl error: {e}", exc_info=True)
            db.rollback()

    async def _crawl_tga():
        try:
            logger.info("Executing Australia TGA live search for '%s'", query_clean)
            await tga_adapter.search(query=query_clean, db=db, force_refresh=True)
        except Exception as exc:
            logger.error("Australia TGA search crawl error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()

    async def _crawl_medwatch():
        try:
            logger.info("Executing FDA MedWatch live search for '%s'", query_clean)
            await medwatch_adapter.search(query=query_clean, db=db, force_refresh=True)
        except Exception as exc:
            logger.error("FDA MedWatch search crawl error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()

    async def _crawl_mhra():
        try:
            logger.info("Executing UK MHRA live search for '%s'", query_clean)
            await mhra_adapter.search(query=query_clean, db=db, force_refresh=True)
        except Exception as exc:
            logger.error("UK MHRA search crawl error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()

    if source_clean in ("HEALTH_CANADA_INFOWATCH", "HEALTH_CANADA", "ALL"):
        tasks.append(_crawl_hc())

    if source_clean in ("FDA_SRLC", "FDA", "ALL"):
        tasks.append(_crawl_fda())

    if source_clean in ("AUSTRALIA_TGA", "TGA", "ALL"):
        tasks.append(_crawl_tga())

    if source_clean in ("FDA_MEDWATCH", "MEDWATCH", "ALL"):
        tasks.append(_crawl_medwatch())

    if source_clean in ("UK_MHRA", "MHRA", "ALL"):
        tasks.append(_crawl_mhra())

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    # Step 3: Retrieve local results matching query
    local_drugs = DatabaseService.search_drugs(db, query_clean, source=source_clean)

    # Step 4: Build response list
    results_list = []
    for d in local_drugs:
        chgs = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
        if source_clean in ("HEALTH_CANADA_INFOWATCH", "HEALTH_CANADA"):
            chgs = [c for c in chgs if "HEALTH_CANADA" in (c.source or "")]
        elif source_clean in ("FDA_SRLC", "FDA"):
            chgs = [c for c in chgs if "FDA_SRLC" in (c.source or "")]
        elif source_clean in ("AUSTRALIA_TGA", "TGA"):
            chgs = [c for c in chgs if "AUSTRALIA_TGA" in (c.source or "") or "TGA" in (c.source or "")]
        elif source_clean in ("FDA_MEDWATCH", "MEDWATCH"):
            chgs = [c for c in chgs if "MEDWATCH" in (c.source or "")]
        elif source_clean in ("UK_MHRA", "MHRA"):
            chgs = [c for c in chgs if "MHRA" in (c.source or "")]

        d_source = d.source or "FDA_SRLC"
        last_verified = chgs[0].last_verified_at if chgs else (d.updated_at or d.created_at)
        results_list.append({
            "drug_id": d.id,
            "drug_name": d.display_name,
            "active_ingredient": d.active_ingredient,
            "application_number": d.application_number,
            "source": d_source,
            "safety_change_count": len(chgs),
            "last_verified_at": last_verified,
        })

    return render_homepage_html(query=query_clean, results=results_list, source=source_clean)


@app.get("/search", response_class=HTMLResponse)
async def web_search_redirect(
    q: str = Query(..., min_length=1),
    source: Optional[str] = Query("ALL"),
    db: Session = Depends(get_db),
):
    """Search endpoint delegating to homepage with results."""
    return await homepage(q=q, source=source, db=db)


@app.get("/drugs/{drug_id}", response_class=HTMLResponse)
async def web_drug_detail(
    drug_id: int,
    db: Session = Depends(get_db),
):
    """
    Render full drug detail view showing all safety labeling changes.
    Adapts for Health Canada InfoWatch or FDA SrLC.
    """
    drug = DatabaseService.get_drug_by_id(db, drug_id)
    if not drug:
        return render_homepage_html(error=f"Drug #{drug_id} not found.")

    changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
    drug_dict = {
        "id": drug.id,
        "display_name": drug.display_name,
        "normalized_name": drug.normalized_name,
        "active_ingredient": drug.active_ingredient,
        "application_number": drug.application_number,
        "source": drug.source,
    }
    changes_list = [
        {
            "id": c.id,
            "source": c.source,
            "section": c.section,
            "change_type": c.change_type,
            "source_record_id": c.source_record_id,
            "source_date": c.source_date,
            "updated_text": c.updated_text,
            "original_text": c.original_text,
            "fda_comment": c.fda_comment,
            "source_url": c.source_url,
            "last_verified_at": c.last_verified_at,
        }
        for c in changes
    ]
    return render_drug_detail_html(drug_dict, changes_list)


@app.get("/drugs/{drug_id}/export")
async def web_drug_export(
    drug_id: int,
    format: str = Query("csv", regex="^(csv|json)$"),
    db: Session = Depends(get_db),
):
    """
    Download drug safety data in CSV or JSON format.
    """
    drug = DatabaseService.get_drug_by_id(db, drug_id)
    if not drug:
        return Response(status_code=404, content="Drug not found")

    changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
    clean_name = (drug.normalized_name or "drug").replace(" ", "_")

    if format.lower() == "csv":
        csv_data = export_drug_csv(drug, changes)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{clean_name}_safety_changes.csv"'
            },
        )
    else:
        json_data = export_drug_json(drug, changes)
        return Response(
            content=json_data,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{clean_name}_safety_changes.json"'
            },
        )


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "medicine-safety-backend",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
