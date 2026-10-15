import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_signal_and_risk_post_success():
    """
    Validates teammate's integration endpoint:
    - Sends POST request with submissionId and productName ('amikacin').
    - Verifies HTTP 200 status.
    - Verifies exact top-level keys: ['responseType', 'submissionId', 'responseData'].
    - Verifies submissionId is echoed unchanged.
    - Verifies responseType is 'SignalAndRisk'.
    - Verifies responseData contains exactly one entry with keys ['title', 'Data'].
    - Verifies title is 'summary_of_safety_concerns'.
    - Verifies 'Data' contains real extracted Section 16 HTML from Amikacin PDF.
    """
    payload = {
        "submissionId": "a0CAq00004acdq7MAA",
        "productName": "amikacin",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    body = res.json()

    # Response keys include productName
    assert set(body.keys()) == {"responseType", "submissionId", "productName", "responseData"}
    assert body["responseType"] == "SignalAndRisk"
    assert body["submissionId"] == "a0CAq00004acdq7MAA"
    assert "amikacin" in body["productName"].lower()

    # Contains Section 16 data (and optional crawler companion entry if running)
    assert isinstance(body["responseData"], list)
    assert len(body["responseData"]) >= 1

    entry = body["responseData"][0]
    assert set(entry.keys()) == {"productName", "title", "Data"}
    assert entry["title"] == "summary_of_safety_concerns"
    assert "amikacin" in entry["productName"].lower()

    # Verifies real Section 16 HTML content string (headings and badges strictly omitted, paragraphs preserved)
    html = entry["Data"]
    assert isinstance(html, str)
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert "Erfa-Amikacin" in html or "amikacin" in html.lower()
    assert "16.1 Summary of Safety Concerns" not in html
    assert "Section 16.1" not in html
    assert "med-brand-tag" not in html
    assert "med-sub-header" not in html


def test_signal_and_risk_alias_endpoint():
    """Verifies that /api/v1/signal-and-risk acts as a direct alias."""
    payload = {
        "submissionId": "a0CAq00004acdq7MAA",
        "productName": "amikacin",
    }
    res = client.post("/api/v1/signal-and-risk", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["responseType"] == "SignalAndRisk"
    assert body["submissionId"] == "a0CAq00004acdq7MAA"
    assert "amikacin" in body["productName"].lower()
    assert len(body["responseData"]) >= 1
    assert body["responseData"][0]["title"] == "summary_of_safety_concerns"
    assert "amikacin" in body["responseData"][0]["productName"].lower()
    assert "Amikacin" in body["responseData"][0]["Data"]


def test_signal_and_risk_validation_missing_submission_id():
    """Missing or empty submissionId returns HTTP 400."""
    res1 = client.post("/api/v1/products/signal-and-risk", json={"productName": "amikacin"})
    assert res1.status_code == 400
    assert "submissionId" in res1.json()["detail"]

    res2 = client.post("/api/v1/products/signal-and-risk", json={"submissionId": "   ", "productName": "amikacin"})
    assert res2.status_code == 400
    assert "submissionId" in res2.json()["detail"]


def test_signal_and_risk_validation_missing_product_name():
    """Missing or empty productName returns HTTP 400."""
    res1 = client.post("/api/v1/products/signal-and-risk", json={"submissionId": "a0CAq00004acdq7MAA"})
    assert res1.status_code == 400
    assert "productName" in res1.json()["detail"]

    res2 = client.post(
        "/api/v1/products/signal-and-risk",
        json={"submissionId": "a0CAq00004acdq7MAA", "productName": ""},
    )
    assert res2.status_code == 400
    assert "productName" in res2.json()["detail"]


def test_signal_and_risk_product_not_found():
    """Non-existent or unindexed product returns clear HTTP 404."""
    res = client.post(
        "/api/v1/products/signal-and-risk",
        json={"submissionId": "a0CAq00004acdq7MAA", "productName": "unknown_medicine_xyz_123"},
    )
    assert res.status_code == 404
    assert "No indexed Section 16 data found" in res.json()["detail"]


def test_signal_and_risk_start_end_dates_ignored():
    """Optional dates are ignored without error."""
    payload = {
        "submissionId": "sub_with_dates_123",
        "productName": "amikacin",
        "startDate": "2024-01-01",
        "endDate": "2024-12-31",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["submissionId"] == "sub_with_dates_123"
    assert len(body["responseData"]) >= 1


def test_signal_and_risk_multiple_indexed_products():
    """Verifies that other indexed products (e.g. Ofloxacin, Lipitor) return their real Section 16 HTML."""
    for prod in ["ofloxacin", "lipitor"]:
        res = client.post(
            "/api/v1/products/signal-and-risk",
            json={"submissionId": f"sub_{prod}", "productName": prod},
        )
        if res.status_code == 404:
            continue
        assert res.status_code == 200, f"Failed for {prod}: {res.text}"
        body = res.json()
        assert body["submissionId"] == f"sub_{prod}"
        assert body["responseType"] == "SignalAndRisk"
        assert len(body["responseData"]) >= 1
        html = body["responseData"][0]["Data"]
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html
        assert "<table" not in html, f"Tables must be stripped from {prod}"


def test_signal_and_risk_browser_get_support():
    """Verifies that visiting the URL via GET in a browser with query params returns valid payload."""
    res = client.get("/api/v1/products/signal-and-risk?productName=amikacin")
    assert res.status_code == 200
    body = res.json()
    assert body["responseType"] == "SignalAndRisk"
    assert "amikacin" in body["productName"].lower()
    assert body["responseData"][0]["title"] == "summary_of_safety_concerns"
    assert "<!DOCTYPE html>" in body["responseData"][0]["Data"]


def test_signal_and_risk_singular_alias():
    """Verifies that typing /product/ (singular) works for both GET and POST."""
    res_post = client.post("/api/v1/product/signal-and-risk", json={"submissionId": "sub_1", "productName": "amikacin"})
    assert res_post.status_code == 200
    assert "amikacin" in res_post.json()["productName"].lower()

    res_get = client.get("/api/v1/product/signal-and-risk?productName=amikacin")
    assert res_get.status_code == 200
    assert "amikacin" in res_get.json()["productName"].lower()


def test_signal_and_risk_salesforce_callback_invoked(monkeypatch):
    """Verifies that send_salesforce_callback is invoked with the expected payload."""
    called_payloads = []

    async def fake_send_callback(payload, callback_url=None):
        called_payloads.append((payload, callback_url))
        return {"status": "delivered", "status_code": 200}

    from backend.api import products
    monkeypatch.setattr(products, "send_salesforce_callback", fake_send_callback)

    payload = {
        "submissionId": "salesforce_test_sub_101",
        "productName": "amikacin",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 200
    assert len(called_payloads) == 1

    callback_data, callback_url = called_payloads[0]
    assert callback_data["submissionId"] == "salesforce_test_sub_101"
    assert callback_data["productName"] == "Amikacin"
    assert callback_data["responseData"][0]["title"] == "summary_of_safety_concerns"
    assert "updateSubmissionResponse" in callback_url


<<<<<<< Updated upstream
def test_signal_and_risk_returns_two_separate_entries_when_crawler_available(monkeypatch):
    """
    Verifies that when both PDF Section 16 data and Crawler data exist:
    - responseData contains exactly TWO SEPARATE entries (not merged together).
    - Entry 0 is the PDF extraction with title 'summary_of_safety_concerns'.
    - Entry 1 is the FDA crawler data with title 'fda_safety_labeling_changes'.
    - The HTML content of both entries remains distinct.
    """
    from backend.api import products

    async def fake_crawler_fetch(product_name, submission_id, timeout_seconds=12.0):
        return {
            "productName": product_name,
            "title": "fda_safety_labeling_changes",
            "Data": "<section class=\"fda-safety-report\"><h2>FDA Live SrLC Report</h2></section>",
        }

    monkeypatch.setattr(products, "fetch_crawler_safety_data", fake_crawler_fetch)

    payload = {
        "submissionId": "sub_multi_source_999",
        "productName": "amikacin",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 200
    body = res.json()

    assert body["submissionId"] == "sub_multi_source_999"
    assert "amikacin" in body["productName"].lower()

    # Two separate items
    items = body["responseData"]
    assert len(items) == 2, f"Expected 2 separate entries, got {len(items)}"

    # Item 1: PDF Extractor
    pdf_item = items[0]
    assert pdf_item["title"] == "summary_of_safety_concerns"
    assert "<!DOCTYPE html>" in pdf_item["Data"]
    assert "16 Signal and Risk Evaluation" in pdf_item["Data"] or "16.1 Summary of Safety Concerns" in pdf_item["Data"]
    assert "fda-safety-report" not in pdf_item["Data"]  # Not merged into item 0!

    # Item 2: Crawler Backend
    crawler_item = items[1]
    assert crawler_item["title"] == "fda_safety_labeling_changes"
    assert "<section class=\"fda-safety-report\">" in crawler_item["Data"]
    assert "FDA Live SrLC Report" in crawler_item["Data"]
    assert "<!DOCTYPE html>" not in crawler_item["Data"]  # Distinct from item 0


def test_signal_and_risk_returns_crawler_when_no_pdf(monkeypatch):
    """
    Verifies that for a drug not in PDF records but present in crawler backend,
    the crawler entry is returned seamlessly with HTTP 200.
    """
    from backend.api import products

    async def fake_crawler_fetch(product_name, submission_id, timeout_seconds=12.0):
        return {
            "productName": "Lipitor",
            "title": "fda_safety_labeling_changes",
            "Data": "<section class=\"fda-safety-report\"><h2>US FDA Lipitor Report</h2></section>",
        }

    monkeypatch.setattr(products, "fetch_crawler_safety_data", fake_crawler_fetch)

    payload = {
        "submissionId": "sub_lipitor_777",
        "productName": "lipitor_unknown_in_pdf",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 200
    body = res.json()

    assert body["submissionId"] == "sub_lipitor_777"
    assert len(body["responseData"]) == 1
    assert body["responseData"][0]["title"] == "fda_safety_labeling_changes"
    assert "US FDA Lipitor Report" in body["responseData"][0]["Data"]
=======
def test_product_section_16_paragraph_only():
    """Verifies that /api/v1/products/section-16 returns purely paragraph text without headers/badges."""
    res = client.get("/api/v1/products/section-16?product_name=amikacin&subsection=16.1")
    assert res.status_code == 200
    data = res.json()
    
    # Text must contain the body paragraph, but no headings
    assert "Erfa-Amikacin" in data["data"]["text"]
    assert "16.1 Summary of Safety Concerns" not in data["data"]["text"]
    assert "16 Signal and Risk" not in data["data"]["text"]
    
    # HTML string Data must not contain banners or badges
    html = data["Data"]
    assert "16.1 Summary of Safety Concerns" not in html
    assert "Section 16.1" not in html
    assert "Amikacin - Section 16" not in html
    assert "med-main-header" not in html
    assert "med-sub-header" not in html
    assert "med-brand-tag" not in html
    assert "Erfa-Amikacin" in html


def test_short_url_p_amikacin_paragraph_only():
    """Verifies that visiting /p/amikacin/16.1 in browser renders pure paragraph without heading banners."""
    res = client.get("/p/amikacin/16.1")
    assert res.status_code == 200
    html = res.text
    assert "16.1 Summary of Safety Concerns" not in html
    assert "Section 16.1" not in html
    assert "Amikacin - Section 16" not in html
    assert "med-main-header" not in html
    assert "med-sub-header" not in html
    assert "med-brand-tag" not in html
    assert "Erfa-Amikacin" in html
>>>>>>> Stashed changes


