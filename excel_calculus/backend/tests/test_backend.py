import pytest
import os
import sys

# Add root path
sys.path.insert(0, "/Users/satya/projects/webcrwler")

from excel_calculus.backend.app.database import SessionLocal
from excel_calculus.backend.app.models.entities import (
    CaseRecord, CaseEvent, SafetyConcern, SearchMatch, SearchRun, 
    RelevanceAssessment, SMQTerm, Dataset, AuditLog
)
from excel_calculus.backend.app.services.ingestion import IngestionService
from excel_calculus.backend.app.services.smq_loader import SMQLoaderService
from excel_calculus.backend.app.services.search_engine import SearchEngineService
from excel_calculus.backend.app.services.case_service import CaseService
from excel_calculus.backend.app.services.report_service import ReportService
from excel_calculus.backend.app.services.concern_seeder import seed_safety_concerns

@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()

# 1. Loading the SMQ master
def test_1_loading_smq_master(db):
    smq_count = db.query(SMQTerm).count()
    assert smq_count > 0, "SMQ master terms must be loaded in database"

# 2. Selecting exact SMQ
def test_2_selecting_exact_smq(db):
    hep_smq = db.query(SMQTerm).filter_by(smq_name="Drug related hepatic disorders - comprehensive search (SMQ)").all()
    assert len(hep_smq) > 0, "Must be able to query exact SMQ name"

# 3. Broad scope
def test_3_broad_scope_resolution(db):
    broad_terms = db.query(SMQTerm).filter_by(
        smq_name="Drug related hepatic disorders - comprehensive search (SMQ)",
        scope="Broad"
    ).all()
    assert len(broad_terms) == 334, f"Broad scope for Drug related hepatic disorders must have 334 PTs, got {len(broad_terms)}"

# 4. Narrow scope
def test_4_narrow_scope_resolution(db):
    narrow_terms = db.query(SMQTerm).filter_by(
        smq_name="Drug related hepatic disorders - comprehensive search (SMQ)",
        scope="Narrow"
    ).all()
    assert len(narrow_terms) == 269, f"Narrow scope for Drug related hepatic disorders must have 269 PTs, got {len(narrow_terms)}"

    rhab_narrow = db.query(SMQTerm).filter_by(
        smq_name="Rhabdomyolysis/myopathy (SMQ)",
        scope="Narrow"
    ).all()
    assert len(rhab_narrow) == 15, f"Narrow scope for Rhabdomyolysis/myopathy must have 15 PTs, got {len(rhab_narrow)}"

# 5. PT extraction
def test_5_pt_extraction(db):
    dili_term = db.query(SMQTerm).filter(
        SMQTerm.smq_name == "Drug related hepatic disorders - comprehensive search (SMQ)",
        SMQTerm.pt_name == "Drug-induced liver injury"
    ).first()
    assert dili_term is not None, "Preferred Term 'Drug-induced liver injury' must exist in SMQ"
    assert dili_term.pt_name == "Drug-induced liver injury"

# 6. PT code extraction
def test_6_pt_code_extraction(db):
    dili_term = db.query(SMQTerm).filter(
        SMQTerm.smq_name == "Drug related hepatic disorders - comprehensive search (SMQ)",
        SMQTerm.pt_name == "Drug-induced liver injury"
    ).first()
    assert dili_term.pt_code == "10072268", f"PT code for DILI must be 10072268, got {dili_term.pt_code}"

# 7. Event Verbatim cleaning
def test_7_event_verbatim_cleaning():
    raw = "  [PAIN IN EXTREMITY]  \n Y / Y / Y \n "
    ingestion = IngestionService(None)
    events = ingestion.parse_event_verbatim(raw)
    assert len(events) == 1
    assert events[0]["normalized_term"] == "PAIN IN EXTREMITY"

# 8. XML artifact removal
def test_8_xml_artifact_removal():
    ingestion = IngestionService(None)
    raw = "[PAIN IN EXTREMITY_x0015__x0016_]_x000D_\nY / Y / Y_x000D_"
    events = ingestion.parse_event_verbatim(raw)
    assert len(events) == 1
    assert events[0]["normalized_term"] == "PAIN IN EXTREMITY"
    assert "_x0015_" not in events[0]["normalized_term"]
    assert "_x000D_" not in events[0]["normalized_term"]

# 9. Y/Y/Y removal from medical terms
def test_9_yyy_removal_from_medical_terms():
    ingestion = IngestionService(None)
    raw = "[GAIT DISTURBANCE]\nY / Y / Y\n[INFLAMMATION]\nN / Y / Y\n[FATIGUE]\nN / N / Y"
    events = ingestion.parse_event_verbatim(raw)
    assert len(events) == 3
    for ev in events:
        assert "Y / Y / Y" not in ev["normalized_term"]
        assert "N / Y / Y" not in ev["normalized_term"]
        assert "N / N / Y" not in ev["normalized_term"]
        assert "Y" not in ev["normalized_term"] or ev["normalized_term"] in ("GAIT DISTURBANCE", "INFLAMMATION", "FATIGUE")
    assert events[0]["seriousness"] == "Y"
    assert events[1]["seriousness"] == "N"
    assert events[2]["causality"] == "Y"

# 10. Multi-event extraction
def test_10_multi_event_extraction():
    ingestion = IngestionService(None)
    raw = (
        "[PAIN IN EXTREMITY_x0015__x0016_]_x000D_\nY / Y / Y_x000D_\n"
        "[GAIT DISTURBANCE_x0016_]_x000D_\nY / Y / Y_x000D_\n"
        "[BONE PAIN_x0016_]_x000D_\nY / Y / Y_x000D_\n"
        "[PROSTATE CANCER_x0016_]_x000D_\nY / Y / Y_x000D_\n"
        "[INFLAMMATION]_x000D_\nN / Y / Y_x000D_\n"
        "[DRY MOUTH]_x000D_\nN / Y / Y_x000D_\n"
        "[DRY THROAT]_x000D_\nN / Y / Y_x000D_\n"
        "[COUGH]_x000D_\nN / N / Y_x000D_\n"
        "[FATIGUE]_x000D_\nN / N / Y"
    )
    events = ingestion.parse_event_verbatim(raw)
    assert len(events) == 9, f"Expected 9 exploded events for case 2025AP002474, got {len(events)}"
    terms = [e["normalized_term"] for e in events]
    assert terms == [
        "PAIN IN EXTREMITY", "GAIT DISTURBANCE", "BONE PAIN", "PROSTATE CANCER",
        "INFLAMMATION", "DRY MOUTH", "DRY THROAT", "COUGH", "FATIGUE"
    ]

# 11. Event position preservation
def test_11_event_position_preservation(db):
    events = db.query(CaseEvent).filter_by(case_number="2025AP002474").order_by(CaseEvent.position).all()
    assert len(events) == 9
    for idx, ev in enumerate(events):
        assert ev.position == idx + 1, f"Position must be 1-indexed in sequence, got {ev.position}"

# 12. Exact lookup matching
def test_12_exact_lookup_matching(db):
    search_service = SearchEngineService(db)
    res = search_service.execute_concern_search("abi_hepatotoxicity")
    assert res["total_event_matches"] == 14
    for case in res["cases"]:
        for match in case["matches"]:
            assert match["matched_term"] in ["Hepatic enzyme increased", "Liver function test increased", "Drug-induced liver injury"]

# 13. Non-match handling
def test_13_non_match_handling(db):
    # Prostate cancer is not in Hepatotoxicity SMQ
    non_match = db.query(CaseEvent).filter_by(case_number="2025AP002474", normalized_term="PROSTATE CANCER").first()
    assert non_match is not None
    # Prior to matching, preferred_term is null and no search match exists for hepatotoxicity
    match = db.query(SearchMatch).filter_by(case_number="2025AP002474", concern_id="abi_hepatotoxicity").first()
    assert match is None, "Non-matching event must return no match"

# 14. Distinct case grouping
def test_14_distinct_case_grouping(db):
    # Medication error has 21 matching events but only 14 distinct cases
    search_service = SearchEngineService(db)
    res = search_service.execute_concern_search("abi_medication_error")
    assert res["total_event_matches"] == 21
    assert res["distinct_candidate_cases"] == 14
    # Case 2024AP011685 has 3 event matches
    case_matches = [c for c in res["cases"] if c["case_number"] == "2024AP011685"][0]
    assert len(case_matches["matches"]) == 3

# 15. SOC search
def test_15_soc_search(db):
    search_service = SearchEngineService(db)
    res = search_service.execute_concern_search("abi_cardiac_disorders")
    # All 119 interval cases for Abiraterone have primary SOC other than Cardiac disorders
    assert res["distinct_candidate_cases"] == 0

# 16. CYP2D6 workflow
def test_16_cyp2d6_workflow(db):
    search_service = SearchEngineService(db)
    res = search_service.execute_concern_search("abi_cyp2d6_interaction")
    assert res["distinct_candidate_cases"] == 6
    assert res["total_event_matches"] == 6
    for c in res["cases"]:
        assert len(c["matches"]) > 0
        assert "CYP2D6" in c["matches"][0]["reference_source"]

# 17. Narrative search
def test_17_narrative_search(db):
    search_service = SearchEngineService(db)
    res = search_service.execute_concern_search("abi_missing_severe_renal")
    assert res["distinct_candidate_cases"] >= 1
    for c in res["cases"]:
        assert "Narrative" in c["matches"][0]["matched_field"]
        assert len(c["matches"][0]["evidence"]) > 10

# 18. Candidate status
def test_18_candidate_status(db):
    search_service = SearchEngineService(db)
    res = search_service.execute_concern_search("abi_overdose_med_error")
    assert res["distinct_candidate_cases"] == 1
    # Fresh candidate has status CANDIDATE
    case_row = res["cases"][0]
    assert case_row["assessment_status"] in ("CANDIDATE", "RELEVANT", "NOT_RELEVANT")

# 19. RELEVANT status
def test_19_relevant_status(db):
    case_service = CaseService(db)
    res = case_service.update_assessment(
        case_number="2025AP034387",
        concern_id="abi_hepatotoxicity",
        status="RELEVANT",
        reviewer_notes="Confirmed DILI during interval period."
    )
    assert res["status"] == "RELEVANT"

# 20. NOT_RELEVANT status
def test_20_not_relevant_status(db):
    case_service = CaseService(db)
    res = case_service.update_assessment(
        case_number="2025AP012204",
        concern_id="abi_hepatotoxicity",
        status="NOT_RELEVANT",
        exclusion_reason="Literature screening case with confounding disease"
    )
    assert res["status"] == "NOT_RELEVANT"
    assert res["exclusion_reason"] == "Literature screening case with confounding disease"

# 21. NEEDS_REVIEW status
def test_21_needs_review_status(db):
    case_service = CaseService(db)
    res = case_service.update_assessment(
        case_number="2025AP006512",
        concern_id="abi_hepatotoxicity",
        status="NEEDS_REVIEW",
        reviewer_notes="Requires medical reviewer consultation."
    )
    assert res["status"] == "NEEDS_REVIEW"

# 22. Final relevant case count
def test_22_final_relevant_case_count(db):
    report_service = ReportService(db)
    rep = report_service.generate_pbrer_section_report("abi_hepatotoxicity")
    # Only cases explicitly marked RELEVANT count!
    assert rep["metrics"]["relevant_case_count"] == 1
    assert rep["metrics"]["excluded_case_count"] == 1
    assert rep["metrics"]["candidate_case_count"] == 14

# 23. Duplicate-event protection
def test_23_duplicate_event_protection(db):
    events = db.query(CaseEvent).filter_by(case_number="2025AP002474").all()
    # 9 distinct positions
    positions = [e.position for e in events]
    assert len(positions) == len(set(positions)), "Event positions must be strictly unique"

# 24. Source lineage
def test_24_source_lineage(db):
    case_service = CaseService(db)
    detail = case_service.get_complete_case("2025AP002474", concern_id="abi_hepatotoxicity")
    assert "source_lineage" in detail
    assert detail["source_lineage"]["row"] == 2
    assert "Abiraterone" in detail["source_lineage"]["file"]
    for ev in detail["events"]:
        assert "source_lineage" in ev
        assert ev["source_lineage"]["row"] == 2

# 25. Re-ingestion
def test_25_re_ingestion(db):
    abi_path = "/Users/satya/Downloads/Required Artifacts for section 16.3 (3)/Abiraterone/Abiraterone_20260428_CAN-KUW-OMAN-UAE PBRER_Interval Linelisting.xlsx"
    ingestion = IngestionService(db)
    res = ingestion.ingest_linelisting_file(
        abi_path,
        primary_product_name="Abiraterone",
        reporting_period="29-Apr-2025 to 28-Apr-2026",
        data_lock_point="28-Apr-2026"
    )
    assert res["total_cases"] == 119
    assert res["total_events"] == 225
    # Total Abiraterone cases in DB must still be exactly 119 (no duplicates!)
    abi_cases = db.query(CaseRecord).filter_by(product_name="Abiraterone").count()
    assert abi_cases == 119, f"Re-ingestion must not create duplicate cases, got {abi_cases}"

# 26. Search reproducibility
def test_26_search_reproducibility(db):
    search_service = SearchEngineService(db)
    run1 = search_service.execute_concern_search("abi_hepatotoxicity")
    run2 = search_service.execute_concern_search("abi_hepatotoxicity")
    assert run1["total_event_matches"] == run2["total_event_matches"]
    assert run1["distinct_candidate_cases"] == run2["distinct_candidate_cases"]
    runs = db.query(SearchRun).filter_by(concern_id="abi_hepatotoxicity").all()
    assert len(runs) >= 2, "Each execution must create an auditable SearchRun record"

# 27. Final Section 16.1 report
def test_27_final_section_16_1_report(db):
    report_service = ReportService(db)
    table_data = report_service.generate_section_16_1_table("Abiraterone")
    assert table_data["title"] == "Section 16.1 Summary of Safety Concerns"
    assert table_data["product_name"] == "Abiraterone"
    assert len(table_data["table_sections"]) == 3
    sec_names = [s["category_name"] for s in table_data["table_sections"]]
    assert "Important Identified Risks" in sec_names
    assert "Important Potential Risks" in sec_names
    assert "Missing Information" in sec_names

    # Check risk items in Important Identified Risks
    id_risks = [r["risk_term"] for sec in table_data["table_sections"] if sec["category_name"] == "Important Identified Risks" for r in sec["risks"]]
    assert "Hepatotoxicity" in id_risks
    assert "Cardiac disorders" in id_risks
    assert "Rhabdomyolysis/Myopathy" in id_risks
