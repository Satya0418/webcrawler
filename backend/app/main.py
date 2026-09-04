"""
Main application factory and entry point for the Medicine Safety Backend API.
Provides REST API endpoints and clean web rendering views for drug safety data.
"""
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
from app.scrapers.fda_srlc_scraper import scraper
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
    description="FDA Drug Safety-related Labeling Changes (SrLC) Backend",
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
    db: Session = Depends(get_db),
):
    """
    Unified Medicine Safety Search and Results page.
    """
    if not q or not q.strip():
        return render_homepage_html()

    query_clean = q.strip()
    local_drugs = DatabaseService.search_drugs(db, query_clean)
    has_safety = any(DatabaseService.get_safety_changes_by_drug_id(db, d.id) for d in local_drugs)

    if not local_drugs or not has_safety:
        try:
            html_resp = await crawler.search_drug(query_clean)
            if html_resp:
                search_res = scraper.parse_search_results(html_resp)
                for item in search_res[:3]:
                    drug, _ = DatabaseService.insert_or_update_drug(db, item)
                    d_url = item.get("detail_url")
                    if d_url:
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
                local_drugs = DatabaseService.search_drugs(db, query_clean)
        except Exception as e:
            logger.error(f"Search crawl error: {e}", exc_info=True)
            db.rollback()

    results_list = []
    for d in local_drugs:
        chgs = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
        results_list.append({
            "drug_id": d.id,
            "drug_name": d.display_name,
            "active_ingredient": d.active_ingredient,
            "application_number": d.application_number,
            "safety_change_count": len(chgs),
            "last_verified_at": chgs[0].last_verified_at if chgs else d.created_at,
        })

    return render_homepage_html(query=query_clean, results=results_list)


@app.get("/search", response_class=HTMLResponse)
async def web_search_redirect(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    """Search endpoint delegating to homepage with results."""
    return await homepage(q=q, db=db)


@app.get("/drugs/{drug_id}", response_class=HTMLResponse)
async def web_drug_detail(
    drug_id: int,
    db: Session = Depends(get_db),
):
    """
    Render full drug detail view showing all safety labeling changes grouped
    by supplement date with bullet points, subsections, and PDF links.
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
    }
    changes_list = [
        {
            "id": c.id,
            "section": c.section,
            "source_record_id": c.source_record_id,
            "source_date": c.source_date,
            "updated_text": c.updated_text,
            "original_text": c.original_text,
            "fda_comment": c.fda_comment,
            "source_url": c.source_url,
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
