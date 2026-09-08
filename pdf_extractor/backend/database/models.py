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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

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
    content_json = Column(Text, nullable=True)

    extraction = relationship("ExtractionRecord", back_populates="blocks")
