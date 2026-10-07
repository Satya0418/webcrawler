import pytest
import os
import sys
import io

# Dynamic portable root path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from excel_calculus.backend.app.database import SessionLocal
from excel_calculus.backend.app.models.entities import (
    CaseRecord, CaseEvent, CaseProduct, SafetyConcern, SearchMatch, SearchRun, 
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
    abi_path = os.environ.get(
        "ABIRATERONE_EXCEL_PATH",
        os.path.join(BASE_DIR, "excel_calculus", "data", "Abiraterone_20260428_CAN-KUW-OMAN-UAE PBRER_Interval Linelisting.xlsx")
    )
    if not os.path.exists(abi_path):
        fallback = os.path.expanduser("~/Downloads/Required Artifacts for section 16.3 (3)/Abiraterone/Abiraterone_20260428_CAN-KUW-OMAN-UAE PBRER_Interval Linelisting.xlsx")
        if os.path.exists(fallback):
            abi_path = fallback

    if not os.path.exists(abi_path):
        pytest.skip(f"Abiraterone linelisting not found at {abi_path}")

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

    # Strictly 13 official concerns; Section 9 Medication error must NOT be in Section 16.1 table
    all_risks = [r["risk_term"] for sec in table_data["table_sections"] for r in sec["risks"]]
    assert len(all_risks) == 13
    assert "Medication error" not in all_risks
    assert "Overdose due to medication error" in all_risks

# 28. Real PDF generation and visual verification via pypdf
def test_28_real_pbrer_pdf_generation(db):
    import pypdf
    report_service = ReportService(db)
    pdf_bytes = report_service.generate_section_16_1_pdf("Abiraterone")

    assert pdf_bytes is not None
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-1.4"), "Must be a valid PDF-1.4 file"

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1

    all_pdf_text = ""
    for page in reader.pages:
        txt = page.extract_text()
        all_pdf_text += "\n" + txt

    # Verify official running header & footer
    assert "Apotex Inc." in all_pdf_text
    assert "Abiraterone" in all_pdf_text
    assert "Periodic Benefit-Risk Evaluation Report" in all_pdf_text
    assert "CONFIDENTIAL" in all_pdf_text
    assert "Page " in all_pdf_text

    # Verify official table headers and categories
    assert "Risk Term" in all_pdf_text
    assert "Case Reports" in all_pdf_text
    assert "IMPORTANT IDENTIFIED RISKS" in all_pdf_text
    assert "IMPORTANT POTENTIAL RISKS" in all_pdf_text
    assert "MISSING INFORMATION" in all_pdf_text

    # Verify all risk terms are present in the PDF
    assert "Hepatotoxicity" in all_pdf_text
    assert "Cardiac disorders" in all_pdf_text
    assert "Osteoporosis including osteoporosis-related fractures" in all_pdf_text
    assert "Allergic alveolitis" in all_pdf_text
    assert "Increased exposure with food" in all_pdf_text
    assert "Rhabdomyolysis/Myopathy" in all_pdf_text
    assert "Cataract" in all_pdf_text
    assert "Drug drug interaction with CYP2D6 inhibitors" in all_pdf_text
    assert "Overdose due to medication error" in all_pdf_text

    # Verify Requirement 18: No Total row in official table
    assert "Total =" not in all_pdf_text
    assert "TOTAL RELEVANT" not in all_pdf_text

# 29. Search run history preservation (non-destructive)
def test_29_search_run_history_preservation(db):
    search_service = SearchEngineService(db)
    run_a = search_service.execute_concern_search("abi_hepatotoxicity", reviewer_id="auditor_a")
    matches_a = db.query(SearchMatch).filter_by(search_run_id=run_a["search_run_id"]).count()
    assert matches_a > 0

    run_b = search_service.execute_concern_search("abi_hepatotoxicity", reviewer_id="auditor_b")
    matches_b = db.query(SearchMatch).filter_by(search_run_id=run_b["search_run_id"]).count()
    assert matches_b > 0

    # Old matches from run_a must still exist in DB (never wiped!)
    matches_a_after = db.query(SearchMatch).filter_by(search_run_id=run_a["search_run_id"]).count()
    assert matches_a_after == matches_a, "Historical SearchMatch records must be preserved"
    assert run_a["search_run_id"] != run_b["search_run_id"]

# 30. Dataset isolation & composite case identity
def test_30_dataset_isolation_composite_identity(db):
    case = db.query(CaseRecord).filter_by(case_number="2025AP002474").first()
    assert case is not None
    assert case.id is not None, "CaseRecord must have internal integer PK id"
    assert case.dataset_id is not None

    # Check related events and products link via case_id
    events = db.query(CaseEvent).filter_by(case_id=case.id).all()
    assert len(events) == 9
    products = db.query(CaseProduct).filter_by(case_id=case.id).all()
    assert len(products) >= 2

# 31. Event onset and product field population
def test_31_event_onset_and_product_fields(db):
    case = db.query(CaseRecord).filter_by(case_number="2025AP002474").first()
    events = db.query(CaseEvent).filter_by(case_id=case.id).all()
    # At least some events have event_onset populated
    onsets = [e.event_onset for e in events if e.event_onset]
    assert len(onsets) > 0
    # Multi-event onsets mapped by position have UNCERTAIN status
    uncertain_events = [e for e in events if e.onset_mapping_status == "UNCERTAIN_MAPPED_BY_POSITION"]
    assert len(uncertain_events) > 0

    # Product fields populated
    prods = db.query(CaseProduct).filter_by(case_id=case.id).all()
    assert any(p.brand_name == "APO-ABIRATERONE" for p in prods)
    assert any(p.role == "Suspect" for p in prods)

# 32. Validated Section 16.1 Benchmark Counts on 2026 Abiraterone Excel
def test_32_section_16_1_validated_benchmark_counts(db):
    report_service = ReportService(db)
    table_data = report_service.generate_section_16_1_table("Abiraterone")
    
    risk_counts = {}
    for sec in table_data["table_sections"]:
        for r in sec["risks"]:
            risk_counts[r["risk_term"]] = r["number_of_relevant_cases"]

    expected_benchmarks = {
        "Hepatotoxicity": 14,
        "Cardiac disorders": 0,
        "Osteoporosis including osteoporosis-related fractures": 1,
        "Allergic alveolitis": 0,
        "Increased exposure with food": 0,
        "Rhabdomyolysis/Myopathy": 4,
        "Cataract": 0,
        "Drug drug interaction with CYP2D6 inhibitors": 6,
        "Overdose due to medication error": 1,
        "Use in patients with moderate/severe hepatic impairment and chronic liver disease": 0,
        "Use in patients with severe renal impairment": 2,
        "Use in patients with heart disease as specified in the safety criteria": 0,
        "Use in patients with baseline hepatitis or significant abnormalities of liver function tests": 0
    }

    for risk_term, expected_count in expected_benchmarks.items():
        assert risk_term in risk_counts, f"Risk '{risk_term}' missing from Section 16.1 table"
        actual_count = risk_counts[risk_term]
        assert actual_count == expected_count, (
            f"Benchmark mismatch for '{risk_term}': expected {expected_count}, got {actual_count}"
        )

    assert table_data["total_relevant_cases"] == 28, (
        f"Total retrieved cases mismatch: expected 28, got {table_data['total_relevant_cases']}"
    )

# 33. Assessment status change does not alter Section 16.1 retrieved-case count
def test_33_assessment_status_change_does_not_alter_section_16_1_count(db):
    report_service = ReportService(db)
    
    # Step 1: Initial Section 16.1 table has Hepatotoxicity = 14
    init_table = report_service.generate_section_16_1_table("Abiraterone")
    hep_risk = next(
        r for sec in init_table["table_sections"] for r in sec["risks"] if r["risk_term"] == "Hepatotoxicity"
    )
    assert hep_risk["number_of_relevant_cases"] == 14

    # Step 2: Manually assess candidate cases: one as RELEVANT, one as NOT_RELEVANT
    cases = db.query(CaseRecord).filter_by(product_name="Abiraterone").all()
    c1, c2 = cases[0], cases[1]
    
    for c_obj, status in [(c1, "RELEVANT"), (c2, "NOT_RELEVANT")]:
        ass = db.query(RelevanceAssessment).filter_by(
            case_number=c_obj.case_number, concern_id="abi_hepatotoxicity"
        ).first()
        if not ass:
            ass = RelevanceAssessment(
                case_id=c_obj.id, case_number=c_obj.case_number, concern_id="abi_hepatotoxicity", status=status
            )
            db.add(ass)
        else:
            ass.status = status
    db.commit()

    # Step 3: Regenerate Section 16.1 table
    updated_table = report_service.generate_section_16_1_table("Abiraterone")
    updated_hep_risk = next(
        r for sec in updated_table["table_sections"] for r in sec["risks"] if r["risk_term"] == "Hepatotoxicity"
    )
    
    # The official Section 16.1 count must remain strictly 14 (distinct retrieved cases)
    assert updated_hep_risk["number_of_relevant_cases"] == 14, (
        f"Official Section 16.1 count must NOT change with reviewer assessment, got {updated_hep_risk['number_of_relevant_cases']}"
    )
    # Reviewer assessment metrics must be tracked separately
    assert updated_hep_risk["confirmed_relevant_count"] >= 1
    assert updated_hep_risk["excluded_count"] >= 1

# 34. Auto-execution when no SearchRun exists for a concern
def test_34_auto_execution_when_no_search_run(db):
    report_service = ReportService(db)
    
    # Deactivate active SearchRuns for Rhabdomyolysis
    db.query(SearchRun).filter_by(concern_id="abi_rhabdomyolysis").update({"is_active": False})
    db.commit()

    # Generating Section 16.1 table should automatically execute the configured search
    table_data = report_service.generate_section_16_1_table("Abiraterone")
    rhabdo_risk = next(
        r for sec in table_data["table_sections"] for r in sec["risks"] if "Rhabdomyolysis" in r["risk_term"]
    )
    assert rhabdo_risk["number_of_relevant_cases"] == 4, (
        f"Auto-executed search must yield 4 cases for Rhabdomyolysis, got {rhabdo_risk['number_of_relevant_cases']}"
    )


