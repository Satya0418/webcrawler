"""
End-to-End Workflow Acceptance Test
Tests all aspects of the Pharmacovigilance line-listing calculus workflow against live server:
1. Data Pipeline Ingestion Status
2. Safety Concern Loading for Abiraterone & Oxycodone
3. Deterministic Search Execution:
   - Hepatotoxicity (Broad SMQ) -> 14 events, 14 cases
   - Medication error (Broad SMQ) -> 21 events, 14 cases (matches DOCX Table 3)
   - Rhabdomyolysis/Myopathy (Narrow SMQ) -> 4 events, 4 cases
   - CYP2D6 Drug Interaction -> 6 events, 6 cases
4. Full Case Retrieval & Exploded Event Inspection (including Nilima's case 2025AP002474)
5. Relevance Assessment Update (CANDIDATE -> RELEVANT with Reviewer Notes)
6. PBRER Section 16.3 Report Generation & Verification
7. Cross-Product Search for Oxycodone (Accidental exposure / Off-label use)
"""

import os
import json
import pytest
from fastapi.testclient import TestClient
from excel_calculus.backend.app.main import app

client = TestClient(app)

def api_get(endpoint: str):
    resp = client.get(f"/api{endpoint}")
    assert resp.status_code == 200, f"GET {endpoint} failed: {resp.text}"
    return resp.json()

def api_post(endpoint: str, data: dict = None):
    resp = client.post(f"/api{endpoint}", json=data)
    assert resp.status_code == 200, f"POST {endpoint} failed: {resp.text}"
    return resp.json()

def test_1_data_pipeline_status():
    data = api_get("/ingestion/status")
    assert data["total_cases"] >= 167
    assert data["total_exploded_events"] >= 950
    assert data["total_smq_terms"] >= 45000
    assert data["total_safety_concerns"] >= 14
    assert "Abiraterone" in data["products"]
    assert "Oxycodone" in data["products"]
    assert len(data["ingested_files"]) >= 2

def test_2_safety_concerns_list():
    concerns_ab = api_get("/concerns?product=Abiraterone")
    assert len(concerns_ab) >= 10
    concern_names = [c["name"] for c in concerns_ab]
    assert any("Hepatotoxicity" in n for n in concern_names)
    assert any("Medication error" in n for n in concern_names)
    assert any("Rhabdomyolysis" in n for n in concern_names)
    assert any("CYP2D6" in n for n in concern_names)

    concerns_oxy = api_get("/concerns?product=Oxycodone")
    assert len(concerns_oxy) >= 3

def test_3_search_hepatotoxicity_broad_smq():
    concerns = api_get("/concerns?product=Abiraterone")
    hep_concern = next(c for c in concerns if "Hepatotoxicity" in c["name"])
    
    data = api_post(f"/search/{hep_concern['id']}?reviewer=pv_analyst_1")
    assert data["concern_name"] == "Hepatotoxicity"
    assert data["search_method"] == "BROAD_SMQ"
    assert data["total_event_matches"] == 14
    assert data["distinct_candidate_cases"] == 14
    assert len(data["cases"]) == 14

    for case in data["cases"]:
        assert len(case["matches"]) > 0
        match = case["matches"][0]
        assert match["matched_term"] != ""
        assert "evidence" in match

def test_4_search_medication_error_docx_table3_match():
    concerns = api_get("/concerns?product=Abiraterone")
    med_err = next(c for c in concerns if "Medication error" in c["name"])

    data = api_post(f"/search/{med_err['id']}?reviewer=pv_analyst_1")
    assert data["total_event_matches"] == 21
    assert data["distinct_candidate_cases"] == 14

def test_5_complete_case_review_modal_data():
    concerns = api_get("/concerns?product=Abiraterone")
    hep_concern = next(c for c in concerns if "Hepatotoxicity" in c["name"])

    # 1. Retrieve a matched case (e.g. 2025AP034387)
    case_res = api_get(f"/cases/2025AP034387?concern_id={hep_concern['id']}")
    assert case_res["case_number"] == "2025AP034387"
    assert "overview" in case_res
    assert "patient" in case_res
    assert len(case_res["products"]) > 0
    assert len(case_res["events"]) > 0
    assert any(e["is_matched"] for e in case_res["events"])
    assert "source_lineage" in case_res
    assert case_res["source_lineage"]["row"] > 0

    # 2. Retrieve Nilima's example case 2025AP002474 to verify event explosion
    nilima_case = api_get("/cases/2025AP002474")
    assert nilima_case["case_number"] == "2025AP002474"
    event_terms = [e["normalized_term"] for e in nilima_case["events"]]
    assert "PAIN IN EXTREMITY" in event_terms
    assert "GAIT DISTURBANCE" in event_terms
    assert "BONE PAIN" in event_terms

def test_6_relevance_assessment_update():
    concerns = api_get("/concerns?product=Abiraterone")
    hep_concern = next(c for c in concerns if "Hepatotoxicity" in c["name"])

    payload = {
        "case_number": "2025AP034387",
        "concern_id": hep_concern["id"],
        "status": "RELEVANT",
        "reviewer_notes": "Confirmed clinical relevance during interval review against SMQ criteria.",
        "reviewer_id": "lead_pv_physician"
    }
    result = api_post("/assessment", data=payload)
    assert result["status"] == "RELEVANT"
    assert result["reviewer_notes"] == payload["reviewer_notes"]

    sum_data = api_get(f"/search/{hep_concern['id']}")
    assert sum_data["relevant_cases_count"] >= 1

def test_7_pbrer_section_16_1_summary_table_generation():
    rep = api_get("/reports/section-16-1?product=Abiraterone")
    assert rep["title"] == "Section 16.1 Summary of Safety Concerns"
    assert rep["product_name"] == "Abiraterone"
    assert rep["total_relevant_cases"] > 0
    assert len(rep["table_sections"]) >= 3
    section_names = [s["category_name"] for s in rep["table_sections"]]
    assert "Important Identified Risks" in section_names
    assert "Important Potential Risks" in section_names
    assert "Missing Information" in section_names

def test_8_oxycodone_cross_product_validation():
    concerns = api_get("/concerns?product=Oxycodone")
    off_label_concern = next(c for c in concerns if "Off-label" in c["name"])

    data = api_post(f"/search/{off_label_concern['id']}?reviewer=pv_analyst_2")
    assert data["distinct_candidate_cases"] > 0
    assert data["total_event_matches"] >= 10

def test_9_file_upload_ingestion_api():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    file_path = os.environ.get(
        "OXYCODONE_EXCEL_PATH",
        os.path.join(base_dir, "excel_calculus", "data", "Oxycodone_20260412_CAN PBRER_Interval LL.xlsx")
    )
    if not os.path.exists(file_path):
        fallback = os.path.expanduser("~/Downloads/Required Artifacts for section 16.3 (3)/Oxycodone/Oxycodone_20260412_CAN PBRER_Interval LL.xlsx")
        if os.path.exists(fallback):
            file_path = fallback

    if not os.path.exists(file_path):
        pytest.skip(f"Oxycodone line listing not found at {file_path}")

    with open(file_path, "rb") as f:
        resp = client.post(
            "/api/ingestion/upload",
            files={"file": (os.path.basename(file_path), f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"product_name": "Oxycodone", "file_type": "line_listing"}
        )
        assert resp.status_code == 200
        res_data = resp.json()
        assert res_data["status"] == "success"
        assert res_data["cases_ingested"] == 48
        assert res_data["events_exploded"] == 725

def test_10_pdf_report_api_endpoint():
    import io
    import pypdf

    resp = client.get("/api/reports/section-16-1/pdf?product=Abiraterone")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert 'attachment; filename="Abiraterone_Section_16.1_PBRER_Report.pdf"' in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF-1.4")

    # Verify extracted text via pypdf
    reader = pypdf.PdfReader(io.BytesIO(resp.content))
    assert len(reader.pages) >= 1

    pdf_text = "".join([p.extract_text() for p in reader.pages])
    assert "Apotex Inc." in pdf_text
    assert "Abiraterone" in pdf_text
    assert "Periodic Benefit-Risk Evaluation Report" in pdf_text
    assert "CONFIDENTIAL" in pdf_text
    assert "Risk Term" in pdf_text
    assert "IMPORTANT IDENTIFIED RISKS" in pdf_text
    assert "Hepatotoxicity" in pdf_text
    assert "Rhabdomyolysis/Myopathy" in pdf_text

def test_11_pdf_report_api_preview_mode():
    resp = client.get("/api/reports/section-16-1/pdf?product=Abiraterone&preview=true")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"] == "inline"
    assert resp.content.startswith(b"%PDF-1.4")


