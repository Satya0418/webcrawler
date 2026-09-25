import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Header, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from backend.config import API_KEY
from backend.database.db import get_db
from backend.database.models import ProductSectionRecord
from backend.extraction.section_extractor import SectionExtractor
from backend.services.export_service import ExportService
from backend.services.scanner_service import scanner_service, normalize_product_name

router = APIRouter(prefix="/api/v1", tags=["Client Products API"])


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-KEY")):
    """
    Validates the X-API-KEY header if API_KEY is configured in the environment.
    If no API_KEY is configured, requests are allowed freely.
    """
    if API_KEY:
        if not x_api_key or x_api_key.strip() != API_KEY.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-API-KEY header. Access denied.",
                headers={"WWW-Authenticate": "ApiKey"},
            )
    return True


class ProductQueryRequest(BaseModel):
    product_name: str = Field(..., description="Medicine or product name to search for (e.g. 'Lipitor', 'Ozempic')")
    section: Optional[str] = Field("16", description="Section number (default '16') or subsection (e.g. '16.1')")
    subsection: Optional[str] = Field(None, description="Optional target subsection (e.g. '16.1', '16.2')")
    format: Optional[str] = Field("json", description="Response format: 'json' or 'html'")
    embed_only: bool = Field(False, description="If format=html and embed_only=True, returns embeddable snippet without <html><body>")
    include_tables: bool = Field(True, description="Whether to include structured tables in the response")
    include_html: bool = Field(True, description="Whether to include rendered HTML in the response")


def find_product_record(db: Session, raw_query: str) -> Optional[ProductSectionRecord]:
    """
    Multi-stage intelligent search for matching product records:
    1. Exact match on product_name (case-insensitive)
    2. Exact match on product_normalized
    3. Exact match on filename (without extension)
    4. Substring/prefix match on product_normalized
    5. Substring match on filename
    """
    clean_query = raw_query.strip()
    norm_query = normalize_product_name(clean_query)

    # 1. Exact case-insensitive match on product_name
    record = (
        db.query(ProductSectionRecord)
        .filter(func.lower(ProductSectionRecord.product_name) == clean_query.lower())
        .order_by(ProductSectionRecord.updated_at.desc())
        .first()
    )
    if record:
        return record

    # 2. Match on normalized product name
    if norm_query:
        record = (
            db.query(ProductSectionRecord)
            .filter(ProductSectionRecord.product_normalized == norm_query)
            .order_by(ProductSectionRecord.updated_at.desc())
            .first()
        )
        if record:
            return record

    # 3. Match on filename
    record = (
        db.query(ProductSectionRecord)
        .filter(
            or_(
                func.lower(ProductSectionRecord.filename) == clean_query.lower(),
                func.lower(ProductSectionRecord.filename) == f"{clean_query.lower()}.pdf",
            )
        )
        .order_by(ProductSectionRecord.updated_at.desc())
        .first()
    )
    if record:
        return record

    # 4. Prefix or substring match on normalized name
    if norm_query and len(norm_query) >= 3:
        record = (
            db.query(ProductSectionRecord)
            .filter(ProductSectionRecord.product_normalized.like(f"%{norm_query}%"))
            .order_by(ProductSectionRecord.updated_at.desc())
            .first()
        )
        if record:
            return record

    # 5. Substring match on filename
    if len(clean_query) >= 3:
        record = (
            db.query(ProductSectionRecord)
            .filter(ProductSectionRecord.filename.ilike(f"%{clean_query}%"))
            .order_by(ProductSectionRecord.updated_at.desc())
            .first()
        )
        if record:
            return record

    return None


def extract_html_snippet(full_html: str) -> str:
    """Extracts the <section>...</section> container snippet from a full HTML document."""
    if not full_html:
        return ""
    match = re.search(r'(<section[\s\S]*?</section>)', full_html, re.IGNORECASE)
    if match:
        return match.group(1)
    # If no section tag found, extract body contents
    body_match = re.search(r'<body[^>]*>([\s\S]*?)</body>', full_html, re.IGNORECASE)
    if body_match:
        return body_match.group(1).strip()
    return full_html


def format_product_response(
    record: ProductSectionRecord,
    target_subsection: Optional[str] = None,
    format_type: str = "json",
    embed_only: bool = False,
) -> Dict[str, Any]:
    """
    Formats a database ProductSectionRecord into a structured client-facing payload.
    If target_subsection is provided (e.g. '16.1'), filters strictly to that subsection.
    """
    tables = []
    if record.tables_json:
        try:
            tables = json.loads(record.tables_json)
        except Exception:
            tables = []

    subsections = []
    if record.subsections_json:
        try:
            subsections = json.loads(record.subsections_json)
        except Exception:
            subsections = []

    # Handle subsection-specific request (e.g. "16.1")
    if target_subsection:
        clean_sub = target_subsection.strip()
        matched_sub = None
        for item in subsections:
            if isinstance(item, dict) and item.get("subsection_number") == clean_sub:
                matched_sub = item
                break

        # If found in cached structured subsections
        if matched_sub:
            sub_snippet = matched_sub.get("html_snippet", "")
            sub_full_html = ExportService.generate_structured_html(
                result=SectionExtractor().extract(
                    file_path_or_bytes=Path(record.file_path),
                    main_section="16",
                    target_subsection=clean_sub,
                    doc_name=record.filename,
                ) if Path(record.file_path).exists() else None,
                product_name=record.product_name,
                target_subsection=clean_sub,
                standalone=True,
            ) if Path(record.file_path).exists() else f"<!DOCTYPE html><html><body>{sub_snippet}</body></html>"

            return {
                "status": "success",
                "product_name": record.product_name,
                "target_section": record.target_section,
                "target_subsection": clean_sub,
                "section_title": matched_sub.get("title", f"Section {clean_sub}"),
                "source_document": record.filename,
                "total_pages": record.total_pages,
                "pages": {
                    "start": record.start_page,
                    "end": record.end_page,
                },
                "extraction_status": "success",
                "confidence_score": record.confidence_score,
                "last_updated": record.updated_at.isoformat() if record.updated_at else record.created_at.isoformat(),
                "data": {
                    "text": matched_sub.get("text", ""),
                    "tables": matched_sub.get("tables", []),
                    "subsections": [clean_sub],
                    "html": sub_full_html,
                    "html_snippet": sub_snippet,
                },
            }

        # If not cached, extract on-the-fly if source PDF is available
        file_p = Path(record.file_path)
        if file_p.exists():
            extractor = SectionExtractor()
            res = extractor.extract(
                file_path_or_bytes=file_p,
                main_section=record.target_section,
                target_subsection=clean_sub,
                doc_name=record.filename,
            )
            if res.status == "success":
                full_html = ExportService.generate_structured_html(
                    res, product_name=record.product_name, target_subsection=clean_sub, standalone=True
                )
                snippet = ExportService.generate_structured_html(
                    res, product_name=record.product_name, target_subsection=clean_sub, standalone=False
                )
                sub_tables = []
                for blk in res.blocks:
                    if getattr(blk, "block_type", "") == "table":
                        sub_tables.append({
                            "id": blk.id,
                            "page": blk.page,
                            "columns": getattr(blk, "table_columns", None) or [],
                            "rows": getattr(blk, "table_rows", None) or [],
                            "markdown": getattr(blk, "table_markdown", "") or "",
                        })

                # Determine subsection heading
                sub_title = f"Section {clean_sub}"
                for blk in res.blocks:
                    if getattr(blk, "block_type", "") == "heading" and blk.section == clean_sub:
                        sub_title = blk.text
                        break

                return {
                    "status": "success",
                    "product_name": record.product_name,
                    "target_section": record.target_section,
                    "target_subsection": clean_sub,
                    "section_title": sub_title,
                    "source_document": record.filename,
                    "total_pages": record.total_pages,
                    "pages": {
                        "start": res.start_page,
                        "end": res.end_page,
                    },
                    "extraction_status": "success",
                    "confidence_score": getattr(res.validation, "confidence_score", 1.0),
                    "last_updated": record.updated_at.isoformat() if record.updated_at else record.created_at.isoformat(),
                    "data": {
                        "text": res.content,
                        "tables": sub_tables,
                        "subsections": [clean_sub],
                        "html": full_html,
                        "html_snippet": snippet,
                    },
                }

    # Full Section 16 response
    full_html = record.extracted_html or ""
    html_snippet = extract_html_snippet(full_html)

    return {
        "status": "success",
        "product_name": record.product_name,
        "target_section": record.target_section,
        "target_subsection": None,
        "section_title": record.section_title or f"Section {record.target_section}",
        "source_document": record.filename,
        "total_pages": record.total_pages,
        "pages": {
            "start": record.start_page,
            "end": record.end_page,
        },
        "extraction_status": record.status,
        "confidence_score": record.confidence_score,
        "last_updated": record.updated_at.isoformat() if record.updated_at else record.created_at.isoformat(),
        "data": {
            "text": record.extracted_text or "",
            "tables": tables,
            "subsections": subsections,
            "html": full_html,
            "html_snippet": html_snippet,
        },
    }


@router.get("/products/section-16", summary="Fetch Section 16 or 16.1 structured data for a specified product")
async def get_product_section_16(
    product_name: str = Query(..., description="Brand name or medicine name (e.g. 'Lipitor')"),
    subsection: Optional[str] = Query(None, description="Optional target subsection, e.g. '16.1' or '16.2'"),
    section: Optional[str] = Query(None, description="Alternative: '16' or '16.1'"),
    format: Optional[str] = Query("json", description="Output format: 'json' or 'html'"),
    embed_only: bool = Query(False, description="If format=html and embed_only=True, returns embeddable snippet without <html><body>"),
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_api_key),
):
    """
    **Primary Client API Endpoint**:
    Returns pre-extracted Section 16 or subsection 16.1 data in proper structured HTML5 and JSON.
    Results are returned instantly (<15ms) directly from the database without parsing PDFs on-the-fly.
    
    Supports:
    - Entire Section 16: `?product_name=Lipitor`
    - Specific Subsection 16.1: `?product_name=Lipitor&subsection=16.1`
    - Standalone HTML page: `?product_name=Lipitor&format=html`
    - Embeddable HTML snippet: `?product_name=Lipitor&format=html&embed_only=true`
    """
    record = find_product_record(db, product_name)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "status": "not_found",
                "message": f"No extracted data found for product '{product_name}'.",
                "suggestion": "Verify product spelling or ensure the PDF is in the watch folder.",
            },
        )

    # Determine target subsection (e.g. "16.1" or from section parameter)
    target_sub = subsection
    if not target_sub and section and section != "16":
        target_sub = section

    resp_data = format_product_response(
        record=record,
        target_subsection=target_sub,
        format_type=format,
        embed_only=embed_only,
    )

    # Return pure HTML if requested
    if format and format.lower() == "html":
        content_to_serve = resp_data["data"]["html_snippet"] if embed_only else resp_data["data"]["html"]
        if not content_to_serve:
            content_to_serve = f"<section class='med-section-container'><p>{resp_data['data']['text']}</p></section>"
        return HTMLResponse(content=content_to_serve, media_type="text/html")

    return resp_data


@router.post("/products/section-16", summary="Fetch Section 16 data via POST JSON body")
async def post_product_section_16(
    req: ProductQueryRequest,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_api_key),
):
    """POST alternative for clients querying with a JSON payload."""
    record = find_product_record(db, req.product_name)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "status": "not_found",
                "message": f"No extracted data found for product '{req.product_name}'.",
            },
        )

    target_sub = req.subsection
    if not target_sub and req.section and req.section != "16":
        target_sub = req.section

    resp_data = format_product_response(
        record=record,
        target_subsection=target_sub,
        format_type=req.format or "json",
        embed_only=req.embed_only,
    )

    if req.format and req.format.lower() == "html":
        content_to_serve = resp_data["data"]["html_snippet"] if req.embed_only else resp_data["data"]["html"]
        return HTMLResponse(content=content_to_serve, media_type="text/html")

    return resp_data


@router.get("/products/search", summary="Search available indexed products")
async def search_products(
    query: str = Query(..., min_length=2, description="Search term for product name or filename"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_api_key),
):
    """Enables autocomplete and fuzzy product searches for client search bars."""
    norm_q = normalize_product_name(query)
    records = (
        db.query(ProductSectionRecord)
        .filter(
            or_(
                ProductSectionRecord.product_normalized.like(f"%{norm_q}%"),
                ProductSectionRecord.filename.ilike(f"%{query}%"),
            )
        )
        .order_by(ProductSectionRecord.product_name.asc())
        .limit(limit)
        .all()
    )

    results = []
    for r in records:
        results.append({
            "product_name": r.product_name,
            "filename": r.filename,
            "section": r.target_section,
            "section_title": r.section_title,
            "status": r.status,
            "has_tables": bool(r.tables_json and r.tables_json != "[]"),
            "last_updated": r.updated_at.isoformat() if r.updated_at else None,
        })

    return {
        "status": "success",
        "query": query,
        "count": len(results),
        "results": results,
    }


@router.get("/products/list", summary="List all indexed products (paginated)")
async def list_all_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_api_key),
):
    """Returns a paginated list of all indexed products and their Section 16 status."""
    total = db.query(ProductSectionRecord).count()
    offset = (page - 1) * page_size
    records = (
        db.query(ProductSectionRecord)
        .order_by(ProductSectionRecord.product_name.asc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items = []
    for r in records:
        items.append({
            "product_name": r.product_name,
            "filename": r.filename,
            "total_pages": r.total_pages,
            "section": r.target_section,
            "status": r.status,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })

    return {
        "status": "success",
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        "products": items,
    }


@router.post("/scanner/trigger", summary="Manually trigger an immediate folder scan")
async def trigger_scan(
    _auth: bool = Depends(verify_api_key),
):
    """
    Allows on-demand trigger of the 30-minute folder scanner.
    Useful after dumping new PDFs into the watch folder without waiting for the next 30-minute timer.
    """
    stats = await scanner_service.scan_once_async()
    return {
        "status": "success",
        "message": "Scan completed successfully",
        "stats": stats,
    }


@router.get("/scanner/status", summary="Get scanner health and operational metrics")
async def get_scanner_status(
    _auth: bool = Depends(verify_api_key),
):
    """Returns scanner health, watch directory, and next scheduled scan time."""
    return scanner_service.get_status()
