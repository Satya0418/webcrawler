from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from excel_calculus.backend.app.database import Base

class CaseRecord(Base):
    __tablename__ = "case_records"

    case_number = Column(String(64), primary_key=True, index=True)
    product_name = Column(String(255), index=True)
    primary_product = Column(String(255), index=True)
    country = Column(String(128), index=True)
    report_type = Column(String(128))
    age = Column(String(64))
    sex = Column(String(32))
    initial_receipt_date = Column(String(64), index=True)
    is_serious = Column(Boolean, default=False)
    seriousness_raw = Column(String(32))
    listedness = Column(String(64))
    case_outcome = Column(String(128))
    primary_soc = Column(String(255), index=True)
    primary_event_flag = Column(String(32))
    previous_submission = Column(String(32))
    healthcare_prof = Column(String(32))
    non_serious_listed = Column(String(32))
    follow_up = Column(String(32))
    case_classification = Column(String(128))
    relevant_history = Column(Text, nullable=True)
    narrative = Column(Text, nullable=True)
    death_cause = Column(Text, nullable=True)
    case_comments = Column(Text, nullable=True)
    raw_source_file = Column(String(255))
    raw_source_sheet = Column(String(128))
    raw_source_row = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    events = relationship("CaseEvent", back_populates="case", cascade="all, delete-orphan")
    products = relationship("CaseProduct", back_populates="case", cascade="all, delete-orphan")
    assessments = relationship("RelevanceAssessment", back_populates="case", cascade="all, delete-orphan")
    matches = relationship("SearchMatch", back_populates="case", cascade="all, delete-orphan")

class CaseEvent(Base):
    __tablename__ = "case_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_number = Column(String(64), ForeignKey("case_records.case_number"), index=True)
    position = Column(Integer)
    raw_verbatim = Column(Text)
    normalized_term = Column(String(255), index=True) # Uppercase normalized
    preferred_term = Column(String(255), index=True)  # Clean display term
    soc = Column(String(255), index=True, nullable=True)
    event_onset = Column(String(128), nullable=True)
    event_outcome = Column(String(128), nullable=True)
    seriousness_flag = Column(String(16), nullable=True)
    listedness_flag = Column(String(16), nullable=True)
    causality_flag = Column(String(16), nullable=True)

    case = relationship("CaseRecord", back_populates="events")

class CaseProduct(Base):
    __tablename__ = "case_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_number = Column(String(64), ForeignKey("case_records.case_number"), index=True)
    product_name_raw = Column(Text)
    brand_name = Column(String(255), nullable=True)
    active_substance = Column(String(255), index=True, nullable=True)
    role = Column(String(64), index=True) # Suspect, Concom, etc.
    daily_dose = Column(String(255), nullable=True)
    form = Column(String(128), nullable=True)
    duration = Column(String(255), nullable=True)
    indication_pt = Column(String(255), nullable=True)

    case = relationship("CaseRecord", back_populates="products")

class SMQTerm(Base):
    __tablename__ = "smq_terms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    smq_name = Column(String(255), index=True)
    smq_code = Column(String(32), index=True)
    scope = Column(String(32), index=True) # Broad, Narrow
    pt_name = Column(String(255), index=True)
    pt_name_upper = Column(String(255), index=True)
    pt_code = Column(String(32), index=True)
    is_active = Column(Boolean, default=True)

class SafetyConcern(Base):
    __tablename__ = "safety_concerns"

    id = Column(String(64), primary_key=True)
    product_name = Column(String(128), index=True)
    reporting_period = Column(String(128), index=True)
    name = Column(String(255), index=True)
    category = Column(String(128)) # Important Identified Risks, Important Potential Risks, Missing Information
    description = Column(Text, nullable=True)
    search_method = Column(String(64)) # BROAD_SMQ, NARROW_SMQ, SOC, SINGLE_PT, MULTIPLE_PTS, SMQ_SUBFILTER, CONCOMITANT_INTERACTION, NARRATIVE, MANUAL
    search_config = Column(Text) # JSON configuration
    requires_secondary_assessment = Column(Boolean, default=False)
    secondary_assessment_instructions = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    matches = relationship("SearchMatch", back_populates="concern", cascade="all, delete-orphan")
    assessments = relationship("RelevanceAssessment", back_populates="concern", cascade="all, delete-orphan")

class SearchMatch(Base):
    __tablename__ = "search_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    concern_id = Column(String(64), ForeignKey("safety_concerns.id"), index=True)
    case_number = Column(String(64), ForeignKey("case_records.case_number"), index=True)
    event_id = Column(Integer, ForeignKey("case_events.id"), nullable=True)
    search_method = Column(String(64))
    matched_field = Column(String(128))
    matched_term = Column(String(255))
    reference_source = Column(String(255))
    evidence = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    concern = relationship("SafetyConcern", back_populates="matches")
    case = relationship("CaseRecord", back_populates="matches")
    event = relationship("CaseEvent")

class RelevanceAssessment(Base):
    __tablename__ = "relevance_assessments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_number = Column(String(64), ForeignKey("case_records.case_number"), index=True)
    concern_id = Column(String(64), ForeignKey("safety_concerns.id"), index=True)
    status = Column(String(32), default="CANDIDATE", index=True) # CANDIDATE, RELEVANT, NOT_RELEVANT, NEEDS_REVIEW
    exclusion_reason = Column(String(255), nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    secondary_assessment_result = Column(Text, nullable=True)
    reviewer_id = Column(String(64), default="reviewer")
    updated_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("CaseRecord", back_populates="assessments")
    concern = relationship("SafetyConcern", back_populates="assessments")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_number = Column(String(64), nullable=True, index=True)
    concern_id = Column(String(64), nullable=True, index=True)
    user_id = Column(String(64), default="system")
    action = Column(String(128))
    previous_state = Column(Text, nullable=True)
    new_state = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
