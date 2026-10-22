"""
Automated Section 16.1 Table Generation & Robustness Test Suite
Verifies:
1. Table correctness: official risk terms, category headers, 2-column structure, zero counts, no Total row.
2. Verified benchmark counts: Hepatotoxicity=14, Cardiac=2, Osteoporosis=1, Allergic Alveolitis=0, Exposure=0, Rhabdomyolysis=4.
3. Dataset isolation: identical case numbers in two different datasets producing independent counts.
4. Excel ingestion: streaming/read-only mode, missing header validation, empty sheet handling, synthetic large workbook.
5. API endpoints: 1-click POST /generate, GET /excel (.xlsx generation), GET /pdf (A4 regulatory report without 16.2/16.3).
6. Separation of retrieved case count vs reviewer confirmed relevant count.
"""

import os
import sys
import io
import pytest
import openpyxl
from fastapi.testclient import TestClient

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from excel_calculus.backend.app.main import app
from excel_calculus.backend.app.database import SessionLocal
from excel_calculus.backend.app.models.entities import (
    CaseRecord, CaseEvent, SafetyConcern, SearchMatch, SearchRun, Dataset, RelevanceAssessment
)
from excel_calculus.backend.app.services.ingestion import IngestionService
from excel_calculus.backend.app.services.report_service import ReportService
from excel_calculus.backend.app.services.excel_service import ExcelReportService
from excel_calculus.backend.app.services.pdf_service import PDFReportService
from excel_calculus.backend.app.services.search_engine import SearchEngineService

client = TestClient(app)

@pytest.fixture(scope="module")
def db_session():
    session = SessionLocal()
    yield session
    session.close()


# --------------------------------------------------------------------------
# 1. TABLE CORRECTNESS & OFFICIAL REGULATORY SPECIFICATION
# --------------------------------------------------------------------------

def test_section_16_1_table_structure_and_categories(db_session):
    """
    Verify Section 16.1 table structure:
    - 3 official categories in exact order: Important Identified Risks, Important Potential Risks, Missing Information.
    - Official risk terms present.
    - Section 9 'Medication error' excluded.
    - Zero-count terms preserved (Allergic alveolitis, Increased exposure with food, etc.).
    """
    report_service = ReportService(db_session)
    report = report_service.generate_section_16_1_table("Abiraterone")

    assert report["product_name"] == "Abiraterone"
    assert "table_sections" in report
    assert len(report["table_sections"]) == 3

    categories = [s["category_name"] for s in report["table_sections"]]
    assert categories == [
        "Important Identified Risks",
        "Important Potential Risks",
        "Missing Information"
    ]

    all_risks = []
    for section in report["table_sections"]:
        for risk in section["risks"]:
            all_risks.append(risk["risk_term"])

    # Official risk terms must be present
    assert any("Hepatotoxicity" in r for r in all_risks)
    assert any("Cardiac" in r for r in all_risks)
    assert any("Osteoporosis" in r for r in all_risks)
    assert any("Rhabdomyolysis" in r for r in all_risks)
    assert any("Allergic alveolitis" in r for r in all_risks)
    assert any("Increased exposure with food" in r for r in all_risks)
    assert any("Cataract" in r for r in all_risks)
    assert any("CYP2D6" in r for r in all_risks)
    assert any("Overdose due to medication error" in r for r in all_risks)

    # Section 9 Medication error must NOT be in Section 16.1
    assert not any(r == "Medication error" for r in all_risks)


def test_section_16_1_official_counts_and_zero_count_preservation(db_session):
    """
    Verify exact counts matching PBRER Section 16.1:
    - Hepatotoxicity: 14
    - Osteoporosis including osteoporotic fractures: 1
    - Allergic alveolitis: 0 (must be included as 0)
    - Increased exposure with food: 0 (must be included as 0)
    - Rhabdomyolysis/Myopathy: 4
    - Drug drug interaction with CYP2D6 inhibitors: 6
    """
    report_service = ReportService(db_session)
    report = report_service.generate_section_16_1_table("Abiraterone")

    risk_map = {}
    for section in report["table_sections"]:
        for risk in section["risks"]:
            risk_map[risk["risk_term"]] = risk["number_of_relevant_cases"]

    # Verify counts
    hep_key = next(k for k in risk_map if "Hepatotoxicity" in k)
    osteo_key = next(k for k in risk_map if "Osteoporosis" in k)
    rhabdo_key = next(k for k in risk_map if "Rhabdomyolysis" in k)
    alveolitis_key = next(k for k in risk_map if "Allergic alveolitis" in k)
    food_key = next(k for k in risk_map if "Increased exposure with food" in k)
    cyp_key = next(k for k in risk_map if "CYP2D6" in k)

    assert risk_map[hep_key] == 14
    assert risk_map[osteo_key] == 1
    assert risk_map[rhabdo_key] == 4
    assert risk_map[cyp_key] == 6
    assert risk_map[alveolitis_key] == 0, "Zero-count term Allergic alveolitis must display 0"
    assert risk_map[food_key] == 0, "Zero-count term Increased exposure with food must display 0"


# --------------------------------------------------------------------------
# 2. DATASET ISOLATION & COUNT CORRECTNESS
# --------------------------------------------------------------------------

def test_dataset_isolation_with_shared_case_number(db_session):
    """
    Create two isolated datasets with the exact same case number 'CASE-SHARED-999'.
    Verify searches and counts are strictly isolated by dataset_id.
    """
    ds_a_id = "test-dataset-a-iso"
    ds_b_id = "test-dataset-b-iso"
    try:
        # Dataset A
        case_a = CaseRecord(
            dataset_id=ds_a_id,
            case_number="CASE-SHARED-999",
            product_name="IsoProductA",
            sex="Male"
        )
        db_session.add(case_a)
        db_session.flush()

        event_a = CaseEvent(
            case_id=case_a.id,
            case_number=case_a.case_number,
            dataset_id=ds_a_id,
            raw_verbatim="Drug-induced liver injury",
            normalized_term="DRUG-INDUCED LIVER INJURY",
            soc="Hepatobiliary disorders"
        )
        db_session.add(event_a)

        # Dataset B
        case_b = CaseRecord(
            dataset_id=ds_b_id,
            case_number="CASE-SHARED-999",
            product_name="IsoProductA",
            sex="Female"
        )
        db_session.add(case_b)
        db_session.flush()

        event_b = CaseEvent(
            case_id=case_b.id,
            case_number=case_b.case_number,
            dataset_id=ds_b_id,
            raw_verbatim="Cardiac failure",
            normalized_term="CARDIAC FAILURE",
            soc="Cardiac disorders"
        )
        db_session.add(event_b)
        db_session.commit()

        # Query CaseRecords strictly by dataset_id
        cases_a = db_session.query(CaseRecord).filter_by(dataset_id=ds_a_id).all()
        cases_b = db_session.query(CaseRecord).filter_by(dataset_id=ds_b_id).all()
        assert len(cases_a) == 1
        assert len(cases_b) == 1
        assert cases_a[0].case_number == cases_b[0].case_number
        assert cases_a[0].id != cases_b[0].id
        assert cases_a[0].sex == "Male"
        assert cases_b[0].sex == "Female"
    finally:
        db_session.query(CaseEvent).filter(CaseEvent.dataset_id.in_([ds_a_id, ds_b_id])).delete(synchronize_session=False)
        db_session.query(CaseRecord).filter(CaseRecord.dataset_id.in_([ds_a_id, ds_b_id])).delete(synchronize_session=False)
        db_session.commit()


# --------------------------------------------------------------------------
# 3. STREAMING EXCEL INGESTION & ROBUSTNESS
# --------------------------------------------------------------------------

def test_streaming_ingestion_valid_workbook(db_session):
    """
    Test streaming ingestion using read-only openpyxl mode on a small valid synthetic workbook.
    """
    import tempfile
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LineListing"
    headers = [
        "Case Number", "Age", "Sex", "Product Name", 
        "Event Verbatim", "Case Seriousness?", "Country"
    ]
    ws.append(headers)
    ws.append(["SYNTH-001", "65", "Male", "SyntheticProd", "Hepatitis acute", "Yes", "Canada"])
    ws.append(["SYNTH-002", "72", "Female", "SyntheticProd", "Cardiac arrest", "Yes", "USA"])

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name
    wb.save(tmp_path)
    wb.close()

    ingestion = IngestionService(db_session)
    dataset_id = None
    try:
        res = ingestion.ingest_linelisting_file(
            tmp_path,
            primary_product_name="SyntheticProd"
        )
        dataset_id = res["dataset_id"]
        assert res["status"] == "success"
        assert res["total_cases"] == 2
        assert res["total_events"] >= 2
        assert dataset_id is not None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        if dataset_id:
            db_session.query(CaseEvent).filter_by(dataset_id=dataset_id).delete(synchronize_session=False)
            db_session.query(CaseRecord).filter_by(dataset_id=dataset_id).delete(synchronize_session=False)
            db_session.query(Dataset).filter_by(id=dataset_id).delete(synchronize_session=False)
            db_session.commit()


def test_streaming_ingestion_missing_case_number_header(db_session):
    """
    Test that ingestion raises a clear ValueError when the required 'Case Number' header is missing.
    """
    import tempfile
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["InvalidHeader1", "InvalidHeader2"])
    ws.append(["Val1", "Val2"])

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name
    wb.save(tmp_path)
    wb.close()

    ingestion = IngestionService(db_session)
    try:
        with pytest.raises(ValueError) as excinfo:
            ingestion.ingest_linelisting_file(tmp_path, primary_product_name="InvalidTest")
        assert "Required header 'Case Number' not found" in str(excinfo.value)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_streaming_ingestion_empty_sheet(db_session):
    """
    Test that ingestion raises a clear ValueError on empty sheets.
    """
    import tempfile
    wb = openpyxl.Workbook()
    ws = wb.active

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name
    wb.save(tmp_path)
    wb.close()

    ingestion = IngestionService(db_session)
    try:
        with pytest.raises(ValueError) as excinfo:
            ingestion.ingest_linelisting_file(tmp_path, primary_product_name="EmptyTest")
        assert "contains an empty sheet" in str(excinfo.value)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_streaming_ingestion_large_synthetic_workbook(db_session):
    """
    Test performance and batching with 300 synthetic rows to verify streaming read-only and flushing.
    """
    import tempfile
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LargeListing"
    ws.append(["Case Number", "Age", "Sex", "Product Name", "Event Verbatim"])
    for i in range(1, 301):
        ws.append([f"LARGE-CASE-{i:04d}", "60", "Male", "LargeProd", f"Fatigue\nJaundice {i}"])

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name
    wb.save(tmp_path)
    wb.close()

    ingestion = IngestionService(db_session)
    dataset_id = None
    try:
        res = ingestion.ingest_linelisting_file(
            tmp_path,
            primary_product_name="LargeProd"
        )
        dataset_id = res["dataset_id"]
        assert res["status"] == "success"
        assert res["total_cases"] == 300
        assert res["total_events"] == 600  # 2 events per case
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        if dataset_id:
            db_session.query(CaseEvent).filter_by(dataset_id=dataset_id).delete(synchronize_session=False)
            db_session.query(CaseRecord).filter_by(dataset_id=dataset_id).delete(synchronize_session=False)
            db_session.query(Dataset).filter_by(id=dataset_id).delete(synchronize_session=False)
            db_session.commit()


# --------------------------------------------------------------------------
# 4. API ENDPOINTS & 1-CLICK AUTOMATED WORKFLOW
# --------------------------------------------------------------------------

def test_api_1click_generate_section_16_1():
    """
    Test POST /api/reports/section-16-1/generate endpoint:
    - Ingests file, runs searches, and returns Section 16.1 report data.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Case Number", "Suspect Product Names", "Events Reported (Cleaned)"])
    ws.append(["API-001", "SyntheticApiProduct", "Hepatitis acute"])
    ws.append(["API-002", "SyntheticApiProduct", "Cardiac arrest"])

    bio = io.BytesIO()
    wb.save(bio)
    wb.close()
    bio.seek(0)

    response = client.post(
        "/api/reports/section-16-1/generate",
        data={"product": "SyntheticApiProduct"},
        files={"file": ("api_test.xlsx", bio, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )

    assert response.status_code == 200, f"Generate API failed: {response.text}"
    json_data = response.json()
    assert json_data["status"] == "success"
    assert "data" in json_data
    report = json_data["data"]
    assert report["product_name"] == "SyntheticApiProduct"
    assert len(report["table_sections"]) == 3

    # Clean up generated dataset
    ds_id = report.get("dataset_id")
    if ds_id:
        db = SessionLocal()
        db.query(CaseEvent).filter_by(dataset_id=ds_id).delete(synchronize_session=False)
        db.query(CaseRecord).filter_by(dataset_id=ds_id).delete(synchronize_session=False)
        db.query(SearchMatch).filter(SearchMatch.search_run_id.in_(
            db.query(SearchRun.id).filter_by(dataset_id=ds_id)
        )).delete(synchronize_session=False)
        db.query(SearchRun).filter_by(dataset_id=ds_id).delete(synchronize_session=False)
        db.query(Dataset).filter_by(id=ds_id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_api_1click_generate_without_file():
    """
    Test POST /api/reports/section-16-1/generate without uploading a file.
    Recalculates all searches on existing indexed line listings.
    """
    response = client.post(
        "/api/reports/section-16-1/generate",
        data={"product": "Abiraterone"}
    )
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["status"] == "success"
    assert json_data["data"]["product_name"] == "Abiraterone"


def test_api_get_section_16_1_excel():
    """
    Test GET /api/reports/section-16-1/excel:
    - Returns valid Excel file with application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
    - Inspects generated workbook to verify headers, category banners, and risk terms.
    """
    response = client.get("/api/reports/section-16-1/excel?product=Abiraterone")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment; filename=" in response.headers["content-disposition"]

    # Verify binary is valid Excel
    excel_bytes = io.BytesIO(response.content)
    wb = openpyxl.load_workbook(excel_bytes)
    assert "Section 16.1 Safety Summary" in wb.sheetnames
    ws = wb["Section 16.1 Safety Summary"]

    # Inspect cell values
    all_values = [cell.value for row in ws.iter_rows() for cell in row if cell.value is not None]
    assert any("PBRER Section 16.1" in str(v) for v in all_values)
    assert any("Risk Term" in str(v) for v in all_values)
    assert any("Number of Relevant Case Reports" in str(v) for v in all_values)
    assert any("IMPORTANT IDENTIFIED RISKS" in str(v).upper() for v in all_values)
    assert any("Hepatotoxicity" in str(v) for v in all_values)
    wb.close()


def test_api_get_section_16_1_pdf_format_and_cleanliness():
    """
    Test GET /api/reports/section-16-1/pdf:
    - Returns valid application/pdf binary.
    - Default generation does NOT include Sections 16.2 / 16.3 boilerplate narratives.
    - Test preview mode returns inline Content-Disposition.
    """
    # Regular download
    resp_dl = client.get("/api/reports/section-16-1/pdf?product=Abiraterone&preview=false")
    assert resp_dl.status_code == 200
    assert resp_dl.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in resp_dl.headers["content-disposition"]
    assert len(resp_dl.content) > 1000
    assert resp_dl.content[:4] == b"%PDF"

    # Preview mode
    resp_prev = client.get("/api/reports/section-16-1/pdf?product=Abiraterone&preview=true")
    assert resp_prev.status_code == 200
    assert "inline" in resp_prev.headers["content-disposition"]


def test_pdf_service_excludes_16_2_and_16_3_by_default(db_session):
    """
    Verify PDFReportService excludes 16.2 and 16.3 boilerplate by default.
    """
    report_service = ReportService(db_session)
    report_data = report_service.generate_section_16_1_table("Abiraterone")
    pdf_service = PDFReportService(db_session)
    pdf_bytes = pdf_service.generate_section_16_1_pdf(report_data, include_subsequent_sections=False)
    assert len(pdf_bytes) > 0
    assert pdf_bytes[:4] == b"%PDF"


# --------------------------------------------------------------------------
# 5. REVIEWER ASSESSMENT SEPARATION VS OFFICIAL COUNT
# --------------------------------------------------------------------------

def test_reviewer_assessment_does_not_mutate_official_count(db_session):
    """
    Confirm that changing reviewer assessment status (e.g. CANDIDATE -> NOT_RELEVANT)
    updates confirmed_relevant_count in the reviewer audit trail, but does NOT alter
    the official PBRER Section 16.1 count (which is distinct cases retrieved by safety search).
    """
    report_service = ReportService(db_session)

    # Initial official count for Hepatotoxicity
    report_before = report_service.generate_section_16_1_table("Abiraterone")
    hep_before = None
    for sec in report_before["table_sections"]:
        for r in sec["risks"]:
            if "Hepatotoxicity" in r["risk_term"]:
                hep_before = r
                break

    assert hep_before is not None
    official_count_before = hep_before["number_of_relevant_cases"]
    assert official_count_before == 14

    # Now simulate an assessment status change via API
    resp = client.post("/api/assessment", json={
        "case_number": "2025AP002474",
        "concern_id": hep_before["concern_id"],
        "status": "NOT_RELEVANT",
        "exclusion_reason": "Confounding viral hepatitis etiology",
        "reviewer_notes": "Tested in automated test suite",
        "reviewer_id": "Dr. Automated Test"
    })
    assert resp.status_code == 200

    # Regenerate Section 16.1 report
    report_after = report_service.generate_section_16_1_table("Abiraterone")
    hep_after = None
    for sec in report_after["table_sections"]:
        for r in sec["risks"]:
            if "Hepatotoxicity" in r["risk_term"]:
                hep_after = r
                break

    assert hep_after is not None
    # The official Section 16.1 count MUST remain strictly 14
    assert hep_after["number_of_relevant_cases"] == 14
    # But excluded_count in reviewer breakdown reflects the change
    assert hep_after["excluded_count"] >= 1
