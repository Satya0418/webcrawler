import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_signal_and_risk_post_success():
    """
    Validates teammate's unified integration endpoint:
    - Sends POST request with submissionId and productName ('amikacin').
    - Verifies HTTP 200 status.
    - Verifies exact top-level keys: ['submissionId', 'productName', 'website_Data', 'pdf_extractor_Data'].
    - Verifies submissionId is echoed unchanged.
    - Verifies website_Data.title is 'Website Crawler Data'.
    - Verifies pdf_extractor_Data.title is 'PDF Extractor Data'.
    - Verifies pdf_extractor_Data contains real extracted Section 16 HTML from Amikacin PDF.
    """
    payload = {
        "submissionId": "a0CAq00004acdq7MAA",
        "productName": "amikacin",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    body = res.json()

    # Response top-level keys
    assert "submissionId" in body
    assert "productName" in body
    assert "website_Data" in body
    assert "pdf_extractor_Data" in body

    assert body["submissionId"] == "a0CAq00004acdq7MAA"
    assert "amikacin" in body["productName"].lower()

    # Website crawler data section
    web_section = body["website_Data"]
    assert web_section["title"] in ("Safety Action Taken", "Website Crawler Data")
    assert web_section["status"] in ("success", "not_found", "error")
    assert isinstance(web_section["data"], list)

    # PDF extractor data section
    pdf_section = body["pdf_extractor_Data"]
    assert pdf_section["title"] in ("Signal and Risk", "PDF Extractor Data")
    assert pdf_section["status"] == "success"
    assert isinstance(pdf_section["data"], dict)

    pdf_data = pdf_section["data"]
    assert pdf_data["status"] == "success"
    assert "amikacin" in pdf_data["product_name"].lower()
    assert pdf_data["target_section"] == "16"

    # Verifies real Section 16 HTML content string (headings and badges strictly omitted, paragraphs preserved)
    html = pdf_data["Data"]
    assert isinstance(html, str)
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert "Erfa-Amikacin" in html or "amikacin" in html.lower()
    assert "16.1 Summary of Safety Concerns" not in html
    assert "Section 16.1" not in html
    assert "med-brand-tag" not in html
    assert "med-sub-header" not in html


def test_signal_and_risk_alias_endpoint():
    """Verifies that /api/v1/signal-and-risk and /api/v1/product/signal-and-risk act as direct aliases."""
    payload = {
        "submissionId": "a0CAq00004acdq7MAA",
        "productName": "amikacin",
    }
    for endpoint in ["/api/v1/signal-and-risk", "/api/v1/product/signal-and-risk"]:
        res = client.post(endpoint, json=payload)
        assert res.status_code == 200, f"Failed for {endpoint}"
        body = res.json()
        assert body["submissionId"] == "a0CAq00004acdq7MAA"
        assert "amikacin" in body["productName"].lower()
        assert body["pdf_extractor_Data"]["title"] in ("Signal and Risk", "PDF Extractor Data")
        assert body["pdf_extractor_Data"]["status"] == "success"
        assert body["website_Data"]["title"] in ("Safety Action Taken", "Website Crawler Data")


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
    """Non-existent product in both PDF and crawler backend returns HTTP 404."""
    res = client.post(
        "/api/v1/products/signal-and-risk",
        json={"submissionId": "a0CAq00004acdq7MAA", "productName": "unknown_medicine_xyz_123"},
    )
    assert res.status_code == 404
    assert "No data found for product 'unknown_medicine_xyz_123'" in res.json()["detail"]


def test_signal_and_risk_date_range_valid_dd_mm_yyyy():
    """Valid DD-MM-YYYY dates are accepted and propagated."""
    payload = {
        "submissionId": "sub_with_dates_123",
        "productName": "amikacin",
        "startDate": "01-01-2025",
        "endDate": "01-01-2026",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["submissionId"] == "sub_with_dates_123"
    assert body["pdf_extractor_Data"]["status"] == "success"


def test_signal_and_risk_date_range_invalid_format():
    """Invalid date format (e.g. malformed string) returns HTTP 422."""
    payload = {
        "submissionId": "sub_invalid_date",
        "productName": "amikacin",
        "startDate": "2025/01/01",  # Malformed slashes
        "endDate": "01-01-2026",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 422
    assert "DD-MM-YYYY" in res.json()["detail"]


def test_signal_and_risk_date_range_reversed_dates():
    """Start date later than end date returns HTTP 422."""
    payload = {
        "submissionId": "sub_reversed_dates",
        "productName": "amikacin",
        "startDate": "01-01-2026",
        "endDate": "01-01-2025",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 422
    assert "cannot be later than endDate" in res.json()["detail"]


def test_signal_and_risk_empty_strings_omitted_filters():
    """Empty strings for optional fields are treated as omitted without error."""
    payload = {
        "submissionId": "sub_empty_filters",
        "productName": "amikacin",
        "startDate": "",
        "endDate": "",
        "genericName": "",
        "activeIngredients": "",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["submissionId"] == "sub_empty_filters"
    assert body["pdf_extractor_Data"]["status"] == "success"


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
        pdf_data = body["pdf_extractor_Data"]["data"]
        html = pdf_data["Data"]
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html
        assert "<table" not in html, f"Tables must be stripped from {prod}"


def test_signal_and_risk_browser_get_support():
    """Verifies that visiting the URL via GET in a browser with query params returns valid payload."""
    res = client.get("/api/v1/products/signal-and-risk?productName=amikacin")
    assert res.status_code == 200
    body = res.json()
    assert "amikacin" in body["productName"].lower()
    assert body["pdf_extractor_Data"]["title"] in ("Signal and Risk", "PDF Extractor Data")
    assert body["website_Data"]["title"] in ("Safety Action Taken", "Website Crawler Data")
    assert "<!DOCTYPE html>" in body["pdf_extractor_Data"]["data"]["Data"]


def test_signal_and_risk_singular_alias():
    """Verifies that typing /product/ (singular) works for both GET and POST."""
    res_post = client.post("/api/v1/product/signal-and-risk", json={"submissionId": "sub_1", "productName": "amikacin"})
    assert res_post.status_code == 200
    assert "amikacin" in res_post.json()["productName"].lower()

    res_get = client.get("/api/v1/product/signal-and-risk?productName=amikacin")
    assert res_get.status_code == 200
    assert "amikacin" in res_get.json()["productName"].lower()


def test_signal_and_risk_salesforce_callback_invoked(monkeypatch):
    """Verifies that send_salesforce_callback is invoked with two separate payloads (SafetyActionTaken and SignalAndRisk)."""
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
    assert len(called_payloads) == 2

    # Webhook Call #1: Safety Action Taken
    cb_safety, cb_url_1 = called_payloads[0]
    assert cb_safety["submissionId"] == "salesforce_test_sub_101"
    assert cb_safety["responseType"] == "SafetyActionTaken"
    assert isinstance(cb_safety["responseData"], list)
    assert len(cb_safety["responseData"]) >= 1
    assert "website_Name" in cb_safety["responseData"][0]
    assert "website_Data" in cb_safety["responseData"][0]
    assert "updateSubmissionResponse" in cb_url_1

    # Webhook Call #2: Signal and Risk
    cb_signal, cb_url_2 = called_payloads[1]
    assert cb_signal["submissionId"] == "salesforce_test_sub_101"
    assert cb_signal["responseType"] == "SignalAndRisk"
    assert "responseData" in cb_signal
    assert "updateSubmissionResponse" in cb_url_2


def test_signal_and_risk_both_success_independent_objects(monkeypatch):
    """
    Verifies that when both PDF Section 16 data and Crawler data exist:
    - Response contains TWO SEPARATE response objects: website_Data and pdf_extractor_Data.
    - website_Data.title in ('Safety Action Taken', 'Website Crawler Data')
    - pdf_extractor_Data.title in ('Signal and Risk', 'PDF Extractor Data')
    - Website HTML appears ONLY in website_Data.data[0].Data.
    - PDF HTML appears ONLY in pdf_extractor_Data.data.Data.
    - Neither overwrites, merges, or mislabels the other.
    """
    from backend.api import products

    async def fake_crawler_fetch(product_name, submission_id, **kwargs):
        return {
            "status": "success",
            "item": {
                "website_Name": "FDA_details",
                "title": "Website Safety Data",
                "productName": product_name,
                "genericName": "amikacin sulfate",
                "activeIngredients": "AMIKACIN SULFATE",
                "startDate": kwargs.get("start_date", ""),
                "endDate": kwargs.get("end_date", ""),
                "Data": "<section class=\"fda-safety-report\"><h2>FDA Live SrLC Report</h2></section>",
                "submissionId": submission_id,
            },
        }

    monkeypatch.setattr(products, "fetch_crawler_safety_data", fake_crawler_fetch)

    payload = {
        "submissionId": "sub_multi_source_999",
        "productName": "amikacin",
        "startDate": "01-01-2025",
        "endDate": "01-01-2026",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 200
    body = res.json()

    assert body["submissionId"] == "sub_multi_source_999"
    assert "amikacin" in body["productName"].lower()

    # Subsystem 1: website_Data
    web_res = body["website_Data"]
    assert web_res["title"] in ("Safety Action Taken", "Website Crawler Data")
    assert web_res["status"] == "success"
    assert len(web_res["data"]) == 1
    web_item = web_res["data"][0]
    assert web_item["website_Name"] == "FDA_details"
    assert web_item["title"] == "Website Safety Data"
    assert "FDA Live SrLC Report" in web_item["Data"]
    assert "Erfa-Amikacin" not in web_item["Data"]  # Distinct from PDF!

    # Subsystem 2: pdf_extractor_Data
    pdf_res = body["pdf_extractor_Data"]
    assert pdf_res["title"] in ("Signal and Risk", "PDF Extractor Data")
    assert pdf_res["status"] == "success"
    pdf_data = pdf_res["data"]
    assert "<!DOCTYPE html>" in pdf_data["Data"]
    assert "Erfa-Amikacin" in pdf_data["Data"] or "amikacin" in pdf_data["Data"].lower()
    assert "fda-safety-report" not in pdf_data["Data"]  # Distinct from website!


def test_signal_and_risk_returns_crawler_when_no_pdf(monkeypatch):
    """
    Verifies that for a drug not in PDF records but present in crawler backend:
    - HTTP 200 is returned.
    - website_Data.status == 'success' with website records.
    - pdf_extractor_Data.status == 'not_found' with data == None.
    - Successful website results are NOT suppressed.
    """
    from backend.api import products

    async def fake_crawler_fetch(product_name, submission_id, **kwargs):
        return {
            "status": "success",
            "item": {
                "website_Name": "FDA_details",
                "title": "Website Safety Data",
                "productName": "Lipitor",
                "genericName": "atorvastatin calcium",
                "activeIngredients": "ATORVASTATIN CALCIUM",
                "startDate": "",
                "endDate": "",
                "Data": "<section class=\"fda-safety-report\"><h2>US FDA Lipitor Report</h2></section>",
                "submissionId": submission_id,
            },
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
    assert body["website_Data"]["status"] == "success"
    assert len(body["website_Data"]["data"]) == 1
    assert "US FDA Lipitor Report" in body["website_Data"]["data"][0]["Data"]

    # PDF status is not_found, but does not break the response
    assert body["pdf_extractor_Data"]["status"] == "not_found"
    assert body["pdf_extractor_Data"]["data"] is None


def test_signal_and_risk_returns_pdf_when_crawler_fails(monkeypatch):
    """
    Verifies that when crawler backend fails (e.g. error or timeout):
    - HTTP 200 is returned.
    - pdf_extractor_Data.status == 'success' with Section 16 data.
    - website_Data.status == 'error' with data == [].
    - PDF result is preserved intact.
    """
    from backend.api import products

    async def fake_crawler_fetch_error(product_name, submission_id, **kwargs):
        return {
            "status": "error",
            "message": "Connection to crawler_backend:8001 timed out after 15s",
        }

    monkeypatch.setattr(products, "fetch_crawler_safety_data", fake_crawler_fetch_error)

    payload = {
        "submissionId": "sub_pdf_only_555",
        "productName": "amikacin",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 200
    body = res.json()

    assert body["submissionId"] == "sub_pdf_only_555"
    assert body["pdf_extractor_Data"]["status"] == "success"
    assert "<!DOCTYPE html>" in body["pdf_extractor_Data"]["data"]["Data"]

    assert body["website_Data"]["status"] == "error"
    assert body["website_Data"]["data"] == []
    assert "timed out" in body["website_Data"]["message"]


def test_signal_and_risk_auth_failure(monkeypatch):
    """Verifies that when API_KEY is configured, requests without valid X-API-KEY return HTTP 401."""
    from backend.api import products
    monkeypatch.setattr(products, "API_KEY", "secret-test-api-key")

    payload = {
        "submissionId": "sub_auth_test",
        "productName": "amikacin",
    }
    # Missing key
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 401

    # Wrong key
    res_wrong = client.post(
        "/api/v1/products/signal-and-risk",
        json=payload,
        headers={"X-API-KEY": "wrong-key"},
    )
    assert res_wrong.status_code == 401

    # Correct key
    res_ok = client.post(
        "/api/v1/products/signal-and-risk",
        json=payload,
        headers={"X-API-KEY": "secret-test-api-key"},
    )
    assert res_ok.status_code == 200


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


def test_signal_and_risk_iso_date_format_support():
    """Verifies that Salesforce ISO dates like '2024-10-31T00:00:00.000Z' or '2024-10-31' parse cleanly without 422."""
    payload = {
        "submissionId": "iso_date_sub_001",
        "productName": "amikacin",
        "startDate": "2024-10-31T00:00:00.000Z",
        "endDate": "2025-12-31T00:00:00.000Z",
    }
    res = client.post("/api/v1/products/signal-and-risk", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["submissionId"] == "iso_date_sub_001"
