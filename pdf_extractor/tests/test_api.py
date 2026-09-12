import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import SAMPLE_DIR

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"


def test_browse_samples():
    res = client.get("/api/files/samples")
    assert res.status_code == 200
    data = res.json()
    assert data["total_found"] >= 1
    assert any(f["filename"] == "test1_basic.pdf" for f in data["files"])


def test_browse_folder_mode_a():
    res = client.post("/api/files/browse", json={"folder_path": str(SAMPLE_DIR)})
    assert res.status_code == 200
    data = res.json()
    assert data["total_found"] >= 8


def test_extract_endpoint_single():
    sample_pdf = SAMPLE_DIR / "test1_basic.pdf"
    res = client.post("/api/extract", json={
        "file_path": str(sample_pdf),
        "filename": "test1_basic.pdf",
        "main_section": "16",
        "target_subsection": "16.1",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["requested_section"] == "16"
    assert data["requested_subsection"] == "16.1"
    assert "16" in data["validation"]["included_sections"]
    assert "16.1" in data["validation"]["included_sections"]
    assert "16.2" in data["validation"]["excluded_sections"]
    assert "txt" in data["download_urls"]
    assert "json" in data["download_urls"]
    assert "csv" in data["download_urls"]
    assert "excel" in data["download_urls"]


def test_extract_endpoint_neglect_table():
    sample_pdf = SAMPLE_DIR / "test8_tables.pdf"
    res = client.post("/api/extract", json={
        "file_path": str(sample_pdf),
        "filename": "test8_tables.pdf",
        "main_section": "16",
        "target_subsection": "16.1",
        "table_mode": "neglect",
        "include_tables": False
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["table_mode"] == "neglect"
    assert data["tables_neglected"] >= 1
    assert data["validation"]["tables_included_count"] == 0
    assert "Safety information text with clinical event tables below." in data["content"]
    assert "Table 1 summarizes all treatment-emergent adverse reactions." in data["content"]
    assert "Headache" not in data["content"]
    assert "Drug A" not in data["content"]



def test_extract_batch_endpoint():
    pdf1 = SAMPLE_DIR / "test1_basic.pdf"
    pdf2 = SAMPLE_DIR / "test2_deep_subsections.pdf"

    res = client.post("/api/extract/batch", json={
        "files": [str(pdf1), str(pdf2)],
        "main_section": "16",
        "target_subsection": "16.1",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["total_documents"] == 2
    assert data["successful"] == 2
    assert len(data["results"]) == 2
    assert data["summary_csv_url"] is not None
    assert data["summary_excel_url"] is not None


def test_upload_and_delete_endpoint():
    sample_pdf = SAMPLE_DIR / "test1_basic.pdf"
    with open(sample_pdf, "rb") as f:
        res = client.post(
            "/api/upload",
            files={"files": ("uploaded_report.pdf", f, "application/pdf")}
        )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["uploaded_count"] == 1
    assert data["files"][0]["original_filename"] == "uploaded_report.pdf"
    saved_name = data["files"][0]["saved_filename"]

    # Test file deletion to ensure no leftover artifacts
    del_res = client.delete(f"/api/upload/{saved_name}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"


def test_extract_html_format_explicit():
    sample_pdf = SAMPLE_DIR / "test1_basic.pdf"
    res = client.post("/api/extract", json={
        "file_path": str(sample_pdf),
        "main_section": "16",
        "target_subsection": "16.1",
        "format": "html"
    })
    assert res.status_code == 200
    data = res.json()
    assert "Data" in data
    assert list(data.keys()) == ["Data"]
    html_str = data["Data"]
    assert html_str.startswith("<!DOCTYPE html>")
    assert '<style>body { font-family: Arial, sans-serif; margin: 40px; background-color: #f9f9f9; } h2 { color: #333; } table { width: 100%; border-collapse: collapse; margin-top: 20px; background-color: #ffffff; box-shadow: 0 2px 5px rgba(0,0,0,0.1); } th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #ddd; } th { background-color: #007BFF; color: white; font-weight: bold; } tr:hover { background-color: #f5f5f5; }</style>' in html_str
    assert "<table>" in html_str
    assert "<th>" in html_str
    assert "<td>" in html_str
    assert "<h2>" in html_str


def test_extract_html_format_tables_pdf():
    sample_pdf = SAMPLE_DIR / "test8_tables.pdf"
    res = client.post("/api/extract", json={
        "file_path": str(sample_pdf),
        "main_section": "16",
        "target_subsection": "16.1",
        "format": "html"
    })
    assert res.status_code == 200
    data = res.json()
    assert "Data" in data
    html_str = data["Data"]
    assert "<th>Adverse Reaction</th>" in html_str
    assert "<th>Drug A (N=100)</th>" in html_str
    assert "<td>Headache</td>" in html_str
    assert "<td>12 (12%)</td>" in html_str


def test_extract_html_natural_query():
    sample_pdf = SAMPLE_DIR / "test1_basic.pdf"
    res = client.post("/api/extract", json={
        "file_path": str(sample_pdf),
        "natural_query": "extract section 16.1, i want resonse in htaml format"
    })
    assert res.status_code == 200
    data = res.json()
    assert "Data" in data
    assert list(data.keys()) == ["Data"]
    assert data["Data"].startswith("<!DOCTYPE html>")


def test_extract_html_dedicated_endpoint():
    sample_pdf = SAMPLE_DIR / "test1_basic.pdf"
    res = client.post("/api/extract/html", json={
        "file_path": str(sample_pdf),
        "main_section": "16",
        "target_subsection": "16.1"
    })
    assert res.status_code == 200
    data = res.json()
    assert "Data" in data
    assert list(data.keys()) == ["Data"]


def test_extract_standard_includes_data_field():
    sample_pdf = SAMPLE_DIR / "test1_basic.pdf"
    res = client.post("/api/extract", json={
        "file_path": str(sample_pdf),
        "main_section": "16",
        "target_subsection": "16.1"
    })
    assert res.status_code == 200
    data = res.json()
    assert "Data" in data
    assert data["Data"] is not None
    assert data["Data"].startswith("<!DOCTYPE html>")
    assert data["status"] == "success"
    assert data["requested_section"] == "16"


def test_extract_html_query_param():
    sample_pdf = SAMPLE_DIR / "test1_basic.pdf"
    res = client.post("/api/extract?format=html", json={
        "file_path": str(sample_pdf),
        "main_section": "16",
        "target_subsection": "16.1"
    })
    assert res.status_code == 200
    data = res.json()
    assert "Data" in data
    assert list(data.keys()) == ["Data"]


def test_extract_batch_html():
    pdf1 = SAMPLE_DIR / "test1_basic.pdf"
    pdf2 = SAMPLE_DIR / "test8_tables.pdf"

    res = client.post("/api/extract/batch", json={
        "files": [str(pdf1), str(pdf2)],
        "main_section": "16",
        "target_subsection": "16.1",
        "format": "html"
    })
    assert res.status_code == 200
    data = res.json()
    assert "Data" in data
    assert data["total_documents"] == 2
    assert "<table>" in data["Data"]


def test_extract_html_user_exact_phrase():
    sample_pdf = SAMPLE_DIR / "test8_tables.pdf"
    res = client.post("/api/extract", json={
        "file_path": str(sample_pdf),
        "natural_query": "in pdf exatractor when i say i want resonse in htaml format so i waNT IT IN THIS FORMAT"
    })
    assert res.status_code == 200
    data = res.json()
    assert "Data" in data
    assert list(data.keys()) == ["Data"]
    html_data = data["Data"]
    assert '<!DOCTYPE html>' in html_data
    assert 'background-color: #007BFF;' in html_data
    assert '<th>Adverse Reaction</th>' in html_data
    assert '<td>Headache</td>' in html_data


def test_html_output_omits_section_numbers_but_extracts_data():
    """Verify that section numbers 16 and 16.1 are omitted from HTML output elements (titles, headings, tables) while section data is extracted."""
    # Test 1: Document without tables (narrative + fallback table)
    sample_basic = SAMPLE_DIR / "test1_basic.pdf"
    res1 = client.post("/api/extract", json={
        "file_path": str(sample_basic),
        "main_section": "16",
        "target_subsection": "16.1",
        "format": "html"
    })
    assert res1.status_code == 200
    html1 = res1.json()["Data"]
    # Check that section numbers 16/16.1 are NOT in title, headings, or table headers/IDs
    assert "<title>Test1 Basic</title>" in html1
    assert "16.1" not in html1
    assert "<h2>16" not in html1
    assert "<th>Section</th>" not in html1
    assert "<td>001</td><td>Heading</td><td>1</td><td>Safety Information</td>" in html1
    assert "Safety Information" in html1
    assert "Adverse Events" in html1

    # Test 2: Document with tables
    sample_tables = SAMPLE_DIR / "test8_tables.pdf"
    res8 = client.post("/api/extract", json={
        "file_path": str(sample_tables),
        "main_section": "16",
        "target_subsection": "16.1",
        "format": "html"
    })
    assert res8.status_code == 200
    html8 = res8.json()["Data"]
    assert "<title>Test8 Tables</title>" in html8
    assert "<h2>Safety Information</h2>" in html8
    assert "<h2>Adverse Events</h2>" in html8
    assert "16.1" not in html8
    assert "<th>Adverse Reaction</th>" in html8
    assert "<td>Headache</td>" in html8



