import json
import re
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query, Header, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

import os
import logging
import httpx

from backend.config import API_KEY, SALESFORCE_CALLBACK_URL
try:
    from backend.config import CRAWLER_BACKEND_URL
except ImportError:
    CRAWLER_BACKEND_URL = os.getenv("CRAWLER_BACKEND_URL", "http://crawler_backend:8001").rstrip("/")
from backend.database.db import get_db
from backend.database.models import ProductSectionRecord
from backend.extraction.section_extractor import SectionExtractor
from backend.services.export_service import ExportService
from backend.services.scanner_service import scanner_service, normalize_product_name

logger = logging.getLogger("pdf_extractor.products")
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
    product_name: Optional[str] = Field(None, description="Medicine or product name to search for (e.g. 'Lipitor', 'Ozempic')")
    productName: Optional[str] = Field(None, description="Alternative camelCase product name")
    submissionId: Optional[str] = Field(None, description="Unique submission identifier (e.g. 'a0CAq00004acdq7MAA')")
    submission_id: Optional[str] = Field(None, description="Alternative submission identifier")
    callbackUrl: Optional[str] = Field(None, description="Callback webhook URL")
    callback_url: Optional[str] = Field(None, description="Callback webhook URL")
    section: Optional[str] = Field("16", description="Section number (default '16') or subsection (e.g. '16.1')")
    subsection: Optional[str] = Field(None, description="Optional target subsection (e.g. '16.1', '16.2')")
    format: Optional[str] = Field("json", description="Response format: 'json' or 'html'")
    embed_only: bool = Field(False, description="If format=html and embed_only=True, returns embeddable snippet without <html><body>")
    include_tables: bool = Field(True, description="Whether to include structured tables in the response")
    include_html: bool = Field(True, description="Whether to include rendered HTML in the response")

    model_config = ConfigDict(extra="ignore")


DATE_REGEX_DMY = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")
DATE_REGEX_SLASH = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
DATE_REGEX_YMD = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")


def validate_client_date_range(
    start_date_val: Optional[Any],
    end_date_val: Optional[Any],
):
    """
    Standardizes and validates client dates in DD-MM-YYYY, MM/DD/YYYY, or ISO/YYYY-MM-DD format.
    Rejects malformed, ambiguous, or invalid calendar dates with HTTP 422.
    Rejects startDate > endDate with HTTP 422.
    Returns (start_dt, end_dt, start_str, end_str).
    """
    s_clean_pre = str(start_date_val).split("T")[0].strip() if start_date_val else ""
    e_clean_pre = str(end_date_val).split("T")[0].strip() if end_date_val else ""
    s_m_dmy = DATE_REGEX_DMY.match(s_clean_pre)
    e_m_dmy = DATE_REGEX_DMY.match(e_clean_pre)
    force_mm_dd = False
    if s_m_dmy and e_m_dmy:
        s_p1, s_p2 = int(s_m_dmy.group(1)), int(s_m_dmy.group(2))
        e_p1, e_p2 = int(e_m_dmy.group(1)), int(e_m_dmy.group(2))
        if s_p1 <= 12 and s_p2 <= 12 and e_p1 <= 12 and e_p2 <= 12:
            if s_p1 == e_p1 and s_p2 <= e_p2:
                force_mm_dd = True

    def _parse(val: Optional[Any], name: str) -> Optional[datetime]:
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None
        s_clean = s.split("T")[0].strip() if "T" in s else s
        m_dmy = DATE_REGEX_DMY.match(s_clean)
        m_slash = DATE_REGEX_SLASH.match(s_clean)
        m_ymd = DATE_REGEX_YMD.match(s_clean)

        if m_dmy:
            p1, p2, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
            if p1 > 12 and p2 <= 12:
                d, mth = p1, p2
            elif p2 > 12 and p1 <= 12:
                mth, d = p1, p2
            elif force_mm_dd:
                mth, d = p1, p2
            else:
                d, mth = p1, p2
        elif m_slash:
            p1, p2, y = int(m_slash.group(1)), int(m_slash.group(2)), int(m_slash.group(3))
            if p2 > 12 and p1 <= 12:
                mth, d = p1, p2  # e.g. 02/21/2024 -> month=2, day=21
            elif p1 > 12 and p2 <= 12:
                d, mth = p1, p2  # e.g. 21/02/2024 -> day=21, month=2
            else:
                mth, d = p1, p2  # Default to MM/DD/YYYY for slashes (FDA SrLC table format)
        elif m_ymd:
            y, mth, d = int(m_ymd.group(1)), int(m_ymd.group(2)), int(m_ymd.group(3))
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid date format for '{name}': '{s}'. Expected DD-MM-YYYY (e.g. '01-01-2025'), MM/DD/YYYY, or YYYY-MM-DD.",
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


class WebsiteDataItem(BaseModel):
    website_Name: str = Field("FDA_details", description="Website identifier e.g. 'FDA_details' or 'TGA_details'")
    title: str = Field("Website Safety Data", description="Title identifier")
    productName: str = Field(..., description="Matched product or medicine name")
    genericName: Optional[str] = Field("", description="Generic name or active ingredient description")
    activeIngredients: Optional[str] = Field("", description="Active ingredients")
    startDate: Optional[str] = Field("", description="Applied start date filter in DD-MM-YYYY format")
    endDate: Optional[str] = Field("", description="Applied end date filter in DD-MM-YYYY format")
    Data: str = Field(..., description="Actual extracted website HTML content string")
    submissionId: Optional[str] = Field(None, description="Preserved submission identifier")


class WebsiteDataSection(BaseModel):
    title: str = Field("Safety Action Taken", description="Source identifier title: 'Safety Action Taken'")
    responseType: Optional[str] = Field("SafetyActionTaken", description="Response type category")
    status: str = Field("success", description="Status: 'success', 'not_found', or 'error'")
    coverage: Optional[str] = Field(None, description="Coverage assessment: 'complete' or 'partial'")
    source_limitation: Optional[str] = Field(None, description="Explanation if date range exceeds source coverage")
    data: List[WebsiteDataItem] = Field(default_factory=list, description="List of website safety results")
    message: Optional[str] = Field(None, description="Informational message or reason for no results")


class PdfExtractorDataSection(BaseModel):
    title: str = Field("Signal and Risk", description="Source identifier title: 'Signal and Risk'")
    responseType: Optional[str] = Field("SignalAndRisk", description="Response type category")
    status: str = Field("success", description="Status: 'success', 'not_found', or 'error'")
    data: Optional[Dict[str, Any]] = Field(None, description="Preserved structured PDF extractor response")
    message: Optional[str] = Field(None, description="Informational message or reason for no results")


class UnifiedClientResponse(BaseModel):
    submissionId: str = Field(..., description="Echo of received submissionId")
    productName: str = Field(..., description="Echo of requested product name")
    website_Data: WebsiteDataSection = Field(..., description="Independent results from website crawler")
    pdf_extractor_Data: PdfExtractorDataSection = Field(..., description="Independent results from PDF extractor")

    model_config = ConfigDict(extra="allow")


# Backward compatibility aliases
SignalAndRiskResponse = UnifiedClientResponse


class SignalAndRiskIntegrationRequest(BaseModel):
    submissionId: Optional[str] = Field(None, description="Unique submission identifier (e.g. 'a0CAq00004acdq7MAA')")
    productName: Optional[str] = Field(None, description="Medicine or product name to search for (e.g. 'ARIKAYCE KIT')")
    startDate: Optional[str] = Field(None, description="Start date filter in DD-MM-YYYY format (e.g. '01-01-2025')")
    endDate: Optional[str] = Field(None, description="End date filter in DD-MM-YYYY format (e.g. '01-01-2026')")
    genericName: Optional[str] = Field(None, description="Generic name filter")
    activeIngredients: Optional[str] = Field(None, description="Active ingredient(s) filter")

    # Snake-case and alternative aliases
    submission_id: Optional[str] = Field(None, description="Alternative snake_case submission identifier")
    product_name: Optional[str] = Field(None, description="Alternative snake_case product name")
    start_date: Optional[str] = Field(None, description="Alternative snake_case start date")
    end_date: Optional[str] = Field(None, description="Alternative snake_case end date")
    generic_name: Optional[str] = Field(None, description="Alternative snake_case generic name")
    active_ingredients: Optional[str] = Field(None, description="Alternative snake_case active ingredients")
    activeIngredient: Optional[str] = Field(None, description="Singular active ingredient alias")
    active_ingredient: Optional[str] = Field(None, description="Singular active ingredient alias")

    callbackUrl: Optional[str] = Field(None, description="Optional custom Salesforce callback webhook URL")
    callback_url: Optional[str] = Field(None, description="Optional custom Salesforce callback webhook URL")
    responseType: Optional[str] = Field(None, description="Custom responseType e.g. 'SafetyActionTaken'")
    response_type: Optional[str] = Field(None, description="Custom response_type e.g. 'SafetyActionTaken'")

    model_config = ConfigDict(extra="ignore")



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


HEADER_LINE_PATTERNS = [
    r'\[page\s+\d+(?:\s+table)?\]',
    r'(?:section\s+)?\d+(?:\.\d+)*\s*[:\-\.]?\s*(?:signal\s+(?:and|&)\s+risk\s+evaluation|summary\s+of\s+safety\s+concerns?|evaluation\s+of\s+(?:signals?|risks?)|signal\s+evaluation|characterization\s+of\s+risks?|effectiveness\s+of\s+risk\s+minimization|benefit-risk\s+balance|summary\s+of\s+safety\s+issues?).*',
    r'signal\s+(?:and|&)\s+risk\s+evaluation',
    r'summary\s+of\s+safety\s+concerns?',
    r'evaluation\s+of\s+(?:signals?|risks?)(?:\s+and\s+new\s+information)?',
    r'signal\s+evaluation',
    r'characterization\s+of\s+risks?',
    r'effectiveness\s+of\s+risk\s+minimization(?:\s+activities)?',
    r'summary\s+of\s+safety\s+issues?',
    r'benefit-risk\s+balance',
    r'periodic\s+(?:benefit-risk|safety\s+update)\s+(?:evaluation\s+)?report.*',
    r'pbrer.*',
    r'psur.*',
    r'apotex(?:\s+inc\.?)?.*',
    r'.*-\s*section\s+\d+.*',
    r'section\s+\d+(?:\.\d+)*',
    r'(?:section\s+)?\d+(?:\.\d+)*\s+[A-Za-z].*',
    r'(?:section\s+)?\d+(?:\.\d+)*$',
]
HEADER_LINE_REGEX = re.compile(r'^(?:' + '|'.join(HEADER_LINE_PATTERNS) + r')$', re.IGNORECASE)


def strip_html_headers(html_str: str) -> str:
    """
    Completely removes brand tag, section main title headers, subsection badge, subsection title,
    running headers, and paragraph titles like:
    'Signal and Risk Evaluation', 'Summary of Safety Concerns', 'Apotex Inc. Periodic Benefit-Risk...',
    'Amikacin - Section 16', 'Section 16.1', '16.1 Summary of Safety Concerns'.
    Preserves purely the body paragraphs and data.
    """
    if not html_str:
        return ""
    # Strip main header and brand tag
    cleaned = re.sub(r'<header class="med-main-header"[\s\S]*?</header>\s*', '', html_str, flags=re.IGNORECASE)
    cleaned = re.sub(r'<div class="med-brand-tag"[\s\S]*?</div>\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<h2 class="med-section-main-title"[\s\S]*?</h2>\s*', '', cleaned, flags=re.IGNORECASE)
    
    # Strip subsection header, badge, and subsection title
    cleaned = re.sub(r'<header class="med-sub-header"[\s\S]*?</header>\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<span class="med-badge"[\s\S]*?</span>\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<h3 class="med-subsection-title"[\s\S]*?</h3>\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<h4 class="med-subheading"[\s\S]*?</h4>\s*', '', cleaned, flags=re.IGNORECASE)
    
    # Strip any general h1-h4 tags
    cleaned = re.sub(r'<h[1-4][^>]*>[\s\S]*?</h[1-4]>\s*', '', cleaned, flags=re.IGNORECASE)
    # Strip header CSS rules from <style> blocks if present
    cleaned = re.sub(r'\.med-(?:main-header|brand-tag|section-main-title|sub-header|badge|subsection-title|subheading)\s*\{[^}]*\}\s*', '', cleaned, flags=re.IGNORECASE)
    # Normalize <title> so section headers are not in the browser title bar
    cleaned = re.sub(r'<title>[^<]*?(?:Section|\d+\.\d+)[^<]*?</title>', '<title>Extracted Document</title>', cleaned, flags=re.IGNORECASE)

    # Clean inner lines of <p> tags: strip header lines, Apotex running headers, or title banners
    def clean_p_content(match):
        p_tag_open = match.group(1)
        p_inner = match.group(2)
        lines = re.split(r'<br\s*/?>|\n', p_inner)
        surviving = []
        for l in lines:
            l_strip = re.sub(r'<[^>]+>', '', l).strip()
            if not l_strip:
                continue
            if HEADER_LINE_REGEX.match(l_strip):
                continue
            surviving.append(l.strip())
        if not surviving:
            return ""
        return f'{p_tag_open}\n        ' + '<br>\n        '.join(surviving) + '\n    </p>'

    cleaned = re.sub(r'(<p(?:\s+class="[^"]*")?>)([\s\S]*?)</p>', clean_p_content, cleaned, flags=re.IGNORECASE)

    # Clean empty articles, empty root divs, or empty wrappers
    cleaned = re.sub(r'<div class="med-root-content">\s*</div>\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<article[^>]*>\s*<div class="med-sub-body">\s*</div>\s*</article>\s*', '', cleaned, flags=re.IGNORECASE)
    return cleaned


def strip_text_headings(text: str) -> str:
    """
    Strips document headings, section titles, running headers, and page indicators from plain text,
    returning purely the body paragraphs.
    """
    if not text:
        return ""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        s = line.strip()
        if not s:
            cleaned.append("")
            continue
        s_unpaged = re.sub(r'^\[page\s+\d+(?:\s+table)?\]\s*', '', s, flags=re.IGNORECASE).strip()
        if not s_unpaged or HEADER_LINE_REGEX.match(s) or HEADER_LINE_REGEX.match(s_unpaged):
            continue
        cleaned.append(line)
    result = "\n".join(cleaned).strip()
    return re.sub(r'\n{3,}', '\n\n', result)


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
    Completely omits section headers, banners, and badges, returning only the extracted paragraph content.
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
                    item_copy["text"] = strip_text_headings(item_copy.get("text", ""))
                    item_copy["html_snippet"] = strip_html_headers(item_copy.get("html_snippet", ""))
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
                    include_headers=False,
                )
                full_html = strip_html_headers(full_html)
                snippet = ExportService.generate_structured_html(
                    res,
                    product_name=record.product_name,
                    target_subsection=clean_sub,
                    standalone=False,
                    include_tables=include_tables,
                    include_headers=False,
                )
                snippet = strip_html_headers(snippet)
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
                clean_text = strip_text_headings(clean_text)

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
            sub_snippet = strip_html_headers(sub_snippet)
            sub_full_html = f"<!DOCTYPE html><html><body>{sub_snippet}</body></html>"
            sub_text = matched_sub.get("text", "")
            if not include_tables:
                sub_text = strip_markdown_tables(sub_text)
            sub_text = strip_text_headings(sub_text)

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
    full_html = strip_html_headers(full_html)
    html_snippet = extract_html_snippet(full_html)

    clean_full_text = record.extracted_text or ""
    if not include_tables:
        clean_full_text = strip_markdown_tables(clean_full_text)
    clean_full_text = strip_text_headings(clean_full_text)

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
    target_name = (req.product_name or req.productName or "").strip()
    if not target_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'product_name' or 'productName' is required in request body.",
        )
    record = find_product_record(db, target_name)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "status": "not_found",
                "message": f"No extracted data found for product '{target_name}'.",
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

    sub_id = (req.submissionId or req.submission_id or "").strip()
    if sub_id:
        raw_html = resp_data.get("Data") or (resp_data.get("data") or {}).get("html") or ""
        clean_html = strip_html_tables(raw_html) if raw_html else ""
        pdf_signal_payload = {
            "responseType": "SignalAndRisk",
            "submissionId": sub_id,
            "productName": record.product_name or target_name,
            "responseData": [
                {
                    "productName": record.product_name or target_name,
                    "title": "summary_of_safety_concerns",
                    "Data": clean_html,
                }
            ],
        }
        target_cb = (req.callbackUrl or req.callback_url or SALESFORCE_CALLBACK_URL or "").strip()
        if target_cb and target_cb.lower() not in ("none", "skip", "disabled", "false"):
            await send_salesforce_callback(pdf_signal_payload, target_cb)
        return pdf_signal_payload

    return resp_data


async def send_salesforce_callback(payload: dict, callback_url: Optional[str] = None) -> dict:
    """
    Dispatches the extracted Section 16 Signal and Risk payload to the Salesforce
    Apex REST webhook endpoint (updateSubmissionResponse).
    """
    target_url = (callback_url or SALESFORCE_CALLBACK_URL or "").strip()
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


async def fetch_crawler_safety_data(
    product_name: str,
    submission_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    generic_name: Optional[str] = None,
    active_ingredients: Optional[str] = None,
    timeout_seconds: float = 15.0,
) -> Dict[str, Any]:
    """
    Queries the sibling medicine crawler backend service for live or indexed FDA safety labeling data.
    Propagates date range, genericName, and activeIngredients.
    Returns a dict with 'status': 'success' | 'not_found' | 'error',
    and on success, 'item': dict.
    """
    candidates = [CRAWLER_BACKEND_URL]
    if "crawler_backend" in CRAWLER_BACKEND_URL:
        candidates.append("http://127.0.0.1:8001")
        candidates.append("http://localhost:8001")

    payload = {
        "submissionId": submission_id,
        "productName": product_name,
        "startDate": start_date or "",
        "endDate": end_date or "",
        "genericName": generic_name or "",
        "activeIngredients": active_ingredients or "",
        "callbackUrl": "skip",  # prevent crawler from sending duplicate callback
    }

    last_error = None
    for base_url in candidates:
        endpoint = f"{base_url.rstrip('/')}/api/drugs/signal-and-risk"
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    # Check website_Data first
                    if isinstance(data.get("website_Data"), dict) and data["website_Data"].get("data"):
                        items = data["website_Data"]["data"]
                        if items and isinstance(items, list):
                            return {
                                "status": "success",
                                "item": items[0],
                                "coverage": data["website_Data"].get("coverage"),
                                "source_limitation": data["website_Data"].get("source_limitation"),
                            }
                    # Fallback to responseData
                    resp_items = data.get("responseData") or []
                    if resp_items and isinstance(resp_items, list):
                        item = resp_items[0]
                        if item.get("website_Data") or item.get("Data"):
                            return {
                                "status": "success",
                                "item": {
                                    "website_Name": item.get("website_Name") or "FDA_details",
                                    "title": "Website Safety Data",
                                    "productName": item.get("productName") or product_name,
                                    "genericName": item.get("genericName") or generic_name or "",
                                    "activeIngredients": item.get("activeIngredients") or active_ingredients or "",
                                    "startDate": item.get("startDate") or start_date or "",
                                    "endDate": item.get("endDate") or end_date or "",
                                    "Data": item.get("Data") or item.get("website_Data") or "",
                                    "submissionId": item.get("submissionId") or submission_id,
                                },
                            }
                elif resp.status_code == 404:
                    detail = ""
                    try:
                        detail = resp.json().get("detail", "")
                    except Exception:
                        pass
                    return {
                        "status": "not_found",
                        "message": detail or f"No website safety data found for product '{product_name}'.",
                    }
                elif resp.status_code == 422:
                    detail = ""
                    try:
                        detail = resp.json().get("detail", "")
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=422,
                        detail=detail or "Validation error in crawler date filtering.",
                    )
        except HTTPException:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            last_error = exc
            continue
        except Exception as exc:
            logger.warning("Error fetching crawler data from %s for '%s': %s", endpoint, product_name, exc)
            last_error = exc
            return {"status": "error", "message": str(exc)}

    return {
        "status": "error",
        "message": f"Website crawler unavailable: {last_error}" if last_error else "Website crawler unavailable.",
    }


def extract_pdf_branch(db: Session, prod_name: str) -> Dict[str, Any]:
    """Extracts structured PDF Section 16 data for the requested product."""
    record = find_product_record(db, prod_name)
    if record and record.status == "success" and record.extracted_html and record.extracted_html.strip():
        resp_data = format_product_response(record=record, include_tables=False)
        return {
            "title": "Signal and Risk",
            "responseType": "SignalAndRisk",
            "status": "success",
            "data": resp_data,
            "product_name": record.product_name,
        }
    return {
        "title": "Signal and Risk",
        "responseType": "SignalAndRisk",
        "status": "not_found",
        "data": None,
        "product_name": None,
        "message": f"No indexed PDF Section 16 data found for product '{prod_name}'.",
    }


@router.post(
    "/products/signal-and-risk",
    response_model=Any,
    summary="Unified Client Integration: Fetch Website Crawler Data and PDF Extractor Data in one call",
)
@router.post(
    "/product/signal-and-risk",
    response_model=Any,
    include_in_schema=False,
)
@router.post(
    "/signal-and-risk",
    response_model=Any,
    summary="Unified Client Integration (short alias)",
)
async def post_signal_and_risk(
    req: SignalAndRiskIntegrationRequest,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_api_key),
):
    """
    **Unified Client API Endpoint**:
    Receives submissionId, productName, startDate, endDate, genericName, activeIngredients.
    Executes both subsystems independently:
    1. Website Crawler Data (live/indexed US FDA SrLC data filtered by date range and search terms)
    2. PDF Extractor Data (structured Section 16 data from indexed product documents)
    Returns one unified JSON response containing two separate, independent response objects:
    - website_Data
    - pdf_extractor_Data
    Dispatches outbound callback to Salesforce if configured.
    """
    # 1. Validate required fields
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

    # 2. Validate date range (format DD-MM-YYYY, reject invalid or startDate > endDate with HTTP 422)
    raw_start = req.startDate if req.startDate is not None else req.start_date
    raw_end = req.endDate if req.endDate is not None else req.end_date
    start_dt, end_dt, start_str, end_str = validate_client_date_range(raw_start, raw_end)

    # 3. Extract generic name and active ingredients filters
    gen_name = (req.genericName or req.generic_name or "").strip() or None
    act_ingr = (
        req.activeIngredients
        or req.active_ingredients
        or req.activeIngredient
        or req.active_ingredient
        or ""
    ).strip() or None

    # 4. Execute PDF extractor branch
    pdf_info = extract_pdf_branch(db, prod_name)
    pdf_extractor_Data = {
        "title": "PDF Extractor Data",
        "status": pdf_info["status"],
        "data": pdf_info["data"],
    }
    if pdf_info.get("message"):
        pdf_extractor_Data["message"] = pdf_info["message"]

    # 5. Execute Website crawler branch
    try:
        crawler_res = await fetch_crawler_safety_data(
            product_name=prod_name,
            submission_id=sub_id,
            start_date=start_str,
            end_date=end_str,
            generic_name=gen_name,
            active_ingredients=act_ingr,
        )
    except TypeError:
        # Fallback for mocks or legacy functions taking only positional arguments
        try:
            crawler_res = await fetch_crawler_safety_data(prod_name, sub_id)
        except Exception as exc:
            crawler_res = {"status": "error", "message": str(exc)}
    except Exception as exc:
        crawler_res = {"status": "error", "message": str(exc)}

    if isinstance(crawler_res, dict) and crawler_res.get("status") == "success":
        website_item = crawler_res.get("item")
        if not website_item:
            website_item = {
                "website_Name": crawler_res.get("website_Name") or "FDA_details",
                "title": crawler_res.get("title") or "Website Safety Data",
                "productName": crawler_res.get("productName") or prod_name,
                "genericName": crawler_res.get("genericName") or gen_name or "",
                "activeIngredients": crawler_res.get("activeIngredients") or act_ingr or "",
                "startDate": crawler_res.get("startDate") or start_str,
                "endDate": crawler_res.get("endDate") or end_str,
                "Data": crawler_res.get("Data") or crawler_res.get("website_Data") or "",
                "submissionId": crawler_res.get("submissionId") or sub_id,
            }
        website_Data = {
            "title": "Safety Action Taken",
            "responseType": "SafetyActionTaken",
            "status": "success",
            "data": [website_item],
        }
        if crawler_res.get("coverage"):
            website_Data["coverage"] = crawler_res["coverage"]
        if crawler_res.get("source_limitation"):
            website_Data["source_limitation"] = crawler_res["source_limitation"]
    elif isinstance(crawler_res, dict) and (crawler_res.get("Data") or crawler_res.get("website_Data")):
        # Direct crawler item dict returned (e.g. from mock or legacy response)
        website_Data = {
            "title": "Safety Action Taken",
            "responseType": "SafetyActionTaken",
            "status": "success",
            "data": [
                {
                    "website_Name": crawler_res.get("website_Name") or "FDA_details",
                    "title": crawler_res.get("title") or "Website Safety Data",
                    "productName": crawler_res.get("productName") or prod_name,
                    "genericName": crawler_res.get("genericName") or gen_name or "",
                    "activeIngredients": crawler_res.get("activeIngredients") or act_ingr or "",
                    "startDate": crawler_res.get("startDate") or start_str,
                    "endDate": crawler_res.get("endDate") or end_str,
                    "Data": crawler_res.get("Data") or crawler_res.get("website_Data") or "",
                    "submissionId": crawler_res.get("submissionId") or sub_id,
                }
            ],
        }
    elif isinstance(crawler_res, dict) and crawler_res.get("status") == "not_found":
        website_Data = {
            "title": "Safety Action Taken",
            "responseType": "SafetyActionTaken",
            "status": "not_found",
            "data": [],
            "message": crawler_res.get("message") or f"No website safety data found for product '{prod_name}'.",
        }
    else:
        website_Data = {
            "title": "Safety Action Taken",
            "responseType": "SafetyActionTaken",
            "status": "error",
            "data": [],
            "message": crawler_res.get("message") if isinstance(crawler_res, dict) else "Website crawler service unavailable.",
        }

    # 6. Total failure check: if BOTH subsystems have no data, return HTTP 404
    pdf_ok = (pdf_extractor_Data["status"] == "success")
    website_ok = (website_Data["status"] == "success")
    if not pdf_ok and not website_ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No data found for product '{prod_name}' in either website crawler or PDF extractor.",
        )

    matched_product = (
        pdf_info.get("product_name")
        or (website_Data.get("data") and website_Data["data"][0].get("productName"))
        or prod_name
    )

    response_payload = {
        "submissionId": sub_id,
        "productName": matched_product,
        "website_Data": website_Data,
        "pdf_extractor_Data": pdf_extractor_Data,
    }

    # 7. Construct clean independent responses
    website_response = {
        "submissionId": sub_id,
        "responseType": "SafetyActionTaken",
        "responseData": [
            {
                "website_Name": item.get("website_Name") or "FDA_details",
                "website_Data": item.get("website_Data") or item.get("Data") or "",
            }
            for item in (website_Data.get("data") or [])
        ],
    }

    clean_pdf_html = ""
    if pdf_extractor_Data.get("status") == "success":
        pdf_cb_item = pdf_extractor_Data.get("data") or {}
        raw_html = pdf_cb_item.get("Data") or (pdf_cb_item.get("data") or {}).get("html") or ""
        clean_pdf_html = strip_html_tables(raw_html) if raw_html else ""

    pdf_response = {
        "responseType": "SignalAndRisk",
        "submissionId": sub_id,
        "productName": matched_product,
        "responseData": [
            {
                "productName": matched_product,
                "title": "summary_of_safety_concerns",
                "Data": clean_pdf_html,
            }
        ] if pdf_extractor_Data.get("status") == "success" else [],
    }

    # 8. Outbound callbacks to Salesforce updateSubmissionResponse webhook
    # Dispatches two separate HTTP POST calls as requested:
    #   Webhook Call #1: responseType "SafetyActionTaken" (Website Crawler data)
    #   Webhook Call #2: responseType "SignalAndRisk" (PDF Extractor data)
    target_callback = (req.callbackUrl or req.callback_url or SALESFORCE_CALLBACK_URL or "").strip()
    if target_callback and target_callback.lower() not in ("none", "skip", "disabled", "false"):
        # Webhook Call #1: Safety Action Taken (Website Crawler)
        if website_Data.get("status") == "success" or not pdf_extractor_Data.get("data"):
            await send_salesforce_callback(website_response, target_callback)

        # Webhook Call #2: Signal and Risk (PDF Extractor)
        if pdf_extractor_Data.get("status") == "success" or not website_Data.get("data"):
            await send_salesforce_callback(pdf_response, target_callback)

    req_format = (getattr(req, "format", None) or "").strip().lower()
    if req_format in ("dict", "unified", "merged"):
        return response_payload

    return [website_response, pdf_response]


@router.get(
    "/products/signal-and-risk",
    response_model=Any,
    summary="Fetch Section 16 Signal and Risk data via GET query for browser testing",
)
@router.get(
    "/product/signal-and-risk",
    response_model=Any,
    include_in_schema=False,
)
@router.get(
    "/signal-and-risk",
    response_model=Any,
    include_in_schema=False,
)
async def get_signal_and_risk(
    productName: Optional[str] = Query(None, description="Medicine or product name (e.g. 'amikacin')"),
    submissionId: Optional[str] = Query("browser_test", description="Submission identifier"),
    startDate: Optional[str] = Query(None, description="Start date filter in DD-MM-YYYY format"),
    endDate: Optional[str] = Query(None, description="End date filter in DD-MM-YYYY format"),
    genericName: Optional[str] = Query(None, description="Generic name filter"),
    activeIngredients: Optional[str] = Query(None, description="Active ingredient filter"),
    callbackUrl: Optional[str] = Query(None, description="Optional custom Salesforce callback webhook URL"),
    product_name: Optional[str] = Query(None, include_in_schema=False),
    submission_id: Optional[str] = Query(None, include_in_schema=False),
    start_date: Optional[str] = Query(None, include_in_schema=False),
    end_date: Optional[str] = Query(None, include_in_schema=False),
    generic_name: Optional[str] = Query(None, include_in_schema=False),
    active_ingredients: Optional[str] = Query(None, include_in_schema=False),
    callback_url: Optional[str] = Query(None, include_in_schema=False),
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_api_key),
):
    """
    Browser Testing Helper:
    Allows directly testing this endpoint in any web browser address bar with query parameters,
    e.g. /api/v1/products/signal-and-risk?productName=amikacin&startDate=01-01-2025&endDate=01-01-2026
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
            detail=(
                "Query parameter 'productName' is required. "
                "Example in browser: /api/v1/products/signal-and-risk?productName=amikacin"
            ),
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
        ),
        db=db,
        _auth=_auth,
    )


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
