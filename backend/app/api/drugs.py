"""
API routes for drug operations.
Provides search, detail, and safety labeling changes endpoints.
Supports multiple data sources: FDA_SRLC and HEALTH_CANADA_INFOWATCH.
"""
import logging
import re
from typing import List, Optional, Any, Tuple, Dict
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException, status, Response
from fastapi.responses import HTMLResponse
import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.drug import Drug, SafetyLabelingChange
from app.schemas.drug import (
    DrugDetailResponse,
    DrugResponse,
    SearchResultResponse,
    DrugSearchResultItem,
    SafetyLabelingChangeResponse,
    SignalAndRiskItem,
    SignalAndRiskResponse,
    SignalAndRiskIntegrationRequest,
)
from app.services.database_service import DatabaseService
from app.crawler.fda_crawler import crawler
from app.scrapers.fda_srlc_scraper import scraper, parse_fda_date
from app.ui import export_drug_csv, export_drug_json, export_drug_html, export_drug_clean_html
# ── TEMPORARILY DISABLED: Other regulatory adapters (Only US FDA SrLC is active) ──
# Uncomment when ready to re-enable other regulatory sources:
# from app.sources.health_canada.infowatch.adapter import adapter as hc_adapter
# from app.sources.australia_tga.adapter import tga_adapter
# from app.sources.fda_medwatch.adapter import medwatch_adapter
# from app.sources.uk_mhra.adapter import mhra_adapter

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
        # ── TEMPORARILY DISABLED: Other regulatory crawlers ─────────────────
        # try:
        #     await hc_adapter.search(query=query_clean, db=db)
        # except Exception as exc:
        #     logger.error("Health Canada search error for '%s': %s", query_clean, exc, exc_info=True)
        #     db.rollback()

        # try:
        #     await tga_adapter.search(query=query_clean, db=db)
        # except Exception as exc:
        #     logger.error("Australia TGA search error for '%s': %s", query_clean, exc, exc_info=True)
        #     db.rollback()

        # try:
        #     await medwatch_adapter.search(query=query_clean, db=db)
        # except Exception as exc:
        #     logger.error("FDA MedWatch search error for '%s': %s", query_clean, exc, exc_info=True)
        #     db.rollback()

        # try:
        #     await mhra_adapter.search(query=query_clean, db=db)
        # except Exception as exc:
        #     logger.error("UK MHRA search error for '%s': %s", query_clean, exc, exc_info=True)
        #     db.rollback()

        # Live US FDA SrLC crawl:
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

    # ── TEMPORARILY DISABLED: Non-FDA individual crawler branches ───────
    # (Uncomment when other agencies are re-enabled)
    # if source_clean in ("AUSTRALIA_TGA", "TGA"):
    #     try:
    #         local_drugs = await tga_adapter.search(query=query_clean, db=db)
    #     except Exception as exc:
    #         logger.error("Australia TGA search error for '%s': %s", query_clean, exc, exc_info=True)
    #         db.rollback()
    #         local_drugs = DatabaseService.search_drugs(db, query_clean, source="AUSTRALIA_TGA")
    # ...
    if source_clean in ("AUSTRALIA_TGA", "TGA", "HEALTH_CANADA_INFOWATCH", "HEALTH_CANADA", "FDA_MEDWATCH", "MEDWATCH", "UK_MHRA", "MHRA"):
        local_drugs = DatabaseService.search_drugs(db, query_clean, source=source_clean)
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
                    source=d.source or source_clean,
                    safety_change_count=len(changes),
                    last_verified_at=last_verified,
                )
            )
        return SearchResultResponse(
            query=query_clean,
            source=source_clean,
            results=results_items,
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


# ── TEMPORARILY DISABLED: Dedicated non-FDA search endpoints ──────────────────
# Uncomment when ready to re-enable other regulatory sources:
# @router.get("/search/health-canada", response_model=SearchResultResponse)
# async def search_health_canada(
#     q: str = Query(..., min_length=1, description="Medicine name, brand, generic, or molecule"),
#     force_refresh: bool = Query(False, description="Force re-crawl even if local data is fresh"),
#     db: Session = Depends(get_db),
# ):
#     ...
# @router.get("/search/fda-medwatch", response_model=SearchResultResponse)
# async def search_fda_medwatch(
#     q: str = Query(..., min_length=1, description="Medicine name or active ingredient"),
#     force_refresh: bool = Query(False, description="Force re-crawl even if local data is fresh"),
#     db: Session = Depends(get_db),
# ):
#     ...
# @router.get("/search/uk-mhra", response_model=SearchResultResponse)
# async def search_uk_mhra(
#     q: str = Query(..., min_length=1, description="Medicine name or active ingredient"),
#     force_refresh: bool = Query(False, description="Force re-crawl even if local data is fresh"),
#     db: Session = Depends(get_db),
# ):
#     ...


async def send_salesforce_callback(payload: dict, callback_url: Optional[str] = None) -> dict:
    """
    Dispatches the extracted drug safety Signal and Risk payload to the Salesforce
    updateSubmissionResponse webhook.
    """
    target_url = (callback_url or getattr(settings, "SALESFORCE_CALLBACK_URL", None) or "").strip()
    if not target_url:
        logger.warning("No Salesforce callback URL configured; skipping outbound webhook.")
        return {"status": "skipped", "detail": "No callback URL configured"}

    logger.info("Dispatching Salesforce callback for submissionId '%s' to %s", payload.get("submissionId"), target_url)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                target_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            logger.info("Salesforce callback returned status %s", resp.status_code)
            return {
                "status": "delivered" if resp.status_code in (200, 201, 204) else "failed",
                "status_code": resp.status_code,
                "url": target_url,
            }
    except Exception as exc:
        logger.error("Failed to send Salesforce callback to %s: %s", target_url, exc)
        return {"status": "error", "error": str(exc), "url": target_url}


DATE_REGEX_DMY = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")
DATE_REGEX_YMD = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")


def validate_client_date_range(
    start_date_val: Optional[Any],
    end_date_val: Optional[Any],
):
    """
    Standardizes and validates client dates in DD-MM-YYYY or ISO/YYYY-MM-DD format.
    Rejects malformed, ambiguous, or invalid calendar dates with HTTP 422.
    Rejects startDate > endDate with HTTP 422.
    Returns (start_dt, end_dt, start_str, end_str).
    """
    def _parse(val: Optional[Any], name: str) -> Optional[datetime]:
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None
        s_clean = s.split("T")[0].strip() if "T" in s else s
        m_dmy = DATE_REGEX_DMY.match(s_clean)
        m_ymd = DATE_REGEX_YMD.match(s_clean)
        if m_dmy:
            d, mth, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        elif m_ymd:
            y, mth, d = int(m_ymd.group(1)), int(m_ymd.group(2)), int(m_ymd.group(3))
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid date format for '{name}': '{s}'. Expected DD-MM-YYYY (e.g. '01-01-2025') or YYYY-MM-DD.",
            )
        try:
            return datetime(y, mth, d)
        except ValueError as err:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid calendar date for '{name}': '{s}' ({err}). Expected DD-MM-YYYY or YYYY-MM-DD.",
            )

    start_dt = _parse(start_date_val, "startDate")
    end_dt = _parse(end_date_val, "endDate")

    start_str = start_dt.strftime("%d-%m-%Y") if start_dt else ""
    end_str = end_dt.strftime("%d-%m-%Y") if end_dt else ""

    if start_dt and end_dt:
        if start_dt > end_dt:
            raise HTTPException(
                status_code=422,
                detail=f"startDate ('{start_str}') cannot be later than endDate ('{end_str}').",
            )
        start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif start_dt:
        start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elif end_dt:
        end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    return start_dt, end_dt, start_str, end_str


@router.post(
    "/signal-and-risk",
    response_model=SignalAndRiskResponse,
    summary="Teammate Integration: Fetch FDA Drug Safety data by submission and product",
)
@router.post(
    "/products/signal-and-risk",
    response_model=SignalAndRiskResponse,
    include_in_schema=False,
)
@router.post(
    "/product/signal-and-risk",
    response_model=SignalAndRiskResponse,
    include_in_schema=False,
)
async def post_signal_and_risk(
    req: SignalAndRiskIntegrationRequest,
    db: Session = Depends(get_db),
):
    """
    **Teammate Integration Endpoint**:
    Receives submissionId, productName, startDate, endDate, genericName, activeIngredients,
    looks up or live-crawls FDA SrLC drug safety data,
    dispatches an outbound callback to Salesforce (updateSubmissionResponse),
    and returns a SignalAndRisk payload containing the extracted HTML inside the 'Data' field.
    Supports format='html' (pure HTML response) or format='data' ({"Data": "<html..."}).
    """
    raw_sub_id = req.submissionId if req.submissionId is not None else req.submission_id
    if raw_sub_id is None or not str(raw_sub_id).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Field 'submissionId' is required and cannot be empty.",
        )
    sub_id = str(raw_sub_id).strip()

    raw_prod_name = req.productName if req.productName is not None else req.product_name
    if raw_prod_name is None or not str(raw_prod_name).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Field 'productName' is required and cannot be empty.",
        )
    prod_name = str(raw_prod_name).strip()

    # Date range validation (DD-MM-YYYY)
    raw_start = req.startDate if req.startDate is not None else req.start_date
    raw_end = req.endDate if req.endDate is not None else req.end_date
    start_dt, end_dt, start_str, end_str = validate_client_date_range(raw_start, raw_end)

    # Multi-filter extraction
    gen_name = (req.genericName or req.generic_name or "").strip() or None
    act_ingr = (
        req.activeIngredients
        or req.active_ingredients
        or req.activeIngredient
        or req.active_ingredient
        or ""
    ).strip() or None

    # Step 1: Look up in local database using multi-filter query
    local_drugs = DatabaseService.search_drugs_filtered(
        db,
        product_name=prod_name,
        generic_name=gen_name,
        active_ingredients=act_ingr,
    )
    if not local_drugs and gen_name:
        local_drugs = DatabaseService.search_drugs_filtered(
            db,
            product_name=gen_name,
            active_ingredients=act_ingr,
        )
    if not local_drugs and act_ingr:
        local_drugs = DatabaseService.search_drugs_filtered(
            db,
            product_name=act_ingr,
        )
    drug = local_drugs[0] if local_drugs else None
    changes = (
        DatabaseService.get_safety_changes_by_drug_id(db, drug.id, start_date=start_dt, end_date=end_dt)
        if drug else []
    )

    # Step 2: If no data locally or no changes found, query FDA SrLC live
    # Traverses all search candidates (not just the first few) and tries generic/ingredient fallbacks
    if not drug or not changes:
        try:
            # Build prioritized search queries: productName -> genericName -> activeIngredients
            search_queries = [prod_name]
            if gen_name and gen_name.lower() != prod_name.lower():
                search_queries.append(gen_name)
            if act_ingr:
                for part in act_ingr.split(","):
                    clean_part = part.strip()
                    if clean_part and clean_part.lower() not in [q.lower() for q in search_queries]:
                        search_queries.append(clean_part)

            search_results = []
            for query_term in search_queries:
                html = await crawler.search_drug(query_term)
                if html:
                    parsed = scraper.parse_search_results(html)
                    if parsed:
                        search_results = parsed
                        break

            if search_results:
                seen_detail_urls = set()
                crawled_drugs = []
                # Consider all applicable results, traversing all candidates rather than slicing
                for candidate in search_results:
                    detail_url = candidate.get("detail_url")
                    if not detail_url or detail_url in seen_detail_urls:
                        continue
                    seen_detail_urls.add(detail_url)

                    c_drug, is_new = DatabaseService.insert_or_update_drug(db, candidate)
                    crawled_drugs.append(c_drug)
                    crawler.visited_urls.discard(detail_url)
                    detail_html = await crawler.get_detail_page(detail_url)
                    if detail_html:
                        detail_data = scraper.parse_detail_page(detail_html, source_url=detail_url)
                        if detail_data:
                            if not c_drug.active_ingredient and detail_data.get("active_ingredient"):
                                c_drug.active_ingredient = detail_data["active_ingredient"]
                            if not c_drug.application_number and detail_data.get("application_number"):
                                c_drug.application_number = detail_data["application_number"]
                            for change in detail_data.get("safety_changes", []):
                                DatabaseService.save_safety_change(db, c_drug.id, change)
                db.commit()

                # Re-query local database after crawl with all filters applied, falling back if brand differs
                local_drugs = DatabaseService.search_drugs_filtered(
                    db,
                    product_name=prod_name,
                    generic_name=gen_name,
                    active_ingredients=act_ingr,
                )
                if not local_drugs and gen_name:
                    local_drugs = DatabaseService.search_drugs_filtered(
                        db,
                        product_name=gen_name,
                        active_ingredients=act_ingr,
                    )
                if not local_drugs and act_ingr:
                    local_drugs = DatabaseService.search_drugs_filtered(
                        db,
                        product_name=act_ingr,
                    )
                if not local_drugs and crawled_drugs:
                    local_drugs = crawled_drugs

                drug = local_drugs[0] if local_drugs else None
                changes = (
                    DatabaseService.get_safety_changes_by_drug_id(db, drug.id, start_date=start_dt, end_date=end_dt)
                    if drug else []
                )
        except Exception as exc:
            logger.error("Live FDA crawl error in signal-and-risk for '%s': %s", prod_name, exc)
            db.rollback()

    if not drug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No FDA Drug Safety data found for product '{prod_name}'.",
        )

    is_date_filtered = (start_dt is not None or end_dt is not None)
    filter_latest = not is_date_filtered

    if is_date_filtered and not changes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No safety labeling changes found for '{prod_name}' within requested date range ({start_str} to {end_str}).",
        )

    matched_product = drug.display_name or prod_name
    html_content = export_drug_clean_html(drug, changes, standalone=False, filter_latest=filter_latest)
    standalone_html = export_drug_clean_html(drug, changes, standalone=True, filter_latest=filter_latest)
    fmt = (req.format or "json").lower()

    if fmt == "html":
        return HTMLResponse(content=standalone_html, media_type="text/html")

    if fmt == "data":
        return {"Data": html_content}

    # Determine website_Name based on drug source
    src = (drug.source or "FDA_SRLC").upper()
    if "TGA" in src:
        site_name = "TGA_details"
    elif "CANADA" in src or "HC" in src:
        site_name = "Health_Canada_details"
    elif "MHRA" in src:
        site_name = "MHRA_details"
    elif "MEDWATCH" in src:
        site_name = "MedWatch_details"
    else:
        site_name = "FDA_details"

    resp_type = req.responseType or req.response_type or "SafetyActionTaken"

    website_item = {
        "website_Name": site_name,
        "title": "Website Safety Data",
        "productName": matched_product,
        "genericName": gen_name or (drug.active_ingredient or ""),
        "activeIngredients": drug.active_ingredient or act_ingr or "",
        "startDate": start_str,
        "endDate": end_str,
        "Data": standalone_html,
        "website_Data": standalone_html,
        "submissionId": sub_id,
    }

    # Check source coverage limitation: US FDA SrLC records begin from 01-01-2016
    fda_srlc_min_date = datetime(2016, 1, 1, 0, 0, 0)
    is_partial_coverage = False
    coverage_limitation_note = None
    if start_dt and start_dt < fda_srlc_min_date:
        is_partial_coverage = True
        coverage_limitation_note = (
            "US FDA SrLC records begin from 01-01-2016. Safety labeling changes prior to 2016 "
            "are not indexed in this database and may reside in the FDA MedWatch archive."
        )

    website_Data_wrapper = {
        "title": "Website Crawler Data",
        "status": "success",
        "data": [website_item],
    }
    if is_partial_coverage:
        website_Data_wrapper["coverage"] = "partial"
        website_Data_wrapper["source_limitation"] = coverage_limitation_note
    elif is_date_filtered:
        website_Data_wrapper["coverage"] = "complete"

    clean_website_item = {
        "website_Name": site_name,
        "website_Data": standalone_html,
    }

    response_payload = {
        "submissionId": sub_id,
        "responseType": resp_type,
        "productName": matched_product,
        "website_Data": website_Data_wrapper,
        "responseData": [clean_website_item],
    }

    # Dispatch outbound callback if target specified or configured
    target_callback = (req.callbackUrl or req.callback_url or getattr(settings, "SALESFORCE_CALLBACK_URL", None) or "").strip()
    if target_callback and target_callback.lower() not in ("none", "skip", "disabled", "false"):
        salesforce_payload = {
            "submissionId": sub_id,
            "responseType": resp_type,
            "responseData": [clean_website_item],
        }
        await send_salesforce_callback(salesforce_payload, target_callback)

    return response_payload


@router.get(
    "/signal-and-risk",
    response_model=SignalAndRiskResponse,
    summary="Teammate Integration: Fetch FDA Drug Safety data via GET query for browser/API testing",
)
@router.get(
    "/products/signal-and-risk",
    response_model=SignalAndRiskResponse,
    include_in_schema=False,
)
@router.get(
    "/product/signal-and-risk",
    response_model=SignalAndRiskResponse,
    include_in_schema=False,
)
async def get_signal_and_risk(
    productName: Optional[str] = Query(None, description="Medicine or product name (e.g. 'amikacin', 'Lipitor')"),
    submissionId: Optional[str] = Query("browser_test", description="Submission identifier"),
    startDate: Optional[str] = Query(None, description="Start date filter (DD-MM-YYYY)"),
    endDate: Optional[str] = Query(None, description="End date filter (DD-MM-YYYY)"),
    genericName: Optional[str] = Query(None, description="Generic name filter"),
    activeIngredients: Optional[str] = Query(None, description="Active ingredient filter"),
    callbackUrl: Optional[str] = Query(None, description="Optional custom Salesforce callback webhook URL"),
    format: Optional[str] = Query("json", description="Output format: 'json', 'html', or 'data'"),
    product_name: Optional[str] = Query(None, include_in_schema=False),
    submission_id: Optional[str] = Query(None, include_in_schema=False),
    start_date: Optional[str] = Query(None, include_in_schema=False),
    end_date: Optional[str] = Query(None, include_in_schema=False),
    generic_name: Optional[str] = Query(None, include_in_schema=False),
    active_ingredients: Optional[str] = Query(None, include_in_schema=False),
    callback_url: Optional[str] = Query(None, include_in_schema=False),
    db: Session = Depends(get_db),
):
    """
    Browser & Client Testing Helper:
    Fetch FDA safety data directly using GET parameters, e.g.
    /api/drugs/signal-and-risk?productName=Lipitor&submissionId=test123
    """
    prod = (productName or product_name or "").strip()
    sub = (submissionId or submission_id or "browser_test").strip()
    cb = (callbackUrl or callback_url or "").strip() or None
    s_date = (startDate or start_date or "").strip() or None
    e_date = (endDate or end_date or "").strip() or None
    g_name = (genericName or generic_name or "").strip() or None
    a_ingr = (activeIngredients or active_ingredients or "").strip() or None
    if not prod:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'productName' is required.",
        )
    return await post_signal_and_risk(
        SignalAndRiskIntegrationRequest(
            submissionId=sub,
            productName=prod,
            startDate=s_date,
            endDate=e_date,
            genericName=g_name,
            activeIngredients=a_ingr,
            callbackUrl=cb,
            format=format,
        ),
        db=db,
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

    if "MEDWATCH" in (drug.source or "").upper():
        ar_change = next(
            (c for c in changes if "Section 6" in (c.change_type or "") or "Adverse Reactions" in (c.section or "")),
            None,
        )
        art_change = next(
            (c for c in changes if "MedWatch Alert" in (c.change_type or "") or "MedWatch Safety Communication" in (c.section or "")),
            None,
        )

        if ar_change and ar_change.updated_text and "NOT FOUND" not in ar_change.updated_text:
            pdf_url = ar_change.source_url or ""
            doc_date = str(ar_change.source_date)[:10] if ar_change.source_date else ""
            fda_comm = ar_change.fda_comment or ""
            pages_m = re.search(r"Pages?:\s*([0-9\s,\-–—]+)", fda_comm)
            page_str = pages_m.group(1).strip() if pages_m else ""
            pages_list = []
            if page_str:
                page_str = re.sub(r"[–—]", "-", page_str)
                for part in page_str.split(","):
                    part = part.strip()
                    if "-" in part:
                        try:
                            p_parts = [int(p) for p in part.split("-")]
                            pages_list.extend(range(p_parts[0], p_parts[1] + 1))
                        except Exception:
                            pass
                    elif part.isdigit():
                        pages_list.append(int(part))
            if not pages_list:
                text_pages = re.findall(r"\[Page\s+(\d+)\]", clean_text)
                if text_pages:
                    pages_list = sorted(list({int(p) for p in text_pages}))

            clean_text = ar_change.updated_text or ""
            subsections = []
            sub_matches = list(re.finditer(r"###\s+([^\n]+)\n(.*?)(?=(?:###\s+[^\n]+\n)|\Z)", clean_text, re.DOTALL))
            for sm in sub_matches:
                sub_title = sm.group(1).strip()
                sub_body = sm.group(2).strip()
                p_in_sub = re.findall(r"\[Page\s+(\d+)\]", sub_body)
                sub_pages = sorted(list({int(p) for p in p_in_sub})) if p_in_sub else (pages_list or [])
                subsections.append({
                    "name": sub_title,
                    "pages": sub_pages,
                    "content": sub_body,
                })

            tables = []
            tbl_blocks = re.findall(r"((?:\|[^\n]+\|\n?)+)", clean_text)
            for tidx, tb in enumerate(tbl_blocks):
                lines = [l.strip() for l in tb.strip().split("\n") if l.strip().startswith("|")]
                if len(lines) >= 3:
                    headers = [c.strip() for c in lines[0].split("|")[1:-1]]
                    rows = []
                    for row_line in lines[2:]:
                        cells = [c.strip() for c in row_line.split("|")[1:-1]]
                        row_dict = {headers[ci]: cells[ci] for ci in range(min(len(headers), len(cells)))}
                        rows.append(row_dict)
                    tables.append({
                        "title": f"Adverse Reactions Table {tidx + 1}",
                        "pages": pages_list or [1],
                        "headers": headers,
                        "rows": rows,
                    })

            return {
                "product": drug.display_name,
                "source": "FDA MedWatch",
                "medwatch_article": {
                    "title": art_change.change_type.replace("FDA MedWatch Alert: ", "") if art_change and art_change.change_type else "",
                    "publication_date": str(art_change.source_date)[:10] if art_change and art_change.source_date else "",
                    "url": art_change.source_url if art_change else "",
                },
                "product_information": {
                    "document_found": True,
                    "document_title": "Full Prescribing Information",
                    "document_date": doc_date,
                    "pdf_url": pdf_url,
                },
                "adverse_reactions": {
                    "found": True,
                    "section": "6. ADVERSE REACTIONS",
                    "pages": pages_list,
                    "subsections": subsections,
                    "tables": tables,
                },
            }
        else:
            return {
                "product": drug.display_name,
                "source": "FDA MedWatch",
                "medwatch_article": {
                    "title": art_change.change_type.replace("FDA MedWatch Alert: ", "") if art_change and art_change.change_type else "",
                    "publication_date": str(art_change.source_date)[:10] if art_change and art_change.source_date else "",
                    "url": art_change.source_url if art_change else "",
                },
                "product_information": {
                    "document_found": False,
                    "pdf_url": None,
                },
                "adverse_reactions": {
                    "found": False,
                    "status": "ADVERSE_REACTIONS_SECTION_NOT_FOUND",
                },
            }

    return scraper.extract_adverse_reactions_from_records(
        drug_name=drug.display_name,
        active_ingredient=drug.active_ingredient,
        changes=changes,
    )



@router.get("/{drug_id}/export")
async def export_drug_safety_data(
    drug_id: int,
    format: str = Query("json", regex="^(csv|json|html)$"),
    db: Session = Depends(get_db),
):
    """
    Export drug safety labeling changes in HTML, CSV, or JSON format.
    """
    drug = DatabaseService.get_drug_by_id(db, drug_id)
    if not drug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drug with ID {drug_id} not found",
        )

    changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
    clean_name = (drug.normalized_name or "drug").replace(" ", "_")

    if format.lower() == "html":
        html_data = export_drug_html(drug, changes, standalone=True)
        return Response(
            content=html_data,
            media_type="text/html",
            headers={
                "Content-Disposition": f'attachment; filename="{clean_name}_safety_report.html"'
            },
        )
    elif format.lower() == "csv":
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


@router.get("/{drug_id}/html", response_class=HTMLResponse)
async def get_drug_html_report(
    drug_id: int,
    download: bool = Query(False, description="Whether to trigger file download"),
    db: Session = Depends(get_db),
):
    """
    Get clean standalone HTML report for a drug.
    If download=true, sends Content-Disposition attachment header.
    """
    drug = DatabaseService.get_drug_by_id(db, drug_id)
    if not drug:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drug with ID {drug_id} not found",
        )
    changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
    html_content = export_drug_html(drug, changes, standalone=True)
    if download:
        clean_name = (drug.normalized_name or "drug").replace(" ", "_")
        return Response(
            content=html_content,
            media_type="text/html",
            headers={
                "Content-Disposition": f'attachment; filename="{clean_name}_safety_report.html"'
            },
        )
    return HTMLResponse(content=html_content, media_type="text/html")

