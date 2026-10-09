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

    # Exactly one entry backed by real extracted data (no fabricated 16.2)
    assert isinstance(body["responseData"], list)
    assert len(body["responseData"]) == 1

    entry = body["responseData"][0]
    assert set(entry.keys()) == {"productName", "title", "Data"}
    assert entry["title"] == "summary_of_safety_concerns"
    assert "amikacin" in entry["productName"].lower()

    # Verifies real Section 16 HTML content string
    html = entry["Data"]
    assert isinstance(html, str)
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert "Amikacin" in html
    assert "16 Signal and Risk Evaluation" in html or "16.1 Summary of Safety Concerns" in html


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
    assert len(body["responseData"]) == 1
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
    assert len(body["responseData"]) == 1


def test_signal_and_risk_multiple_indexed_products():
    """Verifies that other indexed products (e.g. Ofloxacin, Lipitor) return their real Section 16 HTML."""
    for prod in ["ofloxacin", "lipitor"]:
        res = client.post(
            "/api/v1/products/signal-and-risk",
            json={"submissionId": f"sub_{prod}", "productName": prod},
        )
        assert res.status_code == 200, f"Failed for {prod}: {res.text}"
        body = res.json()
        assert body["submissionId"] == f"sub_{prod}"
        assert body["responseType"] == "SignalAndRisk"
        assert len(body["responseData"]) == 1
        html = body["responseData"][0]["Data"]
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html
        assert "<table" not in html, f"Tables must be stripped from {prod}"
