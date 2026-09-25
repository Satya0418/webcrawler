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


def strip_markdown_tables(text: str) -> str:
    """Strips [Page X Table] captions and pipe table markdown blocks from extracted text."""
    if not text:
        return ""
    text = re.sub(r'\[Page\s+\d+\s+Table\][\s\S]*?(?=\n\n|\Z)', '', text)
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        s = line.strip()
        if s.startswith('|') and s.endswith('|'):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned).strip()


def strip_html_tables(html_str: str) -> str:
    """Completely strips <table> and wrapper <div class="table-responsive"> elements from HTML."""
    if not html_str:
        return ""
    cleaned = re.sub(r'<div class="table-responsive"[\s\S]*?</div>\s*', '', html_str, flags=re.IGNORECASE)
    cleaned = re.sub(r'<table[\s\S]*?</table>\s*', '', cleaned, flags=re.IGNORECASE)
    return cleaned


def format_product_response(
    record: ProductSectionRecord,
    target_subsection: Optional[str] = None,
    format_type: str = "json",
    embed_only: bool = False,
    include_tables: bool = False,
) -> Dict[str, Any]:
    """
    Formats a database ProductSectionRecord into a structured client-facing payload.
    If target_subsection is provided (e.g. '16.1'), filters strictly to that subsection.
    When include_tables is False, completely omits tables, table rows, and renders text-only paragraphs.
    """
    tables = []
    if include_tables and record.tables_json:
        try:
            tables = json.loads(record.tables_json)
        except Exception:
            tables = []

    subsections = []
    if record.subsections_json:
        try:
            raw_subs = json.loads(record.subsections_json)
            for sub in raw_subs:
                if isinstance(sub, dict):
                    item_copy = dict(sub)
                    if not include_tables:
                        item_copy["tables"] = []
                        item_copy["text"] = strip_markdown_tables(item_copy.get("text", ""))
                        item_copy["html_snippet"] = strip_html_tables(item_copy.get("html_snippet", ""))
                    subsections.append(item_copy)
        except Exception:
            subsections = []

    # Handle subsection-specific request (e.g. "16.1")
    if target_subsection:
        clean_sub = target_subsection.strip()
        file_p = Path(record.file_path) if record.file_path else None

        # If source PDF is available, extract precise subsection on-the-fly according to table mode
        if file_p and file_p.exists():
            extractor = SectionExtractor()
            res = extractor.extract(
                file_path_or_bytes=file_p,
                main_section=record.target_section,
                target_subsection=clean_sub,
                doc_name=record.filename,
                include_tables=include_tables,
            )
            if res.status == "success":
                full_html = ExportService.generate_structured_html(
                    res,
                    product_name=record.product_name,
                    target_subsection=clean_sub,
                    standalone=True,
                    include_tables=include_tables,
                )
                snippet = ExportService.generate_structured_html(
                    res,
                    product_name=record.product_name,
                    target_subsection=clean_sub,
                    standalone=False,
                    include_tables=include_tables,
                )
                sub_tables = []
                if include_tables:
                    for blk in res.blocks:
                        if getattr(blk, "block_type", "") == "table":
                            sub_tables.append({
                                "id": blk.id,
                                "page": blk.page,
                                "columns": getattr(blk, "table_columns", None) or [],
                                "rows": getattr(blk, "table_rows", None) or [],
                                "markdown": getattr(blk, "table_markdown", "") or "",
                            })

                sub_title = f"Section {clean_sub}"
                for blk in res.blocks:
                    if getattr(blk, "block_type", "") == "heading" and blk.section == clean_sub:
                        sub_title = blk.text
                        break

                clean_text = strip_markdown_tables(res.content) if not include_tables else res.content

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
                    "Data": full_html,
                    "data": {
                        "text": clean_text,
                        "tables": sub_tables,
                        "subsections": [clean_sub],
                        "html": full_html,
                        "html_snippet": snippet,
                    },
                }

        # Fallback to cached subsections if PDF is not locally reachable
        matched_sub = None
        for item in subsections:
            if isinstance(item, dict) and item.get("subsection_number") == clean_sub:
                matched_sub = item
                break

        if matched_sub:
            sub_snippet = matched_sub.get("html_snippet", "")
            if not include_tables:
                sub_snippet = strip_html_tables(sub_snippet)
            sub_full_html = f"<!DOCTYPE html><html><body>{sub_snippet}</body></html>"
            sub_text = matched_sub.get("text", "")
            if not include_tables:
                sub_text = strip_markdown_tables(sub_text)

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
                "Data": sub_full_html,
                "data": {
                    "text": sub_text,
                    "tables": matched_sub.get("tables", []) if include_tables else [],
                    "subsections": [clean_sub],
                    "html": sub_full_html,
                    "html_snippet": sub_snippet,
                },
            }

    # Full Section response
    full_html = record.extracted_html or ""
    if not include_tables:
        full_html = strip_html_tables(full_html)
    html_snippet = extract_html_snippet(full_html)

    clean_full_text = record.extracted_text or ""
    if not include_tables:
        clean_full_text = strip_markdown_tables(clean_full_text)

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
        "Data": full_html,
        "data": {
            "text": clean_full_text,
            "tables": tables if include_tables else [],
            "subsections": subsections,
            "html": full_html,
            "html_snippet": html_snippet,
        },
    }


@router.get("/products/section-16", summary="Fetch Section 16 or 16.1 structured data for a specified product")
async def get_product_section_16(
    product_name: str = Query(..., description="Brand name or medicine name (e.g. 'Lipitor', 'Ofloxacin')"),
    subsection: Optional[str] = Query(None, description="Optional target subsection, e.g. '16.1' or '16.2'"),
    section: Optional[str] = Query(None, description="Alternative: '16' or '16.1'"),
    format: Optional[str] = Query("json", description="Output format: 'json', 'html', or 'data'"),
    response_format: Optional[str] = Query(None, description="Alternative format selector e.g. 'html' or 'data'"),
    embed_only: bool = Query(False, description="If format=html and embed_only=True, returns embeddable snippet without <html><body>"),
    include_tables: bool = Query(False, description="Whether to include clinical tables. Defaults to False (neglect tables, text only)"),
    table_mode: Optional[str] = Query(None, description="Table mode: 'neglect' (default, omit tables) or 'add' (include tables)"),
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_api_key),
):
    """
    **Primary Client API Endpoint**:
    Returns pre-extracted Section 16 or subsection 16.1 data in proper structured HTML5 and JSON.
    By default, neglects tables (text only) as per client specification.
    
    Supports:
    - Entire Section 16: `?product_name=Lipitor`
    - Specific Subsection 16.1: `?product_name=Lipitor&subsection=16.1`
    - Neglect tables (default): `?product_name=Ofloxacin&subsection=16.1` (or `&include_tables=false` / `&table_mode=neglect`)
    - Include tables (optional): `?product_name=Ofloxacin&include_tables=true` (or `&table_mode=add`)
    - Standalone HTML page: `?product_name=Lipitor&format=html`
    - HTML Table ("Data"): `?product_name=Lipitor&format=data` -> returns `{"Data": "<!DOCTYPE html>..."}`
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

    # Determine table mode
    effective_include_tables = False
    if isinstance(table_mode, str):
        effective_include_tables = (table_mode.lower() == "add")
    elif isinstance(include_tables, bool):
        effective_include_tables = include_tables

    raw_format = response_format if isinstance(response_format, str) else (format if isinstance(format, str) else "json")
    effective_format = raw_format.lower()

    resp_data = format_product_response(
        record=record,
        target_subsection=target_sub,
        format_type=effective_format,
        embed_only=embed_only,
        include_tables=effective_include_tables,
    )

    # Return pure HTML if requested
    if effective_format == "html":
        content_to_serve = resp_data["data"]["html_snippet"] if embed_only else resp_data["data"]["html"]
        if not content_to_serve:
            content_to_serve = f"<section class='med-section-container'><p>{resp_data['data']['text']}</p></section>"
        return HTMLResponse(content=content_to_serve, media_type="text/html")

    # If client specifically requested "Data" format (like in the UI option "HTML Table ('Data')")
    if effective_format == "data":
        return {"Data": resp_data.get("Data") or resp_data["data"]["html"]}

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

    effective_include_tables = req.include_tables if req.include_tables is not None else False

    resp_data = format_product_response(
        record=record,
        target_subsection=target_sub,
        format_type=req.format or "json",
        embed_only=req.embed_only,
        include_tables=effective_include_tables,
    )

    if req.format and req.format.lower() == "html":
        content_to_serve = resp_data["data"]["html_snippet"] if req.embed_only else resp_data["data"]["html"]
        return HTMLResponse(content=content_to_serve, media_type="text/html")

    if req.format and req.format.lower() == "data":
        return {"Data": resp_data.get("Data") or resp_data["data"]["html"]}

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
    folder_path: Optional[str] = Query(None, description="Optional folder path to scan on-demand (e.g. '/Users/satya/Desktop/Medical')"),
    _auth: bool = Depends(verify_api_key),
):
    """
    Allows on-demand trigger of the folder scanner.
    If folder_path is provided, immediately scans that directory and stores extracted sections into PostgreSQL.
    Otherwise scans all configured watch directories.
    """
    custom_dir = Path(folder_path).expanduser().resolve() if folder_path else None
    if custom_dir and not custom_dir.exists():
        raise HTTPException(status_code=404, detail=f"Directory '{folder_path}' does not exist.")

    stats = await scanner_service.scan_once_async(custom_dir=custom_dir)
    return {
        "status": "success",
        "message": "Scan completed successfully",
        "scanned_directory": str(custom_dir) if custom_dir else [str(d) for d in scanner_service.watch_dirs],
        "stats": stats,
    }


@router.get("/scanner/status", summary="Get scanner health and operational metrics")
async def get_scanner_status(
    _auth: bool = Depends(verify_api_key),
):
    """Returns scanner health, watch directory, and next scheduled scan time."""
    return scanner_service.get_status()
