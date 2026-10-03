import pytest
import os
import sys

# Add root path
sys.path.insert(0, "/Users/satya/projects/webcrwler")

from excel_calculus.backend.app.database import SessionLocal
from excel_calculus.backend.app.models.entities import CaseRecord, CaseEvent, SafetyConcern, SearchMatch, RelevanceAssessment
from excel_calculus.backend.app.services.search_engine import SearchEngineService
from excel_calculus.backend.app.services.case_service import CaseService
from excel_calculus.backend.app.services.report_service import ReportService

@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()

def test_database_populated(db):
    cases_count = db.query(CaseRecord).count()
    events_count = db.query(CaseEvent).count()
    concerns_count = db.query(SafetyConcern).count()

    assert cases_count >= 119, "Expected at least 119 Abiraterone cases"
    assert events_count >= 225, "Expected at least 225 Abiraterone events"
    assert concerns_count >= 10, "Expected at least 10 safety concerns"

def test_hepatotoxicity_search(db):
    search_service = SearchEngineService(db)
    res = search_service.execute_concern_search("abi_hepatotoxicity")
    
    assert res["concern_name"] == "Hepatotoxicity"
    assert res["distinct_candidate_cases"] == 14, f"Expected 14 distinct cases, got {res['distinct_candidate_cases']}"
    assert res["total_event_matches"] == 14, f"Expected 14 events, got {res['total_event_matches']}"

def test_medication_error_search(db):
    search_service = SearchEngineService(db)
    res = search_service.execute_concern_search("abi_medication_error")
    
    assert res["concern_name"] == "Medication error"
    assert res["distinct_candidate_cases"] == 14, f"Expected 14 distinct cases matching Table 3, got {res['distinct_candidate_cases']}"
    assert res["total_event_matches"] == 21, f"Expected 21 event matches, got {res['total_event_matches']}"

def test_rhabdomyolysis_search(db):
    search_service = SearchEngineService(db)
    res = search_service.execute_concern_search("abi_rhabdomyolysis")
    
    assert res["distinct_candidate_cases"] == 4, f"Expected 4 distinct cases, got {res['distinct_candidate_cases']}"

def test_case_detail_retrieval(db):
    case_service = CaseService(db)
    detail = case_service.get_complete_case("2025AP002474", concern_id="abi_hepatotoxicity")
    
    assert detail["case_number"] == "2025AP002474"
    assert len(detail["events"]) == 9, "Case 2025AP002474 must have 9 exploded events"
    assert len(detail["products"]) >= 1
    assert "narrative" in detail
    assert "source_lineage" in detail
    assert detail["source_lineage"]["row"] == 2

def test_relevance_assessment_workflow(db):
    case_service = CaseService(db)
    test_case = "2025AP006512"
    concern = "abi_hepatotoxicity"

    # Set as NOT_RELEVANT
    res = case_service.update_assessment(
        case_number=test_case,
        concern_id=concern,
        status="NOT_RELEVANT",
        exclusion_reason="Alternative etiology: concomitant chemotherapy",
        reviewer_notes="Patient had documented progression and chemotherapy induced transaminitis."
    )
    assert res["status"] == "NOT_RELEVANT"

    # Verify report reflects exclusion
    report_service = ReportService(db)
    rep = report_service.generate_pbrer_section_report(concern)
    assert rep["metrics"]["excluded_case_count"] >= 1

    # Reset back to RELEVANT
    case_service.update_assessment(
        case_number=test_case,
        concern_id=concern,
        status="RELEVANT",
        reviewer_notes="Confirmed hepatic enzyme elevation temporally related."
    )

def test_pbrer_report_generation(db):
    report_service = ReportService(db)
    rep = report_service.generate_pbrer_section_report("abi_hepatotoxicity")
    
    assert rep["metadata"]["safety_concern"] == "Hepatotoxicity"
    assert rep["metrics"]["candidate_case_count"] == 14
    assert len(rep["pt_summary_table"]) >= 1
    assert "clinical_narrative_summary" in rep
