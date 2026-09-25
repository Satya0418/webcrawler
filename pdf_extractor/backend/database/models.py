import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class DocumentRecord(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False)
    total_pages = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    extractions = relationship("ExtractionRecord", back_populates="document", cascade="all, delete-orphan")


class ExtractionRecord(Base):
    __tablename__ = "extractions"

    id = Column(String(36), primary_key=True)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    main_section = Column(String(50), nullable=False)
    target_subsection = Column(String(50), nullable=True)
    start_page = Column(Integer, default=0)
    end_page = Column(Integer, default=0)
    status = Column(String(50), default="success")
    confidence_score = Column(Float, default=1.0)
    included_sections = Column(Text, default="[]")
    excluded_sections = Column(Text, default="[]")
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    document = relationship("DocumentRecord", back_populates="extractions")
    blocks = relationship("ContentBlockRecord", back_populates="extraction", cascade="all, delete-orphan")


class ContentBlockRecord(Base):
    __tablename__ = "content_blocks"

    id = Column(String(64), primary_key=True)
    extraction_id = Column(String(36), ForeignKey("extractions.id"), nullable=False)
    block_type = Column(String(50), nullable=False)
    page_num = Column(Integer, nullable=False)
    section_number = Column(String(50), nullable=True)
    reading_order = Column(Integer, default=0)
    text = Column(Text, nullable=True)
    bbox_json = Column(String(255), nullable=True)
    extraction = relationship("ExtractionRecord", back_populates="blocks")


class ProductSectionRecord(Base):
    """
    Persistent store for extracted product sections (specifically Section 16).
    Enables sub-millisecond API queries by client systems without re-parsing PDFs.
    """
    __tablename__ = "product_sections"

    id = Column(String(36), primary_key=True)
    product_name = Column(String(255), nullable=False, index=True)
    product_normalized = Column(String(255), nullable=False, index=True)
    filename = Column(String(255), nullable=False, index=True)
    file_path = Column(String(1024), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    file_mtime = Column(Float, nullable=False, default=0.0)
    file_size_bytes = Column(Integer, default=0)
    total_pages = Column(Integer, default=0)
    
    target_section = Column(String(50), nullable=False, default="16", index=True)
    section_title = Column(String(255), nullable=True)
    start_page = Column(Integer, default=0)
    end_page = Column(Integer, default=0)
    status = Column(String(50), default="success", index=True)  # "success", "not_found", "error"
    confidence_score = Column(Float, default=1.0)
    
    extracted_text = Column(Text, nullable=True)
    extracted_html = Column(Text, nullable=True)
    tables_json = Column(Text, nullable=True)
    subsections_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))


class ScannerLogRecord(Base):
    """
    Audit log of automated 30-minute folder scan executions.
    """
    __tablename__ = "scanner_logs"

    id = Column(String(36), primary_key=True)
    scanned_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), index=True)
    duration_seconds = Column(Float, default=0.0)
    files_scanned = Column(Integer, default=0)
    files_processed = Column(Integer, default=0)
    files_skipped = Column(Integer, default=0)
    files_errored = Column(Integer, default=0)
    status = Column(String(50), default="completed")  # "completed", "error"
    error_message = Column(Text, nullable=True)
    details_json = Column(Text, nullable=True)
