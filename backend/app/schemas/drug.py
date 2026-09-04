"""Pydantic schemas for request/response validation."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class DrugBase(BaseModel):
    """Base schema for Drug."""

    display_name: str
    normalized_name: str
    active_ingredient: Optional[str] = None
    application_number: Optional[str] = None
    source: str = "FDA_SRLC"


class DrugCreate(DrugBase):
    """Schema for creating a Drug."""

    pass


class DrugResponse(DrugBase):
    """Schema for Drug response."""

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SafetyLabelingChangeBase(BaseModel):
    """Base schema for SafetyLabelingChange."""

    section: Optional[str] = None
    change_type: Optional[str] = None
    source_date: Optional[datetime] = None
    approval_date: Optional[datetime] = None
    effective_date: Optional[datetime] = None
    original_text: Optional[str] = None
    updated_text: Optional[str] = None
    fda_comment: Optional[str] = None
    source_url: Optional[str] = None


class SafetyLabelingChangeCreate(SafetyLabelingChangeBase):
    """Schema for creating a SafetyLabelingChange."""

    drug_id: int
    source_record_id: Optional[str] = None
    content_hash: Optional[str] = None


class SafetyLabelingChangeResponse(SafetyLabelingChangeBase):
    """Schema for SafetyLabelingChange response."""

    id: int
    drug_id: int
    source_record_id: Optional[str] = None
    content_hash: Optional[str] = None
    first_seen_at: datetime
    last_verified_at: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SafetyChangeVersionResponse(BaseModel):
    """Schema for SafetyChangeVersion response."""

    id: int
    version_number: int
    content_hash: Optional[str] = None
    original_text: Optional[str] = None
    updated_text: Optional[str] = None
    retrieved_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class DrugDetailResponse(DrugResponse):
    """Schema for detailed Drug response with safety changes."""

    safety_changes: List[SafetyLabelingChangeResponse] = []


class DrugSearchResultItem(BaseModel):
    """Schema for individual search result item."""

    drug_id: int
    drug_name: str
    active_ingredient: Optional[str] = None
    application_number: Optional[str] = None
    safety_change_count: int = 0
    last_verified_at: Optional[datetime] = None


class SearchResultResponse(BaseModel):
    """Schema for search results."""

    query: str
    source: str = "FDA_SRLC"
    results: List[DrugSearchResultItem]


class CrawlRunResponse(BaseModel):
    """Schema for CrawlRun response."""

    id: int
    source: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    pages_requested: int
    pages_crawled: int
    records_found: int
    records_added: int
    records_changed: int
    records_unchanged: int
    errors: Optional[str] = None

    class Config:
        from_attributes = True
