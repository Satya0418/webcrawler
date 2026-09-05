"""
Tests for Adverse Reactions extractor and report formatter.
Verifies date-wise chronological selection, section 17 filtering,
editorial text removal, and 'No data is present on adverse reaction' behavior.
"""
import pytest
from datetime import datetime
from app.scrapers.fda_srlc_scraper import (
    scraper,
    format_fda_date_to_report,
    parse_fda_date,
    clean_adverse_reaction_text,
)

# HTML sample recreating real FDA SrLC page for ARIKAYCE KIT
ARIKAYCE_REAL_HTML = """
<!DOCTYPE html>
<html>
<head><title>FDA Safety-related Labeling Changes</title></head>
<body>
    <h2>ARIKAYCE KIT (NDA-207356)</h2>
    <h4>(AMIKACIN SULFATE)</h4>
    <div id="accordion">
        <h3>06/25/2026 <small>(SUPPL-25)</small></h3>
        <div>
            <p><a href="https://example.com/label2026.pdf">Approved Drug Label (PDF)</a></p>
            <h4>6 Adverse Reactions</h4>
            <div>
                <strong>6.2 Postmarketing Experience</strong>
                <p>Newly added information:</p>
                <p>Renal and urinary disorders: acute kidney injury, renal failure</p>
            </div>
        </div>

        <h3>12/05/2025 <small>(SUPPL-19)</small></h3>
        <div>
            <p><a href="https://example.com/label2025.pdf">Approved Drug Label (PDF)</a></p>
            <h4>6 Adverse Reactions</h4>
            <div>
                <p><b>6.2 Postmarketing Experience</b></p>
                <p><i>Additions and/or revisions underlined:</i></p>
                <p>...</p>
                <p>Gastrointestinal disorders: dysphagia, glossitis, glossodynia, salivary hypersecretion, stomatitis, abdominal pain, abdominal distension</p>
                <p>Immune system disorders: hypersensitivity, anaphylaxis, pharyngeal swelling [see Warnings and Precautions (5.5)]</p>
                <p>Respiratory, thoracic, and mediastinal disorders: nasal dryness, rhinorrhea, sneezing, nasal congestion</p>
            </div>
            <h4>17 PCI/PI/MG (Patient Counseling Information/Patient Information/Medication Guide)</h4>
            <div>
                <p><b>MEDICATION GUIDE</b></p>
                <p><i>Additions and/or revisions underlined:</i></p>
                <p>...</p>
                <p><b>How should I use ARIKAYCE?</b></p>
                <p>• Do not use ARIKAYCE unless you understand the directions provided.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

# HTML sample where 2026 has no AR and 2025 has AR (verifying fallback)
SKIP_NEWEST_WHEN_NO_AR_HTML = """
<!DOCTYPE html>
<html>
<body>
    <h2>SAMPLEDRUG (NDA-111111)</h2>
    <h4>(SAMPLE INGREDIENT)</h4>
    <div id="accordion">
        <h3>06/25/2026 <small>(SUPPL-25)</small></h3>
        <div>
            <h4>5 Warnings and Precautions</h4>
            <div><p>Only warnings in 2026.</p></div>
            <h4>17 PCI/PI/MG (Patient Counseling Information/Patient Information/Medication Guide)</h4>
            <div><p>Medication guide in 2026.</p></div>
        </div>
        <h3>12/05/2025 <small>(SUPPL-19)</small></h3>
        <div>
            <h4>6 Adverse Reactions</h4>
            <div>
                <p>Gastrointestinal disorders: dysphagia, glossitis</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

# HTML sample where both 2025 and 2026 have Adverse Reactions
MULTIPLE_DATES_AR_HTML = """
<!DOCTYPE html>
<html>
<body>
    <h2>TESTMED (NDA-123456)</h2>
    <h4>(TESTING INGREDIENT)</h4>
    <div id="accordion">
        <h3>10/12/2025 <small>(SUPPL-10)</small></h3>
        <div>
            <h4>6 Adverse Reactions</h4>
            <div>
                <p>Older adverse reaction: headache, nausea</p>
            </div>
        </div>
        <h3>04/04/2026 <small>(SUPPL-12)</small></h3>
        <div>
            <h4>6 Adverse Reactions</h4>
            <div>
                <p><b>6.2 Postmarketing Experience</b></p>
                <p>Latest adverse reaction: dizziness, fatigue</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

# HTML sample where NO date has Adverse Reactions
NO_AR_HTML = """
<!DOCTYPE html>
<html>
<body>
    <h2>CLEANMED (NDA-999999)</h2>
    <h4>(CLEAN INGREDIENT)</h4>
    <div id="accordion">
        <h3>06/25/2026 <small>(SUPPL-02)</small></h3>
        <div>
            <h4>5 Warnings and Precautions</h4>
            <div><p>Only warnings here.</p></div>
        </div>
        <h3>12/05/2025 <small>(SUPPL-01)</small></h3>
        <div>
            <h4>7 Drug Interactions</h4>
            <div><p>Only drug interactions here.</p></div>
        </div>
    </div>
</body>
</html>
"""


class TestAdverseReactionsExtraction:
    """Test suite for adverse reactions extraction and report formatting."""

    def test_date_formatting(self):
        """Test formatting of FDA dates to DD-Mon-YYYY."""
        assert format_fda_date_to_report("12/05/2025") == "05-Dec-2025"
        assert format_fda_date_to_report("04/04/2026") == "04-Apr-2026"
        assert format_fda_date_to_report("10/12/2025") == "12-Oct-2025"
        assert format_fda_date_to_report("06/25/2026") == "25-Jun-2026"
        assert format_fda_date_to_report("2025-12-05") == "05-Dec-2025"

    def test_clean_adverse_reaction_text_stops_at_section_17(self):
        """Verify section 17 and medication guide are strictly cut off."""
        raw = (
            "Gastrointestinal disorders: dysphagia, glossitis\n\n"
            "Immune system disorders: hypersensitivity\n\n"
            "17 PCI/PI/MG (Patient Counseling Information/Patient Information/Medication Guide)\n\n"
            "MEDICATION GUIDE\n\n"
            "How should I use ARIKAYCE?"
        )
        cleaned = clean_adverse_reaction_text(raw)
        assert "17 PCI/PI/MG" not in cleaned
        assert "MEDICATION GUIDE" not in cleaned
        assert "How should I use" not in cleaned
        assert "Gastrointestinal disorders: dysphagia, glossitis" in cleaned
        assert "Immune system disorders: hypersensitivity" in cleaned

    def test_clean_adverse_reaction_text_strips_noise_and_brackets(self):
        """Verify editorial noise, ellipsis, and [see ...] are removed."""
        raw = (
            "6.2 Postmarketing Experience\n\n"
            "Additions and/or revisions underlined:\n\n"
            "...\n\n"
            "Immune system disorders: hypersensitivity, pharyngeal swelling [see Warnings and Precautions (5.5)]"
        )
        cleaned = clean_adverse_reaction_text(raw)
        assert "Additions and/or revisions underlined:" not in cleaned
        assert "..." not in cleaned
        assert "[see Warnings and Precautions (5.5)]" not in cleaned
        assert "Postmarketing Experience" in cleaned
        assert "Immune system disorders: hypersensitivity, pharyngeal swelling" in cleaned

    def test_arikayce_real_selects_latest_2026_date(self):
        """
        Verify that for ARIKAYCE KIT with real FDA data, the extractor selects
        the latest 25-Jun-2026 date containing Adverse Reactions.
        """
        report = scraper.extract_adverse_reactions_report(ARIKAYCE_REAL_HTML)
        assert report["status"] == "success"
        assert report["selected_date"] == "06/25/2026"
        assert report["formatted_date"] == "25-Jun-2026"
        assert "Renal and urinary disorders: acute kidney injury, renal failure" in report["formatted_report"]
        assert "Postmarketing Experience" in report["formatted_report"]
        assert "3.1 The United States Food and Drug Administration" in report["formatted_report"]
        assert "On 25-Jun-2026, the United States Food and Drug Administration" in report["formatted_report"]
        assert "Arikayce Kit" in report["formatted_report"]

    def test_skip_when_newer_date_lacks_ar(self):
        """
        Verify that when 2026 has no Adverse Reactions and 2025 has Adverse Reactions,
        the extractor verifies 2026, moves to 2025, and selects 2025.
        """
        report = scraper.extract_adverse_reactions_report(SKIP_NEWEST_WHEN_NO_AR_HTML)
        assert report["status"] == "success"
        assert report["selected_date"] == "12/05/2025"
        assert report["formatted_date"] == "05-Dec-2025"
        assert "Gastrointestinal disorders: dysphagia, glossitis" in report["formatted_report"]

    def test_multiple_dates_with_ar_picks_latest_date(self):
        """
        Verify that if Adverse Reactions is present in both 2025 and 2026,
        the extractor selects the latest date (04/04/2026).
        """
        report = scraper.extract_adverse_reactions_report(MULTIPLE_DATES_AR_HTML)
        assert report["status"] == "success"
        assert report["selected_date"] == "04/04/2026"
        assert report["formatted_date"] == "04-Apr-2026"
        assert "dizziness, fatigue" in report["formatted_report"]
        assert "headache, nausea" not in report["formatted_report"]

    def test_no_adverse_reactions_returns_no_data_response(self):
        """
        Verify that when no Adverse Reactions is present in any date,
        the response returns 'No data is present on adverse reaction'.
        """
        report = scraper.extract_adverse_reactions_report(NO_AR_HTML)
        assert report["status"] == "no_data"
        assert report["message"] == "No data is present on adverse reaction"
        assert report["formatted_report"] == "No data is present on adverse reaction"

    def test_extract_from_records_method(self):
        """Test extraction from database SafetyLabelingChange record objects."""
        changes = [
            {
                "source_date": datetime(2026, 6, 25),
                "source_record_id": "SUPPL-25",
                "section": "Warnings and Precautions",
                "updated_text": "Warning text.",
            },
            {
                "source_date": datetime(2025, 12, 5),
                "source_record_id": "SUPPL-19",
                "section": "Adverse Reactions",
                "updated_text": (
                    "6.2 Postmarketing Experience\n\n"
                    "Gastrointestinal disorders: dysphagia\n\n"
                    "17 PCI/PI/MG\nMedication guide text"
                ),
            },
        ]
        report = scraper.extract_adverse_reactions_from_records(
            drug_name="ARIKAYCE KIT",
            active_ingredient="AMIKACIN SULFATE",
            changes=changes,
        )
        assert report["status"] == "success"
        assert report["formatted_date"] == "05-Dec-2025"
        assert "Gastrointestinal disorders: dysphagia" in report["formatted_report"]
        assert "17 PCI/PI/MG" not in report["formatted_report"]
