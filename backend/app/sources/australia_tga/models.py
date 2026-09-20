"""
Data models and typed structures for Australia TGA crawling and extraction pipeline.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TGASearchResult(BaseModel):
    """Represents an individual item parsed from TGA search results."""
    title: str
    url: str
    snippet: str = ""
    date_str: Optional[str] = None
    source_date: Optional[datetime] = None
    artg_number: Optional[str] = None
    active_ingredient: Optional[str] = None
    is_relevant: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TGAProductPage(BaseModel):
    """Represents a discovered product page with metadata and document links."""
    product_name: str
    active_ingredient: Optional[str] = None
    sponsor: Optional[str] = "Australian Sponsor (TGA Registered)"
    application_number: Optional[str] = None  # e.g. AUST R 47485
    dosage_form: Optional[str] = "Therapeutic Good (Australia)"
    source_url: str
    pi_links: List[str] = Field(default_factory=list)
    cmi_links: List[str] = Field(default_factory=list)
    html_content: Optional[str] = None


class TGAPIDocument(BaseModel):
    """Represents a discovered Product Information document candidate."""
    title: str
    pdf_url: str
    source_url: Optional[str] = None
    document_date: Optional[datetime] = None
    revision_date: Optional[datetime] = None
    effective_date: Optional[datetime] = None
    version_str: Optional[str] = None
    version_number: Optional[float] = None
    document_number: Optional[str] = None
    page_count: Optional[int] = None
    retrieved_date: datetime = Field(default_factory=datetime.utcnow)
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)


class ExtractedTable(BaseModel):
    """Represents a structured table extracted from Section 4.8."""
    caption: str = ""
    page: int = 0
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    raw_rows: List[List[str]] = Field(default_factory=list)
    markdown: str = ""
    footnotes: List[str] = Field(default_factory=list)


class ExtractedSection(BaseModel):
    """Represents an extracted regulatory section (4.6 or 4.8)."""
    section_number: str  # "4.6" or "4.8"
    title: str
    start_page: int = 0
    end_page: int = 0
    pages_str: str = ""
    text_content: str = ""
    tables: List[ExtractedTable] = Field(default_factory=list)
    is_present: bool = True
    confidence: float = 1.0
    footnotes: List[str] = Field(default_factory=list)


class TGARegulatoryResult(BaseModel):
    """Conceptually harmonized final TGA regulatory result."""
    product_name: str
    active_ingredient: str
    application_number: str
    sponsor: str
    source: str = "AUSTRALIA_TGA"
    dosage_form: str = "Therapeutic Good (Australia)"
    document_title: str = "Product Information"
    document_date: Optional[str] = None
    revision_date: Optional[str] = None
    version: Optional[str] = None
    pdf_url: Optional[str] = None
    source_url: str
    retrieved_date: str
    section_4_6: ExtractedSection
    section_4_8: ExtractedSection
    content_hash: str
    validation_status: str = "VALID"
    errors: List[str] = Field(default_factory=list)
