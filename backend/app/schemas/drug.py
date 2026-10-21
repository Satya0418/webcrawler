from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, ConfigDict


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
    source: Optional[str] = "FDA_SRLC"
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


class WebsiteResponseItem(BaseModel):
    website_Name: str = Field("FDA_details", description="Website identifier e.g. 'FDA_details' or 'TGA_details'")
    website_Data: str = Field(..., description="Full HTML document string")
    Data: Optional[str] = Field(None, description="HTML document string (alias for website_Data for Salesforce compatibility)")

    model_config = ConfigDict(extra="ignore")


class SignalAndRiskItem(BaseModel):
    website_Name: Optional[str] = Field("FDA_details", description="Website identifier e.g. 'FDA_details' or 'TGA_details'")
    title: Optional[str] = Field("Website Safety Data", description="Title identifier")
    productName: Optional[str] = Field(None, description="Matched product or medicine name")
    genericName: Optional[str] = Field("", description="Generic name or active ingredient description")
    activeIngredients: Optional[str] = Field("", description="Active ingredients")
    startDate: Optional[str] = Field("", description="Applied start date filter in DD-MM-YYYY format")
    endDate: Optional[str] = Field("", description="Applied end date filter in DD-MM-YYYY format")
    Data: Optional[str] = Field(None, description="Actual extracted FDA Drug Safety HTML content string")
    website_Data: Optional[str] = Field(None, description="Full HTML document string")
    submissionId: Optional[str] = Field(None, description="Preserved submission identifier")


class WebsiteDataSection(BaseModel):
    title: str = Field("Website Crawler Data", description="Source identifier title")
    status: str = Field("success", description="Status: 'success', 'not_found', or 'error'")
    coverage: Optional[str] = Field(None, description="Coverage assessment: 'complete' or 'partial'")
    source_limitation: Optional[str] = Field(None, description="Explanation if date range exceeds source coverage")
    data: List[Dict[str, Any]] = Field(default_factory=list, description="List of website safety results")
    message: Optional[str] = Field(None, description="Informational message or reason for no results")


class SignalAndRiskResponse(BaseModel):
    submissionId: str = Field(..., description="Echo of received submissionId")
    responseType: str = Field("SafetyActionTaken", description="Response type category")
    productName: Optional[str] = Field(None, description="Echo of requested and matched product name")
    website_Data: Optional[WebsiteDataSection] = Field(None, description="Website crawler data section")
    responseData: List[WebsiteResponseItem] = Field(..., description="List of extracted section entries")


class SignalAndRiskIntegrationRequest(BaseModel):
    submissionId: Optional[str] = Field(None, description="Unique submission identifier (e.g. 'a0CAq00004acdq7MAA')")
    productName: Optional[str] = Field(None, description="Medicine or product name to search for (e.g. 'amikacin', 'Lipitor')")
    startDate: Optional[str] = Field(None, description="Start date filter in DD-MM-YYYY format (e.g. '01-01-2025')")
    endDate: Optional[str] = Field(None, description="End date filter in DD-MM-YYYY format (e.g. '01-01-2026')")
    genericName: Optional[str] = Field(None, description="Generic name filter")
    activeIngredients: Optional[str] = Field(None, description="Active ingredient(s) filter")

    # Snake-case and singular aliases
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
    format: Optional[str] = Field("json", description="Response format: 'json', 'html', or 'data'")

    model_config = ConfigDict(extra="ignore")

