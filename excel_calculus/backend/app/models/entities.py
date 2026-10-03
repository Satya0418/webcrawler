from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from excel_calculus.backend.app.database import Base

class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String(64), primary_key=True)
    dataset_type = Column(String(64), index=True)  # LINE_LISTING, SMQ_REFERENCE
    product_name = Column(String(128), index=True)
    reporting_period = Column(String(128), index=True, nullable=True)
    data_lock_point = Column(String(64), nullable=True)
    source_filename = Column(String(255))
    source_file_hash = Column(String(64), index=True)
    total_cases = Column(Integer, default=0)
    total_events = Column(Integer, default=0)
    status = Column(String(32), default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    cases = relationship("CaseRecord", back_populates="dataset", cascade="all, delete-orphan")

class CaseRecord(Base):
    __tablename__ = "case_records"

    case_number = Column(String(64), primary_key=True, index=True)
    dataset_id = Column(String(64), ForeignKey("datasets.id"), nullable=True, index=True)
    product_name = Column(String(255), index=True)
    reporting_period = Column(String(128), index=True, nullable=True)
    data_lock_point = Column(String(64), nullable=True)
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
    dataset = relationship("Dataset", back_populates="cases")
    events = relationship("CaseEvent", back_populates="case", cascade="all, delete-orphan")
    products = relationship("CaseProduct", back_populates="case", cascade="all, delete-orphan")
    assessments = relationship("RelevanceAssessment", back_populates="case", cascade="all, delete-orphan")
    matches = relationship("SearchMatch", back_populates="case", cascade="all, delete-orphan")

class CaseEvent(Base):
    __tablename__ = "case_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_number = Column(String(64), ForeignKey("case_records.case_number"), index=True)
    dataset_id = Column(String(64), nullable=True, index=True)
    position = Column(Integer)
    raw_verbatim = Column(Text)
    normalized_term = Column(String(255), index=True)  # Uppercase normalized clean term
    preferred_term = Column(String(255), index=True, nullable=True)  # Matched MedDRA PT (null if unconfirmed)
    pt_code = Column(String(32), index=True, nullable=True)  # Matched MedDRA PT Code
    soc = Column(String(255), index=True, nullable=True)
    event_onset = Column(String(128), nullable=True)
    event_outcome = Column(String(128), nullable=True)
    seriousness_flag = Column(String(16), nullable=True)
    listedness_flag = Column(String(16), nullable=True)
    causality_flag = Column(String(16), nullable=True)
    source_file = Column(String(255), nullable=True)
    source_sheet = Column(String(128), nullable=True)
    source_row = Column(Integer, nullable=True)

    case = relationship("CaseRecord", back_populates="events")

class CaseProduct(Base):
    __tablename__ = "case_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_number = Column(String(64), ForeignKey("case_records.case_number"), index=True)
    dataset_id = Column(String(64), nullable=True, index=True)
    product_name_raw = Column(Text)
    brand_name = Column(String(255), nullable=True)
    active_substance = Column(String(255), index=True, nullable=True)
    role = Column(String(64), index=True)  # Suspect, Concom, etc.
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
    scope = Column(String(32), index=True)  # Broad, Narrow
    pt_name = Column(String(255), index=True)  # Authoritative MedDRA PT
    pt_name_upper = Column(String(255), index=True)  # For exact lookup
    pt_code = Column(String(32), index=True)  # 8-digit MedDRA PT code
    category = Column(String(16), nullable=True)  # Algorithm category if applicable (A, B, C, etc.)
    is_active = Column(Boolean, default=True)
    reference_version = Column(String(32), default="29.0")

class SafetyConcern(Base):
    __tablename__ = "safety_concerns"

    id = Column(String(64), primary_key=True)
    product_name = Column(String(128), index=True)
    reporting_period = Column(String(128), index=True)
    name = Column(String(255), index=True)
    category = Column(String(128))  # Important Identified Risks, Important Potential Risks, Missing Information
    description = Column(Text, nullable=True)
    search_method = Column(String(64))  # BROAD_SMQ, NARROW_SMQ, SOC, SINGLE_PT, MULTIPLE_PTS, SMQ_SUBFILTER, CONCOMITANT_INTERACTION, NARRATIVE, MANUAL
    search_config = Column(Text)  # JSON configuration
    requires_secondary_assessment = Column(Boolean, default=False)
    secondary_assessment_instructions = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    matches = relationship("SearchMatch", back_populates="concern", cascade="all, delete-orphan")
    assessments = relationship("RelevanceAssessment", back_populates="concern", cascade="all, delete-orphan")
    search_runs = relationship("SearchRun", back_populates="concern", cascade="all, delete-orphan")

class SearchRun(Base):
    __tablename__ = "search_runs"

    id = Column(String(64), primary_key=True)
    product_name = Column(String(128), index=True)
    reporting_period = Column(String(128), index=True)
    concern_id = Column(String(64), ForeignKey("safety_concerns.id"), index=True)
    search_method = Column(String(64))
    search_config = Column(Text)
    reference_version = Column(String(32), default="MedDRA 29.0")
    execution_time = Column(DateTime, default=datetime.utcnow)
    candidate_events_count = Column(Integer, default=0)
    distinct_cases_count = Column(Integer, default=0)
    executed_by = Column(String(64), default="reviewer")

    concern = relationship("SafetyConcern", back_populates="search_runs")
    matches = relationship("SearchMatch", back_populates="search_run", cascade="all, delete-orphan")

class SearchMatch(Base):
    __tablename__ = "search_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    search_run_id = Column(String(64), ForeignKey("search_runs.id"), nullable=True, index=True)
    concern_id = Column(String(64), ForeignKey("safety_concerns.id"), index=True)
    case_number = Column(String(64), ForeignKey("case_records.case_number"), index=True)
    event_id = Column(Integer, ForeignKey("case_events.id"), nullable=True)
    search_method = Column(String(64))
    matched_field = Column(String(128))
    matched_term = Column(String(255))
    pt_code = Column(String(32), nullable=True)
    smq_name = Column(String(255), nullable=True)
    smq_scope = Column(String(32), nullable=True)
    reference_source = Column(String(255))
    evidence = Column(Text)
    source_file = Column(String(255), nullable=True)
    source_sheet = Column(String(128), nullable=True)
    source_row = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    concern = relationship("SafetyConcern", back_populates="matches")
    case = relationship("CaseRecord", back_populates="matches")
    event = relationship("CaseEvent")
    search_run = relationship("SearchRun", back_populates="matches")

class RelevanceAssessment(Base):
    __tablename__ = "relevance_assessments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_number = Column(String(64), ForeignKey("case_records.case_number"), index=True)
    concern_id = Column(String(64), ForeignKey("safety_concerns.id"), index=True)
    status = Column(String(32), default="CANDIDATE", index=True)  # CANDIDATE, RELEVANT, NOT_RELEVANT, NEEDS_REVIEW
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
    dataset_id = Column(String(64), nullable=True, index=True)
    user_id = Column(String(64), default="system")
    action = Column(String(128))
    previous_state = Column(Text, nullable=True)
    new_state = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
