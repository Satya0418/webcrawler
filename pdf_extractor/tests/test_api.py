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


def test_upload_endpoint():
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
