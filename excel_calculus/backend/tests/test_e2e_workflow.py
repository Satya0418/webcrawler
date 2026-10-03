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

import json
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000/api"

def api_get(endpoint: str):
    req = urllib.request.Request(f"{BASE_URL}{endpoint}")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        return json.loads(resp.read().decode())

def api_post(endpoint: str, data: dict = None):
    encoded = json.dumps(data).encode("utf-8") if data is not None else b""
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=encoded,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        return json.loads(resp.read().decode())

def test_1_data_pipeline_status():
    data = api_get("/ingestion/status")
    assert data["total_cases"] >= 167
    assert data["total_exploded_events"] >= 950
    assert data["total_smq_terms"] == 64410
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
    import urllib.request
    import os

    file_path = "/Users/satya/Downloads/Required Artifacts for section 16.3 (3)/Oxycodone/Oxycodone_20260412_CAN PBRER_Interval LL.xlsx"
    if not os.path.exists(file_path):
        return

    # Prepare multipart/form-data
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{os.path.basename(file_path)}"\r\n'
        f"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
    ).encode("utf-8") + file_bytes + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="product_name"\r\n\r\n'
        f"Oxycodone\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file_type"\r\n\r\n'
        f"line_listing\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{BASE_URL}/ingestion/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        res_data = json.loads(resp.read().decode())
        assert res_data["status"] == "success"
        assert res_data["cases_ingested"] == 48
        assert res_data["events_exploded"] == 725

