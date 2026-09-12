from __future__ import annotations
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    BULLET_LIST = "bullet_list"
    NUMBERED_LIST = "numbered_list"
    TABLE = "table"
    HEADER = "header"
    FOOTER = "footer"
    CAPTION = "caption"
    FOOTNOTE = "footnote"


class DocumentBlock(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    block_id: str
    page_num: int
    bbox: Tuple[float, float, float, float]
    block_type: BlockType = BlockType.PARAGRAPH
    text: str = ""
    font_size: float = 0.0
    is_bold: bool = False
    bullet_items: Optional[List[str]] = None
    table_data: Optional[List[List[Optional[str]]]] = None
    table_columns: Optional[List[str]] = None
    table_rows: Optional[List[Dict[str, Any]]] = None
    table_markdown: Optional[str] = None
    section_number: Optional[str] = None
    is_heading: bool = False
    heading_level: Optional[int] = None


class StructuredContentItem(BaseModel):
    """Represents a discrete, typed, structured element in the extracted document."""
    type: str  # 'heading', 'paragraph', 'bullet_list', 'table', etc.
    page: int
    bbox: Optional[List[float]] = None
    section_number: Optional[str] = None
    title: Optional[str] = None  # for heading
    level: Optional[int] = None  # for heading
    text: Optional[str] = None  # for paragraph, caption
    items: Optional[List[str]] = None  # for bullet_list
    table_id: Optional[str] = None  # for table
    caption: Optional[str] = None  # for table
    columns: Optional[List[str]] = None  # for table
    rows: Optional[List[Dict[str, Any]]] = None  # for table rows as dicts
    raw_rows: Optional[List[List[str]]] = None  # for table raw matrix


class SectionSummary(BaseModel):
    number: str
    title: str
    level: int
    start_page: int
    end_page: int
    children: List[SectionSummary] = Field(default_factory=list)


class ValidationChecklist(BaseModel):
    was_main_section_found: bool = False
    was_target_subsection_found: bool = False
    start_page: int = 0
    end_page: int = 0
    included_sections: List[str] = Field(default_factory=list)
    excluded_sections: List[str] = Field(default_factory=list)
    tables_included_count: int = 0
    tables_detected_count: int = 0
    tables_neglected_count: int = 0
    table_mode: str = "add"  # 'add' or 'neglect'
    total_blocks_extracted: int = 0
    confidence_score: float = 0.0
    warnings: List[str] = Field(default_factory=list)
    status_message: str = ""


class ExtractionRequest(BaseModel):
    file_path: Optional[str] = None
    filename: Optional[str] = None
    main_section: str = "16"
    target_subsection: Optional[str] = "16.1"
    natural_query: Optional[str] = None
    format: Optional[str] = None  # e.g., 'html' or 'json'
    response_format: Optional[str] = None
    include_tables: bool = True
    table_mode: str = "add"  # 'add' (include table) or 'neglect' (text only, neglect table)
    section_table_mode: Optional[Dict[str, str]] = None  # Optional per-section overrides e.g. {"16.1": "neglect"}


class BlockTrace(BaseModel):
    id: str
    page: int
    section: Optional[str] = None
    block_type: str
    text: str
    bbox: Optional[List[float]] = None
    bullet_items: Optional[List[str]] = None
    table_columns: Optional[List[str]] = None
    table_rows: Optional[List[Dict[str, Any]]] = None
    table_data: Optional[List[List[Optional[str]]]] = None
    table_markdown: Optional[str] = None


class ExtractionResult(BaseModel):
    Data: Optional[str] = None  # Formatted HTML response string when requested in HTML format
    document: str
    requested_section: str
    requested_subsection: Optional[str] = None
    start_page: int = 0
    end_page: int = 0
    subsections_found: List[str] = Field(default_factory=list)
    content: str = ""
    structured_content: List[StructuredContentItem] = Field(default_factory=list)
    blocks: List[BlockTrace] = Field(default_factory=list)
    validation: ValidationChecklist = Field(default_factory=ValidationChecklist)
    table_mode: str = "add"
    tables_detected: int = 0
    tables_neglected: int = 0
    section_table_status: Dict[str, str] = Field(default_factory=dict)
    status: str = "success"
    error_message: Optional[str] = None
    section_tree: Optional[List[SectionSummary]] = None
    download_urls: Dict[str, str] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BatchExtractionRequest(BaseModel):
    files: List[str] = Field(default_factory=list)
    folder_path: Optional[str] = None
    main_section: str = "16"
    target_subsection: Optional[str] = "16.1"
    natural_query: Optional[str] = None
    format: Optional[str] = None
    response_format: Optional[str] = None
    include_tables: bool = True
    table_mode: str = "add"
    section_table_mode: Optional[Dict[str, str]] = None


class BatchExtractionResponse(BaseModel):
    Data: Optional[str] = None
    total_documents: int
    successful: int
    failed: int
    results: List[ExtractionResult]
    summary_csv_url: Optional[str] = None
    summary_excel_url: Optional[str] = None


class BrowseFolderRequest(BaseModel):
    folder_path: str


class DiscoveredFile(BaseModel):
    filename: str
    full_path: str
    size_bytes: int
    size_formatted: str
    pages_estimate: Optional[int] = None


class BrowseFolderResponse(BaseModel):
    folder_path: str
    total_found: int
    files: List[DiscoveredFile]
