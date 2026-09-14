"""
API routes for drug operations.
Provides search, detail, and safety labeling changes endpoints.
Supports multiple data sources: FDA_SRLC and HEALTH_CANADA_INFOWATCH.
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
from app.sources.health_canada.infowatch.adapter import adapter as hc_adapter
from app.sources.australia_tga.adapter import tga_adapter
from app.sources.fda_medwatch.adapter import medwatch_adapter
from app.sources.uk_mhra.adapter import mhra_adapter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/search", response_model=SearchResultResponse)
async def search_drugs(
    q: str = Query(..., min_length=1, description="Search term for drug name or active ingredient"),
    source: Optional[str] = Query(
        None,
        description="Filter by source: FDA_SRLC, HEALTH_CANADA_INFOWATCH, AUSTRALIA_TGA, FDA_MEDWATCH, or UK_MHRA. Omit to search all.",
    ),
    db: Session = Depends(get_db),
):
    """
    Search for drugs by name or active ingredient.

    - Without `source`: queries both FDA SrLC (live) and local DB.
    - With `source=HEALTH_CANADA_INFOWATCH`: searches Health Canada InfoWatch
      (crawls live data if local DB is stale or empty).
    - With `source=FDA_SRLC`: original FDA-only behaviour.
    """
    query_clean = q.strip()
    source_clean = (source or "").strip().upper()

    # ── Multi-Source Search (ALL) ───────────────────────────────────────
    if source_clean == "ALL":
        try:
            await hc_adapter.search(query=query_clean, db=db)
        except Exception as exc:
            logger.error("Health Canada search error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()

        try:
            await tga_adapter.search(query=query_clean, db=db)
        except Exception as exc:
            logger.error("Australia TGA search error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()

        try:
            await medwatch_adapter.search(query=query_clean, db=db)
        except Exception as exc:
            logger.error("FDA MedWatch search error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()

        try:
            await mhra_adapter.search(query=query_clean, db=db)
        except Exception as exc:
            logger.error("UK MHRA search error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()

        try:
            html = await crawler.search_drug(query_clean)
            if html:
                search_results = scraper.parse_search_results(html)
                for candidate in search_results[:3]:
                    drug, is_new_drug = DatabaseService.insert_or_update_drug(db, candidate)
                    detail_url = candidate.get("detail_url")
                    needs_crawl = is_new_drug
                    if not needs_crawl and detail_url:
                        existing_changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
                        if not existing_changes:
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
        except Exception as exc:
            logger.error("FDA search error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()

        all_drugs = DatabaseService.search_drugs(db, query_clean)
        results_items_all: List[DrugSearchResultItem] = []
        for d in all_drugs:
            changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
            last_verified = changes[0].last_verified_at if changes else d.updated_at or d.created_at
            results_items_all.append(
                DrugSearchResultItem(
                    drug_id=d.id,
                    drug_name=d.display_name,
                    active_ingredient=d.active_ingredient,
                    application_number=d.application_number,
                    source=d.source or "FDA_SRLC",
                    safety_change_count=len(changes),
                    last_verified_at=last_verified,
                )
            )
        return SearchResultResponse(
            query=query_clean,
            source="ALL",
            results=results_items_all,
        )

    # ── Australia TGA path ────────────────────────────────────────────
    if source_clean in ("AUSTRALIA_TGA", "TGA"):
        try:
            local_drugs = await tga_adapter.search(query=query_clean, db=db)
        except Exception as exc:
            logger.error("Australia TGA search error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()
            local_drugs = DatabaseService.search_drugs(db, query_clean, source="AUSTRALIA_TGA")

        results_items: List[DrugSearchResultItem] = []
        for d in local_drugs:
            changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
            tga_changes = [c for c in changes if "AUSTRALIA_TGA" in (c.source or "") or "TGA" in (c.source or "")]
            last_verified = tga_changes[0].last_verified_at if tga_changes else d.updated_at or d.created_at
            results_items.append(
                DrugSearchResultItem(
                    drug_id=d.id,
                    drug_name=d.display_name,
                    active_ingredient=d.active_ingredient,
                    application_number=d.application_number,
                    source=d.source or "AUSTRALIA_TGA",
                    safety_change_count=len(tga_changes),
                    last_verified_at=last_verified,
                )
            )
        return SearchResultResponse(
            query=query_clean,
            source="AUSTRALIA_TGA",
            results=results_items,
        )

    # ── Health Canada path ─────────────────────────────────────────────
    if source_clean in ("HEALTH_CANADA_INFOWATCH", "HEALTH_CANADA"):
        try:
            local_drugs = await hc_adapter.search(query=query_clean, db=db)
        except Exception as exc:
            logger.error("Health Canada search error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()
            local_drugs = DatabaseService.search_drugs(db, query_clean, source="HEALTH_CANADA")

        results_items: List[DrugSearchResultItem] = []
        for d in local_drugs:
            changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
            hc_changes = [c for c in changes if "HEALTH_CANADA" in (c.source or "")]
            last_verified = hc_changes[0].last_verified_at if hc_changes else d.updated_at or d.created_at
            results_items.append(
                DrugSearchResultItem(
                    drug_id=d.id,
                    drug_name=d.display_name,
                    active_ingredient=d.active_ingredient,
                    application_number=d.application_number,
                    source=d.source or "HEALTH_CANADA",
                    safety_change_count=len(hc_changes),
                    last_verified_at=last_verified,
                )
            )
        return SearchResultResponse(
            query=query_clean,
            source="HEALTH_CANADA",
            results=results_items,
        )

    # ── FDA MedWatch path ──────────────────────────────────────────────
    if source_clean in ("FDA_MEDWATCH", "MEDWATCH"):
        try:
            local_drugs = await medwatch_adapter.search(query=query_clean, db=db)
        except Exception as exc:
            logger.error("FDA MedWatch search error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()
            local_drugs = DatabaseService.search_drugs(db, query_clean, source="FDA_MEDWATCH")

        results_items: List[DrugSearchResultItem] = []
        for d in local_drugs:
            changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
            mw_changes = [c for c in changes if "MEDWATCH" in (c.source or "")]
            last_verified = mw_changes[0].last_verified_at if mw_changes else d.updated_at or d.created_at
            results_items.append(
                DrugSearchResultItem(
                    drug_id=d.id,
                    drug_name=d.display_name,
                    active_ingredient=d.active_ingredient,
                    application_number=d.application_number,
                    source=d.source or "FDA_MEDWATCH",
                    safety_change_count=len(mw_changes),
                    last_verified_at=last_verified,
                )
            )
        return SearchResultResponse(
            query=query_clean,
            source="FDA_MEDWATCH",
            results=results_items,
        )

    # ── UK MHRA path ──────────────────────────────────────────────────
    if source_clean in ("UK_MHRA", "MHRA"):
        try:
            local_drugs = await mhra_adapter.search(query=query_clean, db=db)
        except Exception as exc:
            logger.error("UK MHRA search error for '%s': %s", query_clean, exc, exc_info=True)
            db.rollback()
            local_drugs = DatabaseService.search_drugs(db, query_clean, source="UK_MHRA")

        results_items_mhra: List[DrugSearchResultItem] = []
        for d in local_drugs:
            changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
            mhra_changes = [c for c in changes if "MHRA" in (c.source or "")]
            last_verified = mhra_changes[0].last_verified_at if mhra_changes else d.updated_at or d.created_at
            results_items_mhra.append(
                DrugSearchResultItem(
                    drug_id=d.id,
                    drug_name=d.display_name,
                    active_ingredient=d.active_ingredient,
                    application_number=d.application_number,
                    source=d.source or "UK_MHRA",
                    safety_change_count=len(mhra_changes),
                    last_verified_at=last_verified,
                )
            )
        return SearchResultResponse(
            query=query_clean,
            source="UK_MHRA",
            results=results_items_mhra,
        )

    # ── FDA SrLC path (original behaviour) ─────────────────────────────
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
    results_items_fda: List[DrugSearchResultItem] = []
    for d in local_drugs:
        changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
        # Filter by FDA source if source param given
        if source_clean == "FDA_SRLC":
            changes = [c for c in changes if c.source == "FDA_SRLC"]
        last_verified = changes[0].last_verified_at if changes else d.updated_at or d.created_at

        results_items_fda.append(
            DrugSearchResultItem(
                drug_id=d.id,
                drug_name=d.display_name,
                active_ingredient=d.active_ingredient,
                application_number=d.application_number,
                source=d.source or "FDA_SRLC",
                safety_change_count=len(changes),
                last_verified_at=last_verified,
            )
        )

    return SearchResultResponse(
        query=query_clean,
        source=source_clean or "FDA_SRLC",
        results=results_items_fda,
    )


@router.get("/search/health-canada", response_model=SearchResultResponse)
async def search_health_canada(
    q: str = Query(..., min_length=1, description="Medicine name, brand, generic, or molecule"),
    force_refresh: bool = Query(False, description="Force re-crawl even if local data is fresh"),
    db: Session = Depends(get_db),
):
    """
    Search Health Canada Health Product InfoWatch for a medicine.

    Checks local database first. If data is stale or missing, crawls the
    Health Canada published-newsletters index, identifies relevant articles,
    extracts safety information, and stores results.

    Example: GET /api/drugs/search/health-canada?q=dimethyl+fumarate
    """
    query_clean = q.strip()
    try:
        local_drugs = await hc_adapter.search(
            query=query_clean, db=db, force_refresh=force_refresh
        )
    except Exception as exc:
        logger.error("HC search error for '%s': %s", query_clean, exc, exc_info=True)
        db.rollback()
        local_drugs = DatabaseService.search_drugs(db, query_clean)

    results_items: List[DrugSearchResultItem] = []
    for d in local_drugs:
        changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
        hc_changes = [c for c in changes if c.source == "HEALTH_CANADA_INFOWATCH"]
        last_verified = (
            hc_changes[0].last_verified_at if hc_changes else d.updated_at or d.created_at
        )
        results_items.append(
            DrugSearchResultItem(
                drug_id=d.id,
                drug_name=d.display_name,
                active_ingredient=d.active_ingredient,
                application_number=d.application_number,
                safety_change_count=len(hc_changes),
                last_verified_at=last_verified,
            )
        )

    return SearchResultResponse(
        query=query_clean,
        source="HEALTH_CANADA_INFOWATCH",
        results=results_items,
    )


@router.get("/search/fda-medwatch", response_model=SearchResultResponse)
async def search_fda_medwatch(
    q: str = Query(..., min_length=1, description="Medicine name or active ingredient"),
    force_refresh: bool = Query(False, description="Force re-crawl even if local data is fresh"),
    db: Session = Depends(get_db),
):
    """
    Search FDA MedWatch Safety Information and Adverse Event Reporting Program for a medicine.
    """
    query_clean = q.strip()
    try:
        local_drugs = await medwatch_adapter.search(
            query=query_clean, db=db, force_refresh=force_refresh
        )
    except Exception as exc:
        logger.error("MedWatch search error for '%s': %s", query_clean, exc, exc_info=True)
        db.rollback()
        local_drugs = DatabaseService.search_drugs(db, query_clean, source="FDA_MEDWATCH")

    results_items: List[DrugSearchResultItem] = []
    for d in local_drugs:
        changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
        mw_changes = [c for c in changes if "MEDWATCH" in (c.source or "")]
        last_verified = (
            mw_changes[0].last_verified_at if mw_changes else d.updated_at or d.created_at
        )
        results_items.append(
            DrugSearchResultItem(
                drug_id=d.id,
                drug_name=d.display_name,
                active_ingredient=d.active_ingredient,
                application_number=d.application_number,
                source=d.source or "FDA_MEDWATCH",
                safety_change_count=len(mw_changes),
                last_verified_at=last_verified,
            )
        )

    return SearchResultResponse(
        query=query_clean,
        source="FDA_MEDWATCH",
        results=results_items,
    )


@router.get("/search/uk-mhra", response_model=SearchResultResponse)
async def search_uk_mhra(
    q: str = Query(..., min_length=1, description="Medicine name or active ingredient"),
    force_refresh: bool = Query(False, description="Force re-crawl even if local data is fresh"),
    db: Session = Depends(get_db),
):
    """
    Search UK MHRA Drug Safety Update for a medicine.
    """
    query_clean = q.strip()
    try:
        local_drugs = await mhra_adapter.search(
            query=query_clean, db=db, force_refresh=force_refresh
        )
    except Exception as exc:
        logger.error("UK MHRA search error for '%s': %s", query_clean, exc, exc_info=True)
        db.rollback()
        local_drugs = DatabaseService.search_drugs(db, query_clean, source="UK_MHRA")

    results_items: List[DrugSearchResultItem] = []
    for d in local_drugs:
        changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
        mhra_changes = [c for c in changes if "MHRA" in (c.source or "")]
        last_verified = (
            mhra_changes[0].last_verified_at if mhra_changes else d.updated_at or d.created_at
        )
        results_items.append(
            DrugSearchResultItem(
                drug_id=d.id,
                drug_name=d.display_name,
                active_ingredient=d.active_ingredient,
                application_number=d.application_number,
                source=d.source or "UK_MHRA",
                safety_change_count=len(mhra_changes),
                last_verified_at=last_verified,
            )
        )

    return SearchResultResponse(
        query=query_clean,
        source="UK_MHRA",
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
