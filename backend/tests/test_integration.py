"""
Integration tests for complete Medicine Safety Platform API.
Tests end-to-end user workflows: Search -> Crawler/DB -> Cache -> Versioning -> History.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.drug
from app.main import app
from app.database import Base, get_db
from app.services.database_service import DatabaseService
from app.models.drug import Drug, SafetyLabelingChange

# In-memory database with StaticPool for test isolation
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database dependency for isolated tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Setup and teardown tables per test."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "medicine-safety-backend"


def test_source_health_check():
    """Test FDA source health status endpoint."""
    response = client.get("/api/admin/source-health")
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "FDA_SRLC"
    assert data["status"] in ("Healthy", "Warning", "Failed")


def test_drug_search_and_persistence():
    """Test search workflow, database insertion, and cached second query."""
    # First search for Warfarin (triggers live crawl or DB fallback)
    response = client.get("/api/drugs/search?q=warfarin")
    assert response.status_code == 200
    data = response.json()

    assert data["query"] == "warfarin"
    assert data["source"] == "FDA_SRLC"
    assert len(data["results"]) >= 1

    first_result = data["results"][0]
    assert "drug_id" in first_result
    assert "COUMADIN" in first_result["drug_name"].upper() or "WARFARIN" in first_result["drug_name"].upper()
    assert first_result["safety_change_count"] >= 1

    drug_id = first_result["drug_id"]

    # Second search for the same drug - should immediately return without new crawl
    response2 = client.get("/api/drugs/search?q=warfarin")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["results"]) >= 1
    assert data2["results"][0]["drug_id"] == drug_id

    # Test drug detail endpoint
    detail_res = client.get(f"/api/drugs/{drug_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == drug_id
    assert len(detail["safety_changes"]) >= 1

    # Test safety change history endpoint
    first_change = detail["safety_changes"][0]
    change_id = first_change["id"]

    history_res = client.get(f"/api/safety-changes/{change_id}/history")
    assert history_res.status_code == 200
    history = history_res.json()
    assert isinstance(history, list)


def test_change_detection_and_version_archiving():
    """Test that updating a safety change archives the prior version and retains history."""
    db = TestingSessionLocal()
    try:
        # 1. Create drug
        drug, _ = DatabaseService.insert_or_update_drug(
            db,
            {
                "display_name": "TestDrug",
                "active_ingredient": "TestMolecule",
                "application_number": "NDA-999999",
            },
        )
        db.commit()

        # 2. Add first version of safety change
        chg_v1 = {
            "section": "Warnings and Precautions",
            "source_date": "2026-01-10",
            "updated_text": "Original Version 1 safety warning text.",
            "source_record_id": "SUPPL-001",
            "source_url": "https://www.accessdata.fda.gov/test",
        }
        change, is_new = DatabaseService.save_safety_change(db, drug.id, chg_v1)
        db.commit()
        assert is_new is True
        change_id = change.id

        # Check versions (should be 0 archived versions initially)
        versions = DatabaseService.get_versions_by_change_id(db, change_id)
        assert len(versions) == 0

        # 3. Simulate FDA publishing an update to this section (text changed)
        chg_v2 = {
            "section": "Warnings and Precautions",
            "source_date": "2026-04-15",
            "updated_text": "Updated Version 2 safety warning with additional precautions.",
            "source_record_id": "SUPPL-001",
            "source_url": "https://www.accessdata.fda.gov/test",
        }
        updated_change, was_updated = DatabaseService.save_safety_change(db, drug.id, chg_v2)
        db.commit()
        assert was_updated is True
        assert updated_change.id == change_id

        # 4. Check versions via API
        response = client.get(f"/api/safety-changes/{change_id}/history")
        assert response.status_code == 200
        history = response.json()
        assert len(history) == 1
        assert history[0]["version_number"] == 1
        assert history[0]["updated_text"] == "Original Version 1 safety warning text."

        # Verify current active record is Version 2
        active_res = client.get(f"/api/safety-changes/{change_id}")
        assert active_res.status_code == 200
        active = active_res.json()
        assert active["updated_text"] == "Updated Version 2 safety warning with additional precautions."

    finally:
        db.close()


def test_drug_not_found():
    """Test 404 on non-existent drug."""
    response = client.get("/api/drugs/999999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_safety_change_not_found():
    """Test 404 on non-existent safety change."""
    response = client.get("/api/safety-changes/999999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_export_csv_and_json():
    """Test downloading drug safety data in CSV and JSON formats."""
    db = TestingSessionLocal()
    try:
        # Create test drug
        drug_data = {
            "drug_name": "ASPIRIN TEST",
            "active_ingredient": "ASPIRIN",
            "application_number": "NDA-999999",
            "source": "FDA_SRLC",
            "source_url": "https://www.accessdata.fda.gov/test",
        }
        drug, _ = DatabaseService.insert_or_update_drug(db, drug_data)
        db.commit()

        # Add safety change
        chg = {
            "section": "Warnings and Precautions",
            "source_date": "2026-05-01",
            "updated_text": "Risk of bleeding.",
            "source_record_id": "SUPPL-01",
            "source_url": "https://www.accessdata.fda.gov/test",
        }
        DatabaseService.save_safety_change(db, drug.id, chg)
        db.commit()

        # Test CSV export
        res_csv = client.get(f"/drugs/{drug.id}/export?format=csv")
        assert res_csv.status_code == 200
        assert "text/csv" in res_csv.headers["content-type"]
        assert "attachment" in res_csv.headers["content-disposition"]
        assert "ASPIRIN TEST" in res_csv.text
        assert "Risk of bleeding." in res_csv.text

        # Test JSON export
        res_json = client.get(f"/drugs/{drug.id}/export?format=json")
        assert res_json.status_code == 200
        assert "application/json" in res_json.headers["content-type"]
        assert "attachment" in res_json.headers["content-disposition"]
        data = res_json.json()
        assert data["drug"]["display_name"] == "ASPIRIN TEST"
        assert len(data["safety_changes"]) >= 1

        # Test API endpoint export
        api_csv = client.get(f"/api/drugs/{drug.id}/export?format=csv")
        assert api_csv.status_code == 200
        assert "text/csv" in api_csv.headers["content-type"]

    finally:
        db.close()
