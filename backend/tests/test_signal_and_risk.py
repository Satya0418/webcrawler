"""
Unit and integration tests for the unified Signal and Risk crawler endpoint,
covering date-range filtering, boundary conditions, product/generic/ingredient matching,
and validation errors.
"""
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.drug import Drug, SafetyLabelingChange
from app.services.database_service import DatabaseService
from app.api.drugs import validate_client_date_range

# Isolated in-memory database
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Setup and teardown tables per test with clean dependency overrides."""
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=test_engine)


# ---------------------------------------------------------------------------
# 1. Date Range Validation Unit Tests
# ---------------------------------------------------------------------------

def test_validate_client_date_range_valid():
    start_dt, end_dt, start_str, end_str = validate_client_date_range("01-01-2025", "15-06-2025")
    assert start_str == "01-01-2025"
    assert end_str == "15-06-2025"
    assert start_dt == datetime(2025, 1, 1, 0, 0, 0, 0)
    assert end_dt == datetime(2025, 6, 15, 23, 59, 59, 999999)


def test_validate_client_date_range_empty_or_none():
    start_dt, end_dt, start_str, end_str = validate_client_date_range("", None)
    assert start_dt is None
    assert end_dt is None
    assert start_str == ""
    assert end_str == ""


def test_validate_client_date_range_invalid_format():
    with pytest.raises(Exception) as excinfo:
        validate_client_date_range("2025/01/01", "01-01-2026")
    assert "Expected DD-MM-YYYY" in str(excinfo.value.detail)


def test_validate_client_date_range_iso_format():
    start_dt, end_dt, start_str, end_str = validate_client_date_range("2024-10-31T00:00:00.000Z", "2025-12-31")
    assert start_dt.year == 2024 and start_dt.month == 10 and start_dt.day == 31
    assert end_dt.year == 2025 and end_dt.month == 12 and end_dt.day == 31
    assert start_str == "31-10-2024"
    assert end_str == "31-12-2025"


def test_validate_client_date_range_invalid_calendar_date():
    with pytest.raises(Exception) as excinfo:
        validate_client_date_range("31-02-2025", "01-03-2025")
    assert "Invalid calendar date" in str(excinfo.value.detail)


def test_validate_client_date_range_reversed_dates():
    with pytest.raises(Exception) as excinfo:
        validate_client_date_range("01-01-2026", "01-01-2025")
    assert "cannot be later than endDate" in str(excinfo.value.detail)


# ---------------------------------------------------------------------------
# 2. Database Service Filtering & Boundary Tests
# ---------------------------------------------------------------------------

def test_search_drugs_filtered_multi_criteria():
    session = TestingSessionLocal()
    d1 = Drug(
        display_name="ARIKAYCE",
        normalized_name="arikayce",
        active_ingredient="AMIKACIN SULFATE",
        source="FDA_SRLC",
    )
    d2 = Drug(
        display_name="AMIKACIN",
        normalized_name="amikacin",
        active_ingredient="AMIKACIN",
        source="FDA_SRLC",
    )
    d3 = Drug(
        display_name="LIPITOR",
        normalized_name="lipitor",
        active_ingredient="ATORVASTATIN CALCIUM",
        source="FDA_SRLC",
    )
    session.add_all([d1, d2, d3])
    session.commit()

    # Match by product name only
    res = DatabaseService.search_drugs_filtered(session, product_name="arikayce")
    assert len(res) == 1
    assert res[0].display_name == "ARIKAYCE"

    # Match by product name and active ingredients
    res = DatabaseService.search_drugs_filtered(
        session,
        product_name="arikayce",
        active_ingredients="AMIKACIN",
    )
    assert len(res) == 1
    assert res[0].display_name == "ARIKAYCE"

    # Filter with mismatching generic name should return empty
    res = DatabaseService.search_drugs_filtered(
        session,
        product_name="arikayce",
        generic_name="atorvastatin",
    )
    assert len(res) == 0

    session.close()


def test_get_safety_changes_date_boundaries_inclusive():
    session = TestingSessionLocal()
    drug = Drug(display_name="TestDrug", normalized_name="testdrug", source="FDA_SRLC")
    session.add(drug)
    session.commit()

    # Create changes on various dates:
    # 1. Before window: 2024-12-31 23:59:59
    c_before = SafetyLabelingChange(
        drug_id=drug.id,
        section="Warnings",
        source_date=datetime(2024, 12, 31, 23, 59, 59),
        original_text="Old",
    )
    # 2. Exactly at start boundary: 2025-01-01 00:00:00
    c_start = SafetyLabelingChange(
        drug_id=drug.id,
        section="Warnings",
        source_date=datetime(2025, 1, 1, 0, 0, 0),
        original_text="Start boundary",
    )
    # 3. Middle of window: 2025-06-15 12:00:00
    c_mid = SafetyLabelingChange(
        drug_id=drug.id,
        section="Warnings",
        source_date=datetime(2025, 6, 15, 12, 0, 0),
        original_text="Mid",
    )
    # 4. Exactly at end boundary: 2026-01-01 23:59:59
    c_end = SafetyLabelingChange(
        drug_id=drug.id,
        section="Warnings",
        source_date=datetime(2026, 1, 1, 23, 59, 59),
        original_text="End boundary",
    )
    # 5. After window: 2026-01-02 00:00:00
    c_after = SafetyLabelingChange(
        drug_id=drug.id,
        section="Warnings",
        source_date=datetime(2026, 1, 2, 0, 0, 0),
        original_text="After",
    )
    # 6. Null date (should be excluded when date filter is applied)
    c_null = SafetyLabelingChange(
        drug_id=drug.id,
        section="Warnings",
        source_date=None,
        original_text="Null date",
    )

    session.add_all([c_before, c_start, c_mid, c_end, c_after, c_null])
    session.commit()

    start_dt = datetime(2025, 1, 1, 0, 0, 0)
    end_dt = datetime(2026, 1, 1, 23, 59, 59, 999999)

    changes = DatabaseService.get_safety_changes_by_drug_id(
        session, drug.id, start_date=start_dt, end_date=end_dt
    )

    # Must contain c_start, c_mid, c_end; but NOT c_before, c_after, or c_null
    change_texts = [c.original_text for c in changes]
    assert "Start boundary" in change_texts
    assert "Mid" in change_texts
    assert "End boundary" in change_texts
    assert "Old" not in change_texts
    assert "After" not in change_texts
    assert "Null date" not in change_texts
    assert len(changes) == 3

    session.close()


# ---------------------------------------------------------------------------
# 3. Crawler API /api/drugs/signal-and-risk Endpoint Tests
# ---------------------------------------------------------------------------

def test_api_signal_and_risk_date_range_success():
    session = TestingSessionLocal()
    drug = Drug(
        display_name="ARIKAYCE",
        normalized_name="arikayce",
        active_ingredient="AMIKACIN SULFATE",
        source="FDA_SRLC",
    )
    session.add(drug)
    session.commit()

    chg = SafetyLabelingChange(
        drug_id=drug.id,
        section="Boxed Warning",
        source_date=datetime(2025, 5, 20),
        original_text="Original text",
        updated_text="Updated text for 2025",
    )
    session.add(chg)
    session.commit()
    session.close()

    payload = {
        "submissionId": "sub_test_101",
        "productName": "ARIKAYCE",
        "startDate": "01-01-2025",
        "endDate": "01-01-2026",
    }
    res = client.post("/api/drugs/signal-and-risk", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["submissionId"] == "sub_test_101"
    assert data["productName"] == "ARIKAYCE"

    # website_Data object
    assert "website_Data" in data
    web_data = data["website_Data"]
    assert web_data["title"] == "Website Crawler Data"
    assert web_data["status"] == "success"
    assert len(web_data["data"]) == 1

    item = web_data["data"][0]
    assert item["website_Name"] == "FDA_details"
    assert item["startDate"] == "01-01-2025"
    assert item["endDate"] == "01-01-2026"
    assert "<!DOCTYPE html>" in item["Data"]


def test_api_signal_and_risk_no_records_in_date_range_returns_404():
    session = TestingSessionLocal()
    drug = Drug(
        display_name="ARIKAYCE",
        normalized_name="arikayce",
        source="FDA_SRLC",
    )
    session.add(drug)
    session.commit()

    # Record exists in 2023, outside requested 2025 range
    chg = SafetyLabelingChange(
        drug_id=drug.id,
        section="Warnings",
        source_date=datetime(2023, 5, 20),
        original_text="Old 2023 change",
    )
    session.add(chg)
    session.commit()
    session.close()

    payload = {
        "submissionId": "sub_test_outside",
        "productName": "ARIKAYCE",
        "startDate": "01-01-2025",
        "endDate": "01-01-2026",
    }
    res = client.post("/api/drugs/signal-and-risk", json=payload)
    assert res.status_code == 404
    assert "within requested date range" in res.json()["detail"]


def test_api_signal_and_risk_reversed_dates_returns_422():
    payload = {
        "submissionId": "sub_test_rev",
        "productName": "ARIKAYCE",
        "startDate": "01-01-2026",
        "endDate": "01-01-2025",
    }
    res = client.post("/api/drugs/signal-and-risk", json=payload)
    assert res.status_code == 422
    assert "cannot be later than endDate" in res.json()["detail"]


def test_api_signal_and_risk_malformed_date_returns_422():
    payload = {
        "submissionId": "sub_test_bad_date",
        "productName": "ARIKAYCE",
        "startDate": "2025/01/01",  # Malformed date slashes
        "endDate": "01-01-2026",
    }
    res = client.post("/api/drugs/signal-and-risk", json=payload)
    assert res.status_code == 422
    assert "Expected DD-MM-YYYY" in res.json()["detail"]


def test_api_signal_and_risk_empty_strings_omitted():
    session = TestingSessionLocal()
    drug = Drug(
        display_name="ARIKAYCE",
        normalized_name="arikayce",
        source="FDA_SRLC",
    )
    session.add(drug)
    session.commit()
    chg = SafetyLabelingChange(
        drug_id=drug.id,
        section="Warnings",
        source_date=datetime(2024, 1, 1),
        original_text="Default change",
    )
    session.add(chg)
    session.commit()
    session.close()

    payload = {
        "submissionId": "sub_empty_strings",
        "productName": "ARIKAYCE",
        "startDate": "",
        "endDate": "",
        "genericName": "",
        "activeIngredients": "",
    }
    res = client.post("/api/drugs/signal-and-risk", json=payload)
    assert res.status_code == 200
    assert res.json()["submissionId"] == "sub_empty_strings"


# ---------------------------------------------------------------------------
# 4. End-to-End Live/Mocked Crawler & Historical Retrieval Tests
# ---------------------------------------------------------------------------

def test_api_signal_and_risk_traverses_all_candidates_and_retrieves_history(monkeypatch):
    """
    Verifies that:
    - All search candidates in search results are considered (not just the first 3).
    - Detail page with multiple historical accordion panels (2016, 2017) is crawled.
    - Historical date range (2017) filters out 2016 supplements and includes 2017 supplements.
    """
    from pathlib import Path
    from app.crawler.fda_crawler import crawler

    detail_fixture_path = Path(__file__).parent / "fixtures" / "fda" / "detail_warfarin.html"
    with open(detail_fixture_path) as f:
        detail_html = f.read()

    # Search results HTML with 4 distinct candidates
    search_html = """
    <table>
        <tr>
            <th>Drug Name</th>
            <th>Active Ingredient</th>
            <th>Application</th>
            <th>Type</th>
            <th>Date</th>
            <th>Updated</th>
            <th>Link</th>
        </tr>
        <tr>
            <td><a href="/detail?DrugNameID=1">COUMADIN TABLETS</a></td>
            <td>WARFARIN SODIUM</td><td>009218</td><td>NDA</td><td>08/14/2017</td><td>08/17/2017</td>
            <td>https://www.accessdata.fda.gov/detail?DrugNameID=1</td>
        </tr>
        <tr>
            <td><a href="/detail?DrugNameID=2">COUMADIN INJECTION</a></td>
            <td>WARFARIN SODIUM</td><td>009219</td><td>NDA</td><td>08/14/2017</td><td>08/17/2017</td>
            <td>https://www.accessdata.fda.gov/detail?DrugNameID=2</td>
        </tr>
        <tr>
            <td><a href="/detail?DrugNameID=3">COUMADIN 5MG</a></td>
            <td>WARFARIN SODIUM</td><td>009220</td><td>NDA</td><td>08/14/2017</td><td>08/17/2017</td>
            <td>https://www.accessdata.fda.gov/detail?DrugNameID=3</td>
        </tr>
        <tr>
            <td><a href="/detail?DrugNameID=4">COUMADIN 10MG (Candidate 4)</a></td>
            <td>WARFARIN SODIUM</td><td>009221</td><td>NDA</td><td>08/14/2017</td><td>08/17/2017</td>
            <td>https://www.accessdata.fda.gov/detail?DrugNameID=4</td>
        </tr>
    </table>
    """

    visited_detail_urls = []

    async def fake_search_drug(drug_name):
        return search_html

    async def fake_get_detail_page(url):
        visited_detail_urls.append(url)
        return detail_html

    monkeypatch.setattr(crawler, "search_drug", fake_search_drug)
    monkeypatch.setattr(crawler, "get_detail_page", fake_get_detail_page)

    payload = {
        "submissionId": "sub_warfarin_history",
        "productName": "COUMADIN",
        "startDate": "01-01-2017",
        "endDate": "31-12-2017",
    }
    res = client.post("/api/drugs/signal-and-risk", json=payload)
    assert res.status_code == 200, f"Expected 200, got: {res.text}"
    body = res.json()

    # Confirms all 4 candidates were processed (beyond index 3!)
    assert len(visited_detail_urls) == 4

    web_data = body["website_Data"]
    assert web_data["status"] == "success"
    assert web_data["coverage"] == "complete"
    assert len(web_data["data"]) == 1

    html_content = web_data["data"][0]["Data"]
    # 2017 dates must be present in HTML
    assert "2017" in html_content
    # 2016 supplement date must be excluded by the 2017 date boundary
    assert "2016-09-08" not in html_content


def test_api_signal_and_risk_search_fallback_to_generic(monkeypatch):
    """
    Verifies that when productName yields no search results on FDA,
    the crawler falls back to searching by genericName and successfully retrieves data.
    """
    from pathlib import Path
    from app.crawler.fda_crawler import crawler

    fixture_path = Path(__file__).parent / "fixtures" / "fda" / "search_results_warfarin.html"
    with open(fixture_path) as f:
        search_warfarin_html = f.read()

    detail_path = Path(__file__).parent / "fixtures" / "fda" / "detail_warfarin.html"
    with open(detail_path) as f:
        detail_html = f.read()

    searched_queries = []

    async def fake_search_drug(term):
        searched_queries.append(term)
        if term == "UnknownBrandX":
            return ""  # Brand returns no results on FDA
        if "warfarin" in term.lower():
            return search_warfarin_html
        return ""

    async def fake_get_detail_page(url):
        return detail_html

    monkeypatch.setattr(crawler, "search_drug", fake_search_drug)
    monkeypatch.setattr(crawler, "get_detail_page", fake_get_detail_page)

    payload = {
        "submissionId": "sub_fallback_test",
        "productName": "UnknownBrandX",
        "genericName": "warfarin",
        "startDate": "01-01-2017",
        "endDate": "31-12-2017",
    }
    res = client.post("/api/drugs/signal-and-risk", json=payload)
    assert res.status_code == 200
    assert "UnknownBrandX" in searched_queries
    assert "warfarin" in searched_queries
    body = res.json()
    assert body["website_Data"]["status"] == "success"


def test_api_signal_and_risk_pre_2016_coverage_flag():
    """
    Verifies that requesting a date range starting prior to 2016 flags partial coverage
    and provides clear source limitation information (since FDA SrLC begins in 2016).
    """
    session = TestingSessionLocal()
    drug = Drug(display_name="COUMADIN", normalized_name="coumadin", source="FDA_SRLC")
    session.add(drug)
    session.commit()
    chg = SafetyLabelingChange(
        drug_id=drug.id,
        section="Warnings",
        source_date=datetime(2017, 5, 22),
        original_text="2017 change",
    )
    session.add(chg)
    session.commit()
    session.close()

    payload = {
        "submissionId": "sub_pre_2016",
        "productName": "COUMADIN",
        "startDate": "01-01-2010",
        "endDate": "01-01-2020",
    }
    res = client.post("/api/drugs/signal-and-risk", json=payload)
    assert res.status_code == 200
    body = res.json()

    web_data = body["website_Data"]
    assert web_data["coverage"] == "partial"
    assert "2016" in web_data["source_limitation"]


def test_api_signal_and_risk_salesforce_callback_format(monkeypatch):
    """
    Verifies that the outbound Salesforce callback payload and the responseData
    strictly match the {"website_Name": ..., "website_Data": ...} schema.
    """
    from app.api import drugs

    captured_callbacks = []

    async def fake_send_callback(payload, callback_url=None):
        captured_callbacks.append((payload, callback_url))
        return {"status": "delivered", "status_code": 200}

    monkeypatch.setattr(drugs, "send_salesforce_callback", fake_send_callback)

    session = TestingSessionLocal()
    drug = Drug(display_name="WARFARIN", normalized_name="warfarin", source="FDA_SRLC")
    session.add(drug)
    session.commit()
    chg = SafetyLabelingChange(
        drug_id=drug.id,
        section="Boxed Warning",
        source_date=datetime(2024, 3, 1),
        original_text="Bleeding risk",
    )
    session.add(chg)
    session.commit()
    session.close()

    payload = {
        "submissionId": "a0CAq00004acdq7MAA",
        "productName": "WARFARIN",
        "startDate": "01-01-2024",
        "endDate": "01-01-2025",
        "callbackUrl": "https://salesforce.example.com/services/apexrest/updateSubmissionResponse",
    }
    res = client.post("/api/drugs/signal-and-risk", json=payload)
    assert res.status_code == 200
    body = res.json()

    assert body["submissionId"] == "a0CAq00004acdq7MAA"
    assert body["responseType"] == "SafetyActionTaken"
    assert len(body["responseData"]) == 1
    assert "website_Name" in body["responseData"][0]
    assert "website_Data" in body["responseData"][0]
    assert body["responseData"][0]["website_Name"] == "FDA_details"
    assert "<!DOCTYPE html>" in body["responseData"][0]["website_Data"]

    assert len(captured_callbacks) == 1
    cb_payload, cb_url = captured_callbacks[0]
    assert cb_url == "https://salesforce.example.com/services/apexrest/updateSubmissionResponse"
    assert cb_payload["submissionId"] == "a0CAq00004acdq7MAA"
    assert cb_payload["responseType"] == "SafetyActionTaken"
    assert len(cb_payload["responseData"]) == 1
    assert cb_payload["responseData"][0]["website_Name"] == "FDA_details"
    assert "<!DOCTYPE html>" in cb_payload["responseData"][0]["website_Data"]


def test_api_signal_and_risk_active_ingredient_ezetimibe_date_matching(monkeypatch):
    """
    Verifies that when searching for active ingredient EZETIMIBE with date range
    02/21/2024 to 02/22/2024:
    1. The crawler ranks and matches ZETIA (pure EZETIMIBE) over combination drugs
       like LIPTRUZET (ATORVASTATIN CALCIUM; EZETIMIBE).
    2. The search-page date matching correctly identifies the 02/21/2024 row and navigates
       to ZETIA first.
    3. The extracted response contains ZETIA and its safety data matching 02/21/2024.
    """
    from app.crawler.fda_crawler import crawler

    search_html = """
    <table id="example" class="display">
        <thead>
            <tr>
                <th>Drug Name</th><th>Active Ingredient</th><th>Application Number</th>
                <th>Application Type</th><th>Supplement Date</th><th>Database Updated</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><a href="/detail?DrugNameID=200153">LIPTRUZET</a></td>
                <td>ATORVASTATIN CALCIUM; EZETIMIBE</td>
                <td>200153</td><td>NDA</td><td>10/28/2024</td><td>10/30/2024</td>
            </tr>
            <tr>
                <td><a href="/detail?DrugNameID=211617">NEXLIZET</a></td>
                <td>BEMPEDOIC ACID; EZETIMIBE</td>
                <td>211617</td><td>NDA</td><td>01/09/2026</td><td>01/13/2026</td>
            </tr>
            <tr>
                <td><a href="/detail?DrugNameID=213072">ROSZET</a></td>
                <td>EZETIMIBE; ROSUVASTATIN CALCIUM</td>
                <td>213072</td><td>NDA</td><td>08/26/2024</td><td>08/30/2024</td>
            </tr>
            <tr>
                <td><a href="/detail?DrugNameID=021687">VYTORIN</a></td>
                <td>EZETIMIBE; SIMVASTATIN</td>
                <td>021687</td><td>NDA</td><td>03/28/2024</td><td>04/01/2024</td>
            </tr>
            <tr>
                <td><a href="/detail?DrugNameID=021445">ZETIA</a></td>
                <td>EZETIMIBE</td>
                <td>021445</td><td>NDA</td><td>02/21/2024</td><td>02/22/2024</td>
            </tr>
        </tbody>
    </table>
    """

    zetia_detail_html = """
    <html>
        <body>
            <h2>ZETIA (NDA-021445)</h2>
            <h4>(EZETIMIBE)</h4>
            <div id="accordion">
                <h3>02/21/2024 (SUPPL-45)</h3>
                <div>
                    <h4>6 Adverse Reactions</h4>
                    <p>Postmarketing experience: Anaphylaxis, angioedema, rash, and urticaria.</p>
                </div>
            </div>
        </body>
    </html>
    """

    crawled_urls = []

    async def fake_search_drug(drug_name):
        return search_html

    async def fake_get_detail_page(url):
        crawled_urls.append(url)
        return zetia_detail_html

    monkeypatch.setattr(crawler, "search_drug", fake_search_drug)
    monkeypatch.setattr(crawler, "get_detail_page", fake_get_detail_page)

    # Test with MM/DD/YYYY format as shown in user's image: 02/21/2024 to 02/22/2024
    payload = {
        "submissionId": "sub_ezetimibe_match",
        "productName": "EZETIMIBE",
        "startDate": "02/21/2024",
        "endDate": "02/22/2024",
    }
    res = client.post("/api/drugs/signal-and-risk", json=payload)
    assert res.status_code == 200, f"Expected 200, got: {res.text}"
    body = res.json()

    # Verify that ZETIA detail page was crawled first
    assert len(crawled_urls) >= 1
    assert "021445" in crawled_urls[0]

    # Verify response contains ZETIA and its active ingredient EZETIMIBE
    web_data = body["website_Data"]
    assert web_data["status"] == "success"
    entry = web_data["data"][0]
    assert entry["productName"] == "ZETIA"
    assert entry["activeIngredients"] == "EZETIMIBE"
    assert "Anaphylaxis" in entry["Data"]


def test_export_drug_clean_html_section_sequence():
    """
    Verifies that sections in export_drug_clean_html always follow the canonical
    FDA labeling and website sequence (Warnings and Precautions -> Adverse Reactions ->
    Use in Specific Populations), even if changes are stored in reverse order.
    """
    from app.ui import export_drug_clean_html

    fake_drug = {
        "display_name": "ADDYI",
        "active_ingredient": "FLIBANSERIN",
        "application_number": "NDA-022526",
    }
    # Provide changes in reverse order: Use in Specific Populations, then Warnings, then Adverse Reactions
    fake_changes = [
        {
            "section": "Use in Specific Populations",
            "source_date": "2025-12-13",
            "updated_text": "Pregnancy Risk Summary: There are no studies of ADDYI in pregnant women.\n\nGeriatric Use: ADDYI is not indicated for geriatric patients.",
        },
        {
            "section": "Warnings and Precautions",
            "source_date": "2025-12-13",
            "updated_text": "Central Nervous System Depression: ADDYI can cause CNS depression.\n\nHypotension and Syncope with ADDYI Alone: Can cause hypotension and syncope.",
        },
        {
            "section": "Adverse Reactions",
            "source_date": "2025-12-13",
            "updated_text": "Clinical Trials Experience: Extensive changes.\n\nPostmarketing Experience: Hypersensitivity reactions.",
        },
    ]

    html_out = export_drug_clean_html(fake_drug, fake_changes, standalone=True)

    pos_wp = html_out.find("<h2>5 Warnings and Precautions</h2>")
    pos_ar = html_out.find("<h2>6 Adverse Reactions</h2>")
    pos_usp = html_out.find("<h2>8 Use in Specific Populations</h2>")

    assert pos_wp != -1, "5 Warnings and Precautions must be present"
    assert pos_ar != -1, "6 Adverse Reactions must be present"
    assert pos_usp != -1, "8 Use in Specific Populations must be present"

    # Canonical order: Warnings and Precautions < Adverse Reactions < Use in Specific Populations
    assert pos_wp < pos_ar, "Warnings and Precautions must precede Adverse Reactions"
    assert pos_ar < pos_usp, "Adverse Reactions must precede Use in Specific Populations"




