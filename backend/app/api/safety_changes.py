"""
API routes for safety-related labeling changes and version history.
"""
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.drug import SafetyLabelingChangeResponse, SafetyChangeVersionResponse
from app.services.database_service import DatabaseService
from app.scrapers.fda_srlc_scraper import scraper
from app.crawler.fda_crawler import crawler

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/adverse-reactions")
async def get_adverse_reactions(
    drug_name: Optional[str] = Query(None, description="Medicine name or active ingredient (e.g. ARIKAYCE KIT, Warfarin)"),
    drug_id: Optional[int] = Query(None, description="Database Drug ID"),
    url: Optional[str] = Query(None, description="Direct FDA detail page URL or DrugNameID (e.g. 2214)"),
    db: Session = Depends(get_db),
):
    """
    Get the latest Adverse Reactions labeling change for a medicine according to report format:
    1. Checks all dates for the medicine chronologically (latest date first).
    2. Selects the most recent date in which Adverse Reactions is present.
    3. Strips section 17 (PCI/PI/MG / Medication Guide / Patient Counseling Information).
    4. Removes editorial noise ('Additions underlined', '...', '[see Warnings...]').
    5. Formats date as DD-Mon-YYYY (e.g. 05-Dec-2025).
    6. Returns 'No data is present on adverse reaction' if no Adverse Reactions exist.
    """
    if not drug_name and not drug_id and not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide at least one parameter: 'drug_name', 'drug_id', or 'url'",
        )

    # Path 1: Direct detail URL or DrugNameID provided
    if url:
        html = await crawler.get_detail_page(url)
        if not html:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch FDA detail page from {url}",
            )
        return scraper.extract_adverse_reactions_report(html, drug_name=drug_name, source_url=url)

    # Path 2: Drug ID provided
    if drug_id:
        drug = DatabaseService.get_drug_by_id(db, drug_id)
        if not drug:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Drug with ID {drug_id} not found",
            )
        changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
        if changes:
            report = scraper.extract_adverse_reactions_from_records(
                drug_name=drug.display_name,
                active_ingredient=drug.active_ingredient,
                changes=changes,
            )
            if report.get("status") == "success":
                return report

        # If no local adverse reactions or none in DB, search FDA online
        drug_name = drug.display_name

    # Path 3: Search by Drug Name
    query_clean = drug_name.strip()
    local_drugs = DatabaseService.search_drugs(db, query_clean)

    if local_drugs:
        for d in local_drugs:
            changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
            if changes:
                report = scraper.extract_adverse_reactions_from_records(
                    drug_name=d.display_name,
                    active_ingredient=d.active_ingredient,
                    changes=changes,
                )
                if report.get("status") == "success":
                    return report

    # Query FDA online on-demand
    logger.info(f"Querying FDA SrLC for adverse reactions: '{query_clean}'")
    try:
        search_html = await crawler.search_drug(query_clean)
        if not search_html:
            return {
                "status": "no_data",
                "drug_name": query_clean,
                "message": "No data is present on adverse reaction",
                "formatted_report": "No data is present on adverse reaction",
            }

        candidates = scraper.parse_search_results(search_html)
        if not candidates:
            return {
                "status": "no_data",
                "drug_name": query_clean,
                "message": "No data is present on adverse reaction",
                "formatted_report": "No data is present on adverse reaction",
            }

        # Check candidate detail pages
        for cand in candidates[:3]:
            detail_url = cand.get("detail_url")
            if detail_url:
                detail_html = await crawler.get_detail_page(detail_url)
                if detail_html:
                    report = scraper.extract_adverse_reactions_report(
                        detail_html,
                        drug_name=cand.get("drug_name"),
                        active_ingredient=cand.get("active_ingredient"),
                        source_url=detail_url,
                    )
                    # Also persist in database
                    try:
                        drug_obj, _ = DatabaseService.insert_or_update_drug(db, cand)
                        detail_data = scraper.parse_detail_page(detail_html, source_url=detail_url)
                        if detail_data:
                            for chg in detail_data.get("safety_changes", []):
                                DatabaseService.save_safety_change(db, drug_obj.id, chg)
                        db.commit()
                    except Exception as db_err:
                        logger.warning(f"Error saving crawled changes: {db_err}")
                        db.rollback()

                    if report.get("status") == "success":
                        return report

        return {
            "status": "no_data",
            "drug_name": query_clean,
            "message": "No data is present on adverse reaction",
            "formatted_report": "No data is present on adverse reaction",
        }

    except Exception as e:
        logger.error(f"Error in adverse reactions crawl for '{query_clean}': {e}", exc_info=True)
        return {
            "status": "error",
            "drug_name": query_clean,
            "message": f"Error: {str(e)}",
            "formatted_report": "No data is present on adverse reaction",
        }


@router.post("/adverse-reactions/extract")
async def extract_adverse_reactions_from_html(
    payload: Dict[str, Any] = Body(...),
):
    """
    Extract Adverse Reactions report directly from raw HTML.
    Useful for testing, custom scraper flows, or direct payload extraction.
    """
    html_content = payload.get("html") or ""
    drug_name = payload.get("drug_name")
    active_ingredient = payload.get("active_ingredient")

    if not html_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload must contain 'html' key with HTML content",
        )

    return scraper.extract_adverse_reactions_report(
        html_content,
        drug_name=drug_name,
        active_ingredient=active_ingredient,
    )


@router.get("/{record_id}", response_model=SafetyLabelingChangeResponse)
async def get_safety_change(
    record_id: int,
    db: Session = Depends(get_db),
):
    """
    Get a specific safety-related labeling change record.
    """
    change = DatabaseService.get_safety_change_by_id(db, record_id)
    if not change:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Safety labeling change with ID {record_id} not found",
        )
    return SafetyLabelingChangeResponse.from_orm(change)


@router.get("/{record_id}/history", response_model=List[SafetyChangeVersionResponse])
async def get_safety_change_history(
    record_id: int,
    db: Session = Depends(get_db),
):
    """
    Get version history for a safety-related labeling change.
    Returns all historical versions archived whenever content hashes changed.
    """
    change = DatabaseService.get_safety_change_by_id(db, record_id)
    if not change:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Safety labeling change with ID {record_id} not found",
        )

    versions = DatabaseService.get_versions_by_change_id(db, record_id)
    return [SafetyChangeVersionResponse.from_orm(v) for v in versions]


@router.get("/{record_id}/versions", response_model=List[SafetyChangeVersionResponse])
async def get_safety_change_versions(
    record_id: int,
    db: Session = Depends(get_db),
):
    """Alias for /history."""
    return await get_safety_change_history(record_id, db)
