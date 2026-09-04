"""
SQLAlchemy ORM models for drugs and safety labeling changes.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from app.database import Base


class Drug(Base):
    """Drug/Medicine entity."""

    __tablename__ = "drugs"

    id = Column(Integer, primary_key=True, index=True)
    display_name = Column(String(255), nullable=False, index=True)
    normalized_name = Column(String(255), nullable=False, index=True)
    active_ingredient = Column(String(255), nullable=True, index=True)
    application_number = Column(String(50), nullable=True)
    source = Column(String(50), default="FDA_SRLC", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    safety_changes = relationship(
        "SafetyLabelingChange", back_populates="drug", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Drug(id={self.id}, name='{self.display_name}')>"


class SafetyLabelingChange(Base):
    """Safety-related labeling change record."""

    __tablename__ = "safety_labeling_changes"

    id = Column(Integer, primary_key=True, index=True)
    drug_id = Column(Integer, ForeignKey("drugs.id"), nullable=False, index=True)
    source = Column(String(50), default="FDA_SRLC", nullable=False)
    source_record_id = Column(String(100), nullable=True, index=True)
    section = Column(String(100), nullable=True)
    change_type = Column(String(100), nullable=True)
    source_date = Column(DateTime, nullable=True)
    approval_date = Column(DateTime, nullable=True)
    effective_date = Column(DateTime, nullable=True)
    original_text = Column(Text, nullable=True)
    updated_text = Column(Text, nullable=True)
    fda_comment = Column(Text, nullable=True)
    source_url = Column(String(500), nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_verified_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    drug = relationship("Drug", back_populates="safety_changes")
    versions = relationship(
        "SafetyChangeVersion", back_populates="safety_change", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<SafetyLabelingChange(id={self.id}, drug_id={self.drug_id}, section='{self.section}')>"


class SafetyChangeVersion(Base):
    """Version history for safety labeling changes."""

    __tablename__ = "safety_change_versions"

    id = Column(Integer, primary_key=True, index=True)
    safety_change_id = Column(
        Integer, ForeignKey("safety_labeling_changes.id"), nullable=False, index=True
    )
    version_number = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=True)
    original_text = Column(Text, nullable=True)
    updated_text = Column(Text, nullable=True)
    normalized_content = Column(Text, nullable=True)
    retrieved_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    safety_change = relationship("SafetyLabelingChange", back_populates="versions")

    def __repr__(self):
        return f"<SafetyChangeVersion(id={self.id}, version={self.version_number})>"


class CrawlRun(Base):
    """Record of each FDA crawl execution."""

    __tablename__ = "crawl_runs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), default="FDA_SRLC", nullable=False)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="pending", nullable=False)  # pending, running, success, failed
    pages_requested = Column(Integer, default=0)
    pages_crawled = Column(Integer, default=0)
    records_found = Column(Integer, default=0)
    records_added = Column(Integer, default=0)
    records_changed = Column(Integer, default=0)
    records_unchanged = Column(Integer, default=0)
    errors = Column(Text, nullable=True)  # JSON array of errors
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<CrawlRun(id={self.id}, status='{self.status}', source='{self.source}')>"
