import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import SAMPLE_DIR
from backend.services.scanner_service import (
    ScannerService,
    extract_product_name_from_file,
    normalize_product_name,
    compute_file_sha256,
)

client = TestClient(app)


def test_product_name_extraction():
    """Validates heuristic product name extraction and normalization."""
    p1 = Path("/dummy/path/Lipitor_10mg_PI.pdf")
    name1 = extract_product_name_from_file(p1)
    assert "Lipitor" in name1
    assert normalize_product_name(name1) == "lipitor"

    p2 = Path("/dummy/path/Ozempic_injection_FDA_label.pdf")
    name2 = extract_product_name_from_file(p2)
    assert "Ozempic" in name2
    assert normalize_product_name(name2) == "ozempic"

    p3 = Path("/dummy/path/Atorvastatin_Calcium_Tablets.pdf")
    name3 = extract_product_name_from_file(p3)
    assert "Atorvastatin" in name3


def test_scanner_service_delta_and_client_api(tmp_path: Path):
    """
    End-to-end integration test:
    1. Sets up a temporary watch directory with a sample PDF.
    2. Runs scanner: verifies new file is extracted.
    3. Runs scanner again: verifies delta detection skips unchanged file.
    4. Tests client API endpoints: GET, POST, HTML format, search, and list.
    """
    from backend.database.db import get_db_session
    from backend.database.models import ProductSectionRecord

    test_filename = "Lipitor_Sample_PI.pdf"

    # Hermetic isolation: ensure no stale record exists before starting
    with get_db_session() as session:
        session.query(ProductSectionRecord).filter_by(filename=test_filename).delete()

    watch_folder = tmp_path / "test_watch_pdfs"
    watch_folder.mkdir(parents=True, exist_ok=True)

    # Copy test8_tables.pdf (which has Section 16 and Section 16.1 with tables)
    source_sample = SAMPLE_DIR / "test8_tables.pdf"
    assert source_sample.exists(), "Sample test8_tables.pdf must exist for test"
    dest_pdf = watch_folder / test_filename
    shutil.copy(source_sample, dest_pdf)

    # Initialize a test scanner targeting our temporary folder
    test_scanner = ScannerService(watch_dir=watch_folder, interval_minutes=30, target_section="16")

    # Run 1: First scan should process the new file
    stats1 = test_scanner.scan_once()
    assert stats1["status"] == "completed"
    assert stats1["files_scanned"] == 1
    assert stats1["files_processed"] == 1
    assert stats1["files_skipped"] == 0


    # Run 2: Second scan without modifications should SKIP the file (Delta efficiency)
    stats2 = test_scanner.scan_once()
    assert stats2["files_scanned"] == 1
    assert stats2["files_processed"] == 0
    assert stats2["files_skipped"] == 1

    # Test 3: Client API query via GET
    res_get = client.get("/api/v1/products/section-16", params={"product_name": "Lipitor"})
    assert res_get.status_code == 200, f"Failed GET: {res_get.text}"
    data_get = res_get.json()
    assert data_get["status"] == "success"
    assert "Lipitor" in data_get["product_name"]
    assert data_get["target_section"] == "16"
    assert "data" in data_get
    assert "text" in data_get["data"]
    assert len(data_get["data"]["text"]) > 0

    # Test 4: Client API query via POST JSON body
    res_post = client.post("/api/v1/products/section-16", json={"product_name": "Lipitor"})
    assert res_post.status_code == 200
    assert res_post.json()["status"] == "success"

    # Test 5: Client API query requesting HTML format
    res_html = client.get("/api/v1/products/section-16", params={"product_name": "Lipitor", "format": "html"})
    assert res_html.status_code == 200
    assert "text/html" in res_html.headers.get("content-type", "")
    assert "<" in res_html.text and ">" in res_html.text

    # Test 6: Client autocomplete/search endpoint
    res_search = client.get("/api/v1/products/search", params={"query": "lipi"})
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert search_data["status"] == "success"
    assert search_data["count"] >= 1
    assert any("Lipitor" in item["product_name"] for item in search_data["results"])

    # Test 7: Client product listing endpoint
    res_list = client.get("/api/v1/products/list")
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["total"] >= 1

    # Test 8: Non-existent product returns 404
    res_404 = client.get("/api/v1/products/section-16", params={"product_name": "NonExistentDrugXYZ999"})
    assert res_404.status_code == 404

    # Test 9: Scanner status endpoint
    res_status = client.get("/api/v1/scanner/status")
    assert res_status.status_code == 200
    assert "status" in res_status.json()

    # Test 10: Health check endpoint includes scanner and DB
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    health_data = res_health.json()
    assert health_data["status"] == "healthy"
    assert "database" in health_data
    assert "background_scanner" in health_data

    # Test 11: Client query specifically for Subsection 16.1
    res_16_1 = client.get("/api/v1/products/section-16", params={"product_name": "Lipitor", "subsection": "16.1"})
    assert res_16_1.status_code == 200
    data_16_1 = res_16_1.json()
    assert data_16_1["status"] == "success"
    assert data_16_1["target_subsection"] == "16.1"
    assert "16.1" in data_16_1["section_title"]
    assert "html_snippet" in data_16_1["data"]
    assert "<article" in data_16_1["data"]["html_snippet"] or "<section" in data_16_1["data"]["html_snippet"]
    assert "<table" in data_16_1["data"]["html_snippet"]

    # Test 12: Client query specifically for Subsection 16.1 in raw HTML format
    res_16_1_html = client.get("/api/v1/products/section-16", params={"product_name": "Lipitor", "subsection": "16.1", "format": "html"})
    assert res_16_1_html.status_code == 200
    assert "text/html" in res_16_1_html.headers.get("content-type", "")
    assert "<!DOCTYPE html>" in res_16_1_html.text
    assert "16.1" in res_16_1_html.text
    assert "<table" in res_16_1_html.text

    # Test 13: Client query for embeddable HTML snippet (no <!DOCTYPE html>)
    res_embed = client.get("/api/v1/products/section-16", params={"product_name": "Lipitor", "subsection": "16.1", "format": "html", "embed_only": "true"})
    assert res_embed.status_code == 200
    assert "<!DOCTYPE html>" not in res_embed.text
    assert "<section" in res_embed.text or "<article" in res_embed.text

