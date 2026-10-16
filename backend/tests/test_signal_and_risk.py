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
        validate_client_date_range("2025-01-01", "01-01-2026")
    assert "Expected DD-MM-YYYY" in str(excinfo.value.detail)


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
        "startDate": "2025-01-01",  # Not DD-MM-YYYY
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
