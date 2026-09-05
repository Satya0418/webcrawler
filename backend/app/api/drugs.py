"""
API routes for drug operations.
Provides search, detail, and safety labeling changes endpoints.
"""
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException, status, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.drug import Drug, SafetyLabelingChange
from app.schemas.drug import (
    DrugDetailResponse,
    DrugResponse,
    SearchResultResponse,
    DrugSearchResultItem,
    SafetyLabelingChangeResponse,
)
from app.services.database_service import DatabaseService
from app.crawler.fda_crawler import crawler
from app.scrapers.fda_srlc_scraper import scraper, parse_fda_date
from app.ui import export_drug_csv, export_drug_json

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/search", response_model=SearchResultResponse)
async def search_drugs(
    q: str = Query(..., min_length=1, description="Search term for drug name or active ingredient"),
    db: Session = Depends(get_db),
):
    """
    Search for drugs by name or active ingredient.
    Queries local database and verifies against FDA SrLC to ensure the latest supplement dates are captured.
    """
    query_clean = q.strip()

    # Step 1: Check local DB
    local_drugs = DatabaseService.search_drugs(db, query_clean)

    # Step 2: Query FDA to discover new drugs or newer supplement revisions
    try:
        html = await crawler.search_drug(query_clean)
        if html:
            search_results = scraper.parse_search_results(html)
            logger.info(f"FDA returned {len(search_results)} search candidates for '{query_clean}'")

            for candidate in search_results[:3]:
                drug, is_new_drug = DatabaseService.insert_or_update_drug(db, candidate)
                detail_url = candidate.get("detail_url")

                # Check if we need to crawl detail page:
                # - If new drug
                # - If drug has no local safety changes
                # - If candidate has a newer supplement date than what is locally recorded
                needs_crawl = is_new_drug
                if not needs_crawl and detail_url:
                    existing_changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
                    if not existing_changes:
                        needs_crawl = True
                    elif candidate.get("source_date"):
                        cand_dt = parse_fda_date(candidate.get("source_date"))
                        latest_local_dt = parse_fda_date(existing_changes[0].source_date)
                        if cand_dt and latest_local_dt and cand_dt > latest_local_dt:
                            needs_crawl = True

                if needs_crawl and detail_url:
                    crawler.visited_urls.discard(detail_url)
                    detail_html = await crawler.get_detail_page(detail_url)
                    if detail_html:
                        detail_data = scraper.parse_detail_page(detail_html, source_url=detail_url)
                        if detail_data:
                            if not drug.active_ingredient and detail_data.get("active_ingredient"):
                                drug.active_ingredient = detail_data["active_ingredient"]
                            if not drug.application_number and detail_data.get("application_number"):
                                drug.application_number = detail_data["application_number"]

                            for change in detail_data.get("safety_changes", []):
                                DatabaseService.save_safety_change(db, drug.id, change)

            db.commit()
            local_drugs = DatabaseService.search_drugs(db, query_clean)
    except Exception as e:
        logger.error(f"Error during FDA crawl for '{query_clean}': {e}", exc_info=True)
        db.rollback()

    # Step 3: Build response
    results_items: List[DrugSearchResultItem] = []
    for d in local_drugs:
        changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
        last_verified = changes[0].last_verified_at if changes else d.updated_at or d.created_at

        results_items.append(
            DrugSearchResultItem(
                drug_id=d.id,
                drug_name=d.display_name,
                active_ingredient=d.active_ingredient,
                application_number=d.application_number,
                safety_change_count=len(changes),
                last_verified_at=last_verified,
            )
        )

    return SearchResultResponse(
        query=query_clean,
        source="FDA_SRLC",
        results=results_items,
    )


@router.get("/{drug_id}", response_model=DrugDetailResponse)
async def get_drug_detail(
    drug_id: int,
    db: Session = Depends(get_db),
):
    """
    Get detailed information about a drug including all safety changes.
    """
    drug = DatabaseService.get_drug_by_id(db, drug_id)
    if not drug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drug with ID {drug_id} not found",
        )

    changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)

    return DrugDetailResponse(
        id=drug.id,
        display_name=drug.display_name,
        normalized_name=drug.normalized_name,
        active_ingredient=drug.active_ingredient,
        application_number=drug.application_number,
        source=drug.source,
        created_at=drug.created_at,
        updated_at=drug.updated_at,
        safety_changes=[
            SafetyLabelingChangeResponse.from_orm(c) for c in changes
        ],
    )


@router.get("/{drug_id}/safety-changes", response_model=List[SafetyLabelingChangeResponse])
async def get_drug_safety_changes(
    drug_id: int,
    db: Session = Depends(get_db),
):
    """
    Get all safety-related labeling changes for a drug.
    """
    drug = DatabaseService.get_drug_by_id(db, drug_id)
    if not drug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drug with ID {drug_id} not found",
        )

    changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
    return [SafetyLabelingChangeResponse.from_orm(c) for c in changes]


@router.get("/{drug_id}/adverse-reactions")
async def get_drug_adverse_reactions_report(
    drug_id: int,
    db: Session = Depends(get_db),
):
    """
    Get formatted Adverse Reactions report for a specific drug.
    Selects latest date with Adverse Reactions and strips section 17.
    """
    drug = DatabaseService.get_drug_by_id(db, drug_id)
    if not drug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drug with ID {drug_id} not found",
        )

    changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
    return scraper.extract_adverse_reactions_from_records(
        drug_name=drug.display_name,
        active_ingredient=drug.active_ingredient,
        changes=changes,
    )


@router.get("/{drug_id}/export")
async def export_drug_safety_data(
    drug_id: int,
    format: str = Query("json", regex="^(csv|json)$"),
    db: Session = Depends(get_db),
):
    """
    Export drug safety labeling changes in CSV or JSON format.
    """
    drug = DatabaseService.get_drug_by_id(db, drug_id)
    if not drug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drug with ID {drug_id} not found",
        )

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
