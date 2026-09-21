"""
Data models for FDA Drug Safety-related Labeling Changes (SrLC).
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class FDASectionResult:
    """Represents an extracted FDA labeling section."""
    found: bool
    content: Optional[str] = None
    html_content: Optional[str] = None
    section: Optional[str] = None
    date: Optional[str] = None
    source_url: Optional[str] = None
    document_url: Optional[str] = None
    page: Optional[str] = None
    content_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "found": self.found,
            "content": self.content,
            "html_content": self.html_content,
            "section": self.section,
            "date": self.date,
            "source_url": self.source_url,
            "document_url": self.document_url,
            "page": self.page,
        }


@dataclass
class FDASafetySections:
    """Container for the three prioritized FDA safety sections."""
    adverse_reactions: FDASectionResult
    warnings_and_precautions: FDASectionResult
    pregnancy: FDASectionResult

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adverse_reactions": self.adverse_reactions.to_dict(),
            "warnings_and_precautions": self.warnings_and_precautions.to_dict(),
            "pregnancy": self.pregnancy.to_dict(),
        }


@dataclass
class FDASrLCStructuredResult:
    """Complete structured output matching FDA SrLC specification."""
    source: str = "FDA SrLC"
    product: str = ""
    active_ingredient: Optional[str] = None
    latest_labeling_change_date: Optional[str] = None
    supplement_number: Optional[str] = None
    application_number: Optional[str] = None
    sections: Optional[FDASafetySections] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "product": self.product,
            "active_ingredient": self.active_ingredient,
            "latest_labeling_change_date": self.latest_labeling_change_date,
            "supplement_number": self.supplement_number,
            "application_number": self.application_number,
            "sections": self.sections.to_dict() if self.sections else {},
        }


@dataclass
class FDASearchCandidate:
    """Represents a row returned from the FDA search results table."""
    drug_name: str
    active_ingredient: Optional[str] = None
    application_number: Optional[str] = None
    application_type: Optional[str] = None
    supplement_date: Optional[str] = None
    database_updated: Optional[str] = None
    detail_url: Optional[str] = None
    raw_date: Optional[datetime] = None


@dataclass
class FDASupplementRecord:
    """Represents a supplement update under an accordion item."""
    header_text: str
    date_str: str
    date_obj: datetime
    supplement_id: Optional[str] = None
    document_url: Optional[str] = None
    sections: List[Dict[str, Any]] = field(default_factory=list)
