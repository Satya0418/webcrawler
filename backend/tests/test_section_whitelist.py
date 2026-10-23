"""
Tests verifying strict section whitelisting:
1. ONLY Section 6 (Adverse Reactions), Section 5 (Warnings and Precautions), and Section 8.1-8.3 (Pregnancy/Lactation) are extracted.
2. Section 17 (Patient Counseling Information / Medication Guide) is NEVER extracted.
3. If an update or date range has ONLY Section 17, no data is extracted and 'no data' is returned.
"""
from datetime import datetime
import pytest
from bs4 import BeautifulSoup

from app.scrapers.fda_srlc_scraper import scraper
from app.sources.fda_srlc.section_detector import FDASrLCSectionDetector, is_whitelisted_safety_section
from app.models.drug import Drug, SafetyLabelingChange
from app.services.database_service import DatabaseService
from app.ui import export_drug_clean_html


HTML_WITH_SECTION_17_AND_ALLOWED = """
<!DOCTYPE html>
<html>
<body>
    <h2>TESTDRUG (NDA-999999)</h2>
    <h4>(TEST ACTIVE INGREDIENT)</h4>
    <div id="accordion">
        <h3>05/10/2026 (SUPPL-01)</h3>
        <div>
            <h4>5 Warnings and Precautions</h4>
            <p>Serious risk of liver injury.</p>
            <h4>6 Adverse Reactions</h4>
            <p>Postmarketing Experience: acute pancreatitis.</p>
            <h4>8 Use in Specific Populations</h4>
            <p>8.1 Pregnancy: May cause fetal harm.</p>
            <p>8.4 Pediatric Use: Safety not established.</p>
            <h4>17 PCI/PI/MG (Patient Counseling Information/Medication Guide)</h4>
            <p>MEDICATION GUIDE: How should I take this drug?</p>
            <h4>4 Contraindications</h4>
            <p>Do not use if allergic.</p>
            <h4>7 Drug Interactions</h4>
            <p>Avoid strong CYP3A4 inhibitors.</p>
        </div>
    </div>
</body>
</html>
"""

HTML_WITH_ONLY_SECTION_17 = """
<!DOCTYPE html>
<html>
<body>
    <h2>TESTDRUG (NDA-999999)</h2>
    <h4>(TEST ACTIVE INGREDIENT)</h4>
    <div id="accordion">
        <h3>01/10/2026 (SUPPL-02)</h3>
        <div>
            <h4>17 PCI/PI/MG (Patient Counseling Information/Medication Guide)</h4>
            <p>MEDICATION GUIDE: Updated storage instructions for patients.</p>
            <p>Keep out of reach of children.</p>
        </div>
    </div>
</body>
</html>
"""


def test_section_whitelist_detector():
    """Verify section detector allows only Sections 5, 6, and 8.1-8.3, and denies Section 17 & others."""
    # Allowed
    assert FDASrLCSectionDetector.is_whitelisted_section("6 Adverse Reactions") is True
    assert FDASrLCSectionDetector.is_whitelisted_section("6.2 Postmarketing Experience") is True
    assert FDASrLCSectionDetector.is_whitelisted_section("5 Warnings and Precautions") is True
    assert FDASrLCSectionDetector.is_whitelisted_section("Boxed Warning") is True
    assert FDASrLCSectionDetector.is_whitelisted_section("8 Use in Specific Populations", "8.1 Pregnancy: fetal risk") is True
    assert FDASrLCSectionDetector.is_whitelisted_section("8 Use in Specific Populations", "8.2 Lactation: present in milk") is True

    # Denied: Section 17
    assert FDASrLCSectionDetector.is_whitelisted_section("17 PCI/PI/MG") is False
    assert FDASrLCSectionDetector.is_whitelisted_section("17 Patient Counseling Information") is False
    assert FDASrLCSectionDetector.is_whitelisted_section("Medication Guide") is False
    assert FDASrLCSectionDetector.is_section_17("17 PCI/PI/MG (Patient Counseling Information/Patient Information/Medication Guide)") is True
    assert FDASrLCSectionDetector.is_section_17("Patient Counseling Information") is True

    # Denied: Other sections
    assert FDASrLCSectionDetector.is_whitelisted_section("4 Contraindications") is False
    assert FDASrLCSectionDetector.is_whitelisted_section("7 Drug Interactions") is False
    assert FDASrLCSectionDetector.is_whitelisted_section("1 Indications and Usage") is False
    assert FDASrLCSectionDetector.is_whitelisted_section("10 Overdosage") is False

    # Denied: Section 8 with ONLY pediatric / geriatric (no 8.1-8.3)
    assert FDASrLCSectionDetector.is_whitelisted_section("8 Use in Specific Populations", "8.4 Pediatric Use: not established.\n8.5 Geriatric Use: caution.") is False


def test_parse_detail_page_strictly_whitelists_sections():
    """Verify parse_detail_page extracts only 5, 6, and 8.1-8.3, and completely excludes Section 17, 4, 7."""
    parsed = scraper.parse_detail_page(HTML_WITH_SECTION_17_AND_ALLOWED)
    assert parsed is not None
    safety_changes = parsed.get("safety_changes", [])

    extracted_sections = [c["section"] for c in safety_changes]

    # Section 17, 4, 7 must NOT be extracted
    assert not any("17" in s or "Patient Counseling" in s or "Medication Guide" in s for s in extracted_sections)
    assert not any("Contraindications" in s for s in extracted_sections)
    assert not any("Drug Interactions" in s for s in extracted_sections)

    # Allowed sections must be present
    assert "Warnings and Precautions" in extracted_sections
    assert "Adverse Reactions" in extracted_sections
    assert "Use in Specific Populations" in extracted_sections


def test_parse_detail_page_only_section_17_returns_no_safety_changes():
    """When FDA update only modified Section 17, no safety changes are extracted."""
    parsed = scraper.parse_detail_page(HTML_WITH_ONLY_SECTION_17)
    # safety_changes must be empty
    changes = parsed.get("safety_changes", []) if parsed else []
    assert len(changes) == 0


def test_export_drug_clean_html_with_only_section_17_outputs_no_data():
    """When a drug has only Section 17 records, export_drug_clean_html outputs 'No data is present...'"""
    drug = {"display_name": "TestDrug", "active_ingredient": "Test Ingr"}
    changes = [
        {
            "section": "17 PCI/PI/MG",
            "updated_text": "Medication guide patient info",
            "source_date": "2026-01-10",
        },
        {
            "section": "Patient Counseling Information",
            "updated_text": "Advise patient to take with water",
            "source_date": "2026-01-10",
        },
    ]

    clean_html = export_drug_clean_html(drug, changes, standalone=True)
    assert "No data is present on adverse reaction or safety changes" in clean_html
    assert "Patient Counseling" not in clean_html
    assert "Medication Guide" not in clean_html


def test_save_safety_change_drops_section_17_and_non_whitelist():
    """Verify DatabaseService.save_safety_change drops Section 17 and non-whitelisted sections."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.database import Base

    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    drug = Drug(display_name="TESTDRUG", normalized_name="testdrug", source="FDA_SRLC")
    session.add(drug)
    session.commit()

    # Section 17
    sec17_res, inserted = DatabaseService.save_safety_change(session, drug.id, {
        "section": "17 PCI/PI/MG",
        "updated_text": "Medication Guide text",
        "source_date": "2026-01-10",
    })
    assert sec17_res is None
    assert inserted is False

    # Section 4 Contraindications
    sec4_res, inserted = DatabaseService.save_safety_change(session, drug.id, {
        "section": "4 Contraindications",
        "updated_text": "Do not use if allergic",
        "source_date": "2026-01-10",
    })
    assert sec4_res is None
    assert inserted is False

    # Section 6 Adverse Reactions (allowed)
    sec6_res, inserted = DatabaseService.save_safety_change(session, drug.id, {
        "section": "6 Adverse Reactions",
        "updated_text": "Common adverse reaction: headache",
        "source_date": "2026-01-10",
    })
    assert sec6_res is not None
    assert inserted is True

    # Section 8 with only 8.4 (denied)
    sec8_peds_res, inserted = DatabaseService.save_safety_change(session, drug.id, {
        "section": "8 Use in Specific Populations",
        "updated_text": "8.4 Pediatric Use: safety not established.",
        "source_date": "2026-01-10",
    })
    assert sec8_peds_res is None
    assert inserted is False

    # Section 8 with 8.1 Pregnancy (allowed)
    sec8_preg_res, inserted = DatabaseService.save_safety_change(session, drug.id, {
        "section": "8 Use in Specific Populations",
        "updated_text": "8.1 Pregnancy: potential risk to fetus.",
        "source_date": "2026-01-10",
    })
    assert sec8_preg_res is not None
    assert inserted is True

    session.close()


def test_get_safety_changes_by_drug_id_filters_out_section_17():
    """Verify get_safety_changes_by_drug_id filters out Section 17 even if present in table."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.database import Base

    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    drug = Drug(display_name="TESTDRUG", normalized_name="testdrug", source="FDA_SRLC")
    session.add(drug)
    session.commit()

    # Manually bypass save_safety_change and insert legacy Section 17 row
    chg_17 = SafetyLabelingChange(
        drug_id=drug.id,
        section="17 Patient Counseling Information",
        source_date=datetime(2026, 1, 10),
        updated_text="Patient instructions",
    )
    chg_warn = SafetyLabelingChange(
        drug_id=drug.id,
        section="Warnings and Precautions",
        source_date=datetime(2026, 1, 10),
        updated_text="Serious warning note",
    )
    session.add_all([chg_17, chg_warn])
    session.commit()

    changes = DatabaseService.get_safety_changes_by_drug_id(session, drug.id)
    sections = [c.section for c in changes]
    assert "Warnings and Precautions" in sections
    assert not any("17" in s or "Patient Counseling" in s for s in sections)

    session.close()


def test_api_signal_and_risk_drug_with_only_section_17_returns_404():
    """When a drug in database only has Section 17 changes in requested date range, API returns 404."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.main import app
    from app.database import Base, get_db

    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = Session()
    drug = Drug(display_name="ONLYSEC17DRUG", normalized_name="onlysec17drug", source="FDA_SRLC")
    db.add(drug)
    db.commit()

    # Add Section 17 directly in DB
    chg_17 = SafetyLabelingChange(
        drug_id=drug.id,
        section="17 Patient Counseling Information",
        source_date=datetime(2026, 1, 10),
        updated_text="Patient counseling guide",
    )
    db.add(chg_17)
    db.commit()
    db.close()

    payload = {
        "submissionId": "sub_test_sec17_only",
        "productName": "ONLYSEC17DRUG",
        "startDate": "01-01-2026",
        "endDate": "31-01-2026",
    }
    res = client.post("/api/drugs/signal-and-risk", json=payload)
    app.dependency_overrides.pop(get_db, None)

    assert res.status_code == 404
    assert "No safety labeling changes found" in res.json()["detail"]

