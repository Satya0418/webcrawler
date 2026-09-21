"""
Data models for FDA MedWatch discovery and prescribing information extraction.
Enforces strict schema consistency, page-aware auditability, and traceability.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MedWatchArticle(BaseModel):
    """Represents an official FDA MedWatch safety alert, recall, or communication."""
    title: str
    url: str
    publication_date: Optional[str] = None
    product_name: Optional[str] = None
    active_ingredient: Optional[str] = None
    safety_topic: Optional[str] = None
    summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "publication_date": self.publication_date or "",
            "url": self.url,
            "product_name": self.product_name or "",
            "active_ingredient": self.active_ingredient or "",
            "safety_topic": self.safety_topic or "",
            "summary": self.summary or "",
        }


class ProductInfoLink(BaseModel):
    """Represents a discovered link to product information or direct prescribing info."""
    url: str
    link_text: str
    is_direct_pdf: bool = False
    source_page_url: str = ""
    discovery_type: str = "path_a_intermediate"  # "path_a_intermediate" or "path_b_direct"


class MedWatchDocumentInfo(BaseModel):
    """Represents metadata for an official FDA product labeling document / PDF."""
    found: bool = False
    url: Optional[str] = None
    pdf_url: Optional[str] = None
    document_title: Optional[str] = None
    document_date: Optional[str] = None
    version: Optional[str] = None
    supplement_number: Optional[str] = None
    source_article_url: Optional[str] = None
    retrieval_timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "found": self.found,
            "url": self.url or "",
            "pdf_url": self.pdf_url or "",
            "document_title": self.document_title or "",
            "document_date": self.document_date or "",
            "version": self.version or "",
            "supplement_number": self.supplement_number or "",
            "source_article_url": self.source_article_url or "",
            "retrieval_timestamp": self.retrieval_timestamp or "",
        }


class MedWatchSectionItem(BaseModel):
    """Structured extraction result for a specific product labeling safety section."""
    found: bool = False
    content: str = ""
    section: Optional[str] = None
    page: Optional[str] = None
    pages: List[int] = Field(default_factory=list)
    source_pdf: Optional[str] = None
    document_date: Optional[str] = None
    version: Optional[str] = None
    status: Optional[str] = None
    subsections: List[Dict[str, Any]] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "found": self.found,
            "status": self.status or ("SUCCESS" if self.found else "ADVERSE_REACTIONS_SECTION_NOT_FOUND"),
            "content": self.content,
            "section": self.section or "",
            "page": self.page or "",
            "pages": self.pages,
            "source_pdf": self.source_pdf or "",
            "document_date": self.document_date or "",
            "version": self.version or "",
            "subsections": self.subsections,
            "tables": self.tables,
        }


class MedWatchSafetySections(BaseModel):
    """Container for the primary required FDA safety sections."""
    adverse_reactions: MedWatchSectionItem = Field(default_factory=MedWatchSectionItem)
    warnings_and_precautions: MedWatchSectionItem = Field(default_factory=MedWatchSectionItem)
    pregnancy: MedWatchSectionItem = Field(default_factory=MedWatchSectionItem)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adverse_reactions": self.adverse_reactions.to_dict(),
            "warnings_and_precautions": self.warnings_and_precautions.to_dict(),
            "pregnancy": self.pregnancy.to_dict(),
        }


class MedWatchStructuredResult(BaseModel):
    """
    Complete structured result conforming to project schema:
    Contains product info, MedWatch article traceability, document version,
    and authoritative extracted labeling safety sections with page numbers and tables.
    """
    source: str = "FDA MedWatch"
    product: str
    active_ingredient: Optional[str] = None
    application_number: Optional[str] = None
    status: str = "SUCCESS"  # "SUCCESS", "PRODUCT_INFORMATION_DOCUMENT_NOT_FOUND", "ADVERSE_REACTIONS_SECTION_NOT_FOUND", "PDF_EXTRACTION_FAILED", "ERROR"
    medwatch_article: Optional[Dict[str, Any]] = None
    product_information: Optional[Dict[str, Any]] = None
    adverse_reactions: Optional[Dict[str, Any]] = None
    sections: Optional[Dict[str, Any]] = None
    content_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        sec = self.sections or {}
        ar = self.adverse_reactions or sec.get("adverse_reactions", {})
        return {
            "source": self.source,
            "product": self.product,
            "active_ingredient": self.active_ingredient or "",
            "application_number": self.application_number or "",
            "status": self.status,
            "medwatch_article": self.medwatch_article or {},
            "product_information": self.product_information or {},
            "adverse_reactions": ar,
            "sections": sec,
            "content_hash": self.content_hash or "",
        }

