import io
import re
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import BASE_DIR, SAMPLE_DIR
from backend.database.db import check_db_health
from backend.services.scanner_service import scanner_service

client = TestClient(app)


def test_nginx_conf_file_and_directives():
    """Validates nginx/nginx.conf structure, directives, headers, and timeouts."""
    nginx_conf_path = BASE_DIR / "nginx" / "nginx.conf"
    assert nginx_conf_path.exists(), "nginx/nginx.conf file does not exist"

    content = nginx_conf_path.read_text(encoding="utf-8")

    # 1. Reverse proxy destination
    assert "proxy_pass http://pdf-extractor:8000;" in content or "proxy_pass http://pdf_backend" in content, (
        "Nginx must reverse proxy to backend application container"
    )

    # 2. Body size limit
    assert "client_max_body_size 100M;" in content, (
        "client_max_body_size must be configured to 100M"
    )

    # 3. Proxy timeouts
    assert "proxy_connect_timeout 60s;" in content
    assert re.search(r"proxy_send_timeout\s+\d+s;", content)
    assert "proxy_read_timeout 300s;" in content

    # 4. Proxy headers
    assert "proxy_set_header Host $host;" in content
    assert "proxy_set_header X-Real-IP $remote_addr;" in content
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in content
    assert "proxy_set_header X-Forwarded-Proto" in content

    # 5. Server name and port
    assert re.search(r"server_name\s+_[^;]*;", content)
    assert re.search(r"listen\s+(80|443)", content)

    # 6. Syntax balance check (equal opening and closing braces)
    open_braces = content.count("{")
    close_braces = content.count("}")
    assert open_braces == close_braces, f"Mismatched braces in nginx.conf: {open_braces} vs {close_braces}"


def test_docker_compose_architecture():
    """Validates docker-compose.yml services, ports, exposure, and dependencies."""
    compose_path = BASE_DIR / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml does not exist"

    content = compose_path.read_text(encoding="utf-8")

    # Nginx service checks
    assert "image: nginx:alpine" in content
    assert "container_name: pdf_extractor_nginx" in content
    assert "80:80" in content or "443" in content

    # Nginx volume mount for nginx.conf
    assert "./nginx/nginx.conf:/etc/nginx/nginx.conf:ro" in content

    # Nginx dependency on pdf-extractor
    assert "pdf-extractor" in content

    # pdf-extractor exposes 8000 internally without publishing to host
    assert '8000:8000' not in content, "pdf-extractor should not publicly publish port 8000"
    assert '"8000"' in content or "'8000'" in content

    # Database is private to Docker network (no public 5432:5432 mapping)
    assert '5432:5432' not in content, "PostgreSQL should not publicly publish port 5432"

    # Persistent storage volumes preserved
    assert "postgres_data:" in content
    assert "pdf_data:" in content
    assert "./watch_pdfs:/app/watch_pdfs" in content
    assert "./uploads:/app/uploads" in content
    assert "./outputs:/app/outputs" in content


def test_frontend_loads_with_proxy_headers():
    """Verifies that the root frontend HTML loads cleanly behind reverse proxy headers."""
    res = client.get(
        "/",
        headers={
            "Host": "localhost",
            "X-Real-IP": "192.168.1.100",
            "X-Forwarded-For": "192.168.1.100",
            "X-Forwarded-Proto": "http",
        },
    )
    assert res.status_code == 200
    assert "<!DOCTYPE html>" in res.text
    assert "/static/styles.css" in res.text
    assert "/static/app.js" in res.text


def test_static_assets_preserve_paths():
    """Verifies that static assets (/static/styles.css and /static/app.js) are accessible."""
    css_res = client.get("/static/styles.css")
    assert css_res.status_code == 200
    assert len(css_res.text) > 500

    js_res = client.get("/static/app.js")
    assert js_res.status_code == 200
    assert len(js_res.text) > 500


def test_health_endpoint_via_proxy_headers():
    """Verifies /api/health and /health return system, database, and scanner status."""
    res = client.get(
        "/api/health",
        headers={
            "Host": "localhost",
            "X-Real-IP": "10.0.0.1",
            "X-Forwarded-For": "10.0.0.1",
            "X-Forwarded-Proto": "http",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("healthy", "degraded")
    assert "database" in data
    assert "background_scanner" in data
    assert data["engine"] == "deterministic_hierarchical_extractor"

    # Test alias /health
    alias_res = client.get("/health")
    assert alias_res.status_code == 200
    assert alias_res.json()["engine"] == "deterministic_hierarchical_extractor"


def test_docs_and_catalog_routes():
    """Verifies that /docs, /catalog, and /products routes work."""
    docs_res = client.get("/docs")
    assert docs_res.status_code == 200

    catalog_res = client.get("/catalog")
    assert catalog_res.status_code == 200
    assert "Pharmaceutical Products" in catalog_res.text

    products_res = client.get("/products")
    assert products_res.status_code == 200
    assert "Pharmaceutical Products" in products_res.text


def test_product_short_urls():
    """Verifies short URLs /p/<product> and /p/<product>/<subsection>."""
    # Test on known sample product or fallback
    res = client.get("/p/ofloxacin")
    assert res.status_code == 200
    assert "<!DOCTYPE html>" in res.text

    sub_res = client.get("/p/ofloxacin/16.1")
    assert sub_res.status_code == 200
    assert "<!DOCTYPE html>" in sub_res.text


def test_pdf_upload_and_large_body_support():
    """Tests that PDF upload endpoint handles files up to large sizes."""
    sample_pdf = SAMPLE_DIR / "test1_basic.pdf"
    assert sample_pdf.exists()

    with open(sample_pdf, "rb") as f:
        pdf_bytes = f.read()

    # Upload standard file
    upload_res = client.post(
        "/api/upload",
        files={"files": ("test_proxy_upload.pdf", pdf_bytes, "application/pdf")},
        headers={
            "Host": "localhost",
            "X-Forwarded-For": "127.0.0.1",
            "X-Forwarded-Proto": "http",
        },
    )
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert data["status"] == "success"
    saved_filename = data["files"][0]["saved_filename"]

    # Delete uploaded test artifact
    del_res = client.delete(f"/api/upload/{saved_filename}")
    assert del_res.status_code == 200

    # Test large file upload (simulate a 5MB payload, well within the 100M Nginx limit)
    large_payload = pdf_bytes + (b"%" + b"A" * 1024 * 1024 * 4)  # ~4MB+ padded
    large_res = client.post(
        "/api/upload",
        files={"files": ("large_test.pdf", large_payload, "application/pdf")},
    )
    assert large_res.status_code == 200
    large_data = large_res.json()
    assert large_data["status"] == "success"
    large_saved = large_data["files"][0]["saved_filename"]
    client.delete(f"/api/upload/{large_saved}")


def test_extraction_workflow_end_to_end():
    """Verifies that deterministic extraction and table modes work end-to-end."""
    sample_pdf = SAMPLE_DIR / "test1_basic.pdf"
    res = client.post(
        "/api/extract",
        json={
            "file_path": str(sample_pdf),
            "filename": "test1_basic.pdf",
            "main_section": "16",
            "target_subsection": "16.1",
        },
        headers={"Host": "localhost", "X-Forwarded-Proto": "http"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "16.1" in data["validation"]["included_sections"]
    assert "16.2" in data["validation"]["excluded_sections"]
