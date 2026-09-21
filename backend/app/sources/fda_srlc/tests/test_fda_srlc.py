"""
Comprehensive test suite for FDA Drug Safety-related Labeling Changes (SrLC).
Verifies the 10 mandated requirements:
1. Multiple FDA dates -> Latest actual date selected.
2. Latest date has only Adverse Reactions -> AR extracted, older sections not mixed in.
3. Latest date has AR, Warnings, and Pregnancy -> All three extracted.
4. Latest date has AR & Warnings; Pregnancy only in older update -> Pregnancy not taken from older update.
5. Latest date has Pregnancy but no AR -> Pregnancy extracted, no fabricated AR.
6. Multiple records have the same latest date -> All records inspected.
7. No product match -> Handled gracefully with 'No matching FDA SrLC record found'.
8. Malformed HTML structure -> Controlled handling, no crashes or invalid data.
9. Deduplication -> Same record retrieved twice does not create duplicate DB row.
10. Page traceability -> Extracted section retains page numbers from existing PDF extractor.
"""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.database_service import DatabaseService
from app.sources.fda_srlc.adapter import FDASrLCAdapter
from app.sources.fda_srlc.crawler import FDASrLCCrawler
from app.sources.fda_srlc.date_parser import (
    format_fda_date_to_report,
    parse_fda_date,
    select_latest_date_and_records,
)
from app.sources.fda_srlc.extractor import FDASrLCExtractor, NOT_FOUND_MSG
from app.sources.fda_srlc.models import (
    FDASearchCandidate,
    FDASupplementRecord,
)
from app.sources.fda_srlc.result_parser import FDASrLCResultParser
from app.sources.fda_srlc.section_detector import FDASrLCSectionDetector


# ---------------------------------------------------------------------------
# HTML Fixtures recreating realistic FDA SrLC structures
# ---------------------------------------------------------------------------

HTML_MULTIPLE_DATES = """
<div id="accordion">
    <h3>01/15/2024 (SUPPL-10)</h3>
    <div>
        <h4>6 Adverse Reactions</h4>
        <p>2024 older adverse reaction.</p>
    </div>
    <h3>06/20/2026 (SUPPL-20)</h3>
    <div>
        <h4>6 Adverse Reactions</h4>
        <p>2026 latest adverse reaction: dyspnea, tachycardia.</p>
    </div>
    <h3>03/10/2025 (SUPPL-15)</h3>
    <div>
        <h4>5 Warnings and Precautions</h4>
        <p>2025 warning text.</p>
    </div>
</div>
"""

HTML_LATEST_ONLY_AR = """
<div id="accordion">
    <h3>05/20/2026 (SUPPL-30)</h3>
    <div>
        <h4>6 Adverse Reactions</h4>
        <p>Postmarketing Experience: urticaria, angioedema.</p>
    </div>
    <h3>01/10/2025 (SUPPL-25)</h3>
    <div>
        <h4>5 Warnings and Precautions</h4>
        <p>Older warning: hepatotoxicity risk.</p>
        <h4>8 Use in Specific Populations</h4>
        <p>8.1 Pregnancy: Older pregnancy risk summary.</p>
    </div>
</div>
"""

HTML_ALL_THREE_SECTIONS = """
<div id="accordion">
    <h3>08/15/2026 (SUPPL-40)</h3>
    <div>
        <h4>6 Adverse Reactions</h4>
        <p>6.2 Postmarketing Experience: anaphylaxis, erythema multiforme.</p>
        <h4>5 Warnings and Precautions</h4>
        <p>5.1 Severe Cutaneous Adverse Reactions (SCAR).</p>
        <h4>8 Use in Specific Populations</h4>
        <p>8.1 Pregnancy: May cause fetal harm when administered to a pregnant woman.</p>
    </div>
</div>
"""

HTML_PREGNANCY_IN_OLDER_ONLY = """
<div id="accordion">
    <h3>05/20/2026 (SUPPL-50)</h3>
    <div>
        <h4>6 Adverse Reactions</h4>
        <p>6.2 Postmarketing Experience: somnolence, fatigue.</p>
        <h4>5 Warnings and Precautions</h4>
        <p>5.2 Neuropsychiatric Adverse Events.</p>
    </div>
    <h3>03/10/2025 (SUPPL-45)</h3>
    <div>
        <h4>8 Use in Specific Populations</h4>
        <p>8.1 Pregnancy: In animal reproduction studies, embryofetal toxicity occurred.</p>
    </div>
</div>
"""

HTML_PREGNANCY_NO_AR = """
<div id="accordion">
    <h3>09/10/2026 (SUPPL-12)</h3>
    <div>
        <h4>8 Use in Specific Populations</h4>
        <p>8.1 Pregnancy: Published observational studies have not identified a drug-associated risk.</p>
        <p>8.2 Lactation: There are no data on the presence in human milk.</p>
    </div>
    <h3>02/01/2024 (SUPPL-08)</h3>
    <div>
        <h4>6 Adverse Reactions</h4>
        <p>Older adverse reaction from 2024.</p>
    </div>
</div>
"""

HTML_SEARCH_RESULTS_ZYVOX = """
<table id="example" class="display">
    <thead>
        <tr>
            <th>Drug Name</th>
            <th>Active Ingredient</th>
            <th>Application Number</th>
            <th>Application Type</th>
            <th>Supplement Date</th>
            <th>Database Updated</th>
            <th>Link</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td><a href="index.cfm?event=searchdetail.page&DrugNameID=1439">ZYVOX</a></td>
            <td>LINEZOLID</td>
            <td>021130</td>
            <td>NDA</td>
            <td>06/09/2026</td>
            <td>06/17/2026</td>
            <td>https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/index.cfm?event=searchdetail.page&DrugNameID=1439</td>
        </tr>
    </tbody>
</table>
"""


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestFDASrLCIntegration:
    """Test suite covering the 10 mandated FDA SrLC scenarios."""

    @pytest.mark.asyncio
    async def test_01_multiple_fda_dates_selects_latest_date(self):
        """TEST 1: Multiple FDA dates -> Latest actual date selected."""
        extractor = FDASrLCExtractor()
        d_name, ingr, app, records = extractor.parse_supplement_records_from_detail_html(HTML_MULTIPLE_DATES)
        assert len(records) == 3

        result = await extractor.extract_latest_update(
            drug_name="TESTDRUG",
            active_ingredient="TESTINGR",
            application_number="NDA-12345",
            all_supplement_records=records,
        )

        assert result.latest_labeling_change_date == "06/20/2026"
        assert result.sections.adverse_reactions.found is True
        assert "2026 latest adverse reaction: dyspnea, tachycardia" in result.sections.adverse_reactions.content
        assert "2024" not in result.sections.adverse_reactions.content

    @pytest.mark.asyncio
    async def test_02_latest_date_has_only_adverse_reactions_no_mixing(self):
        """
        TEST 2: Latest date has only Adverse Reactions.
        Adverse Reactions extracted. Older sections must NOT be mixed in.
        """
        extractor = FDASrLCExtractor()
        d_name, ingr, app, records = extractor.parse_supplement_records_from_detail_html(HTML_LATEST_ONLY_AR)

        result = await extractor.extract_latest_update(
            drug_name="ARONLYDRUG",
            active_ingredient="ARONLYINGR",
            application_number="NDA-22222",
            all_supplement_records=records,
        )

        assert result.latest_labeling_change_date == "05/20/2026"
        assert result.sections.adverse_reactions.found is True
        assert "urticaria, angioedema" in result.sections.adverse_reactions.content

        # Warnings and Pregnancy were present in 2025, but MUST NOT be pulled into the 2026 result!
        assert result.sections.warnings_and_precautions.found is False
        assert result.sections.warnings_and_precautions.content == NOT_FOUND_MSG
        assert result.sections.pregnancy.found is False
        assert result.sections.pregnancy.content == NOT_FOUND_MSG

    @pytest.mark.asyncio
    async def test_03_latest_date_has_all_three_sections(self):
        """
        TEST 3: Latest date has AR, Warnings & Precautions, and Pregnancy.
        All three extracted in prioritized order.
        """
        extractor = FDASrLCExtractor()
        d_name, ingr, app, records = extractor.parse_supplement_records_from_detail_html(HTML_ALL_THREE_SECTIONS)

        result = await extractor.extract_latest_update(
            drug_name="ALLTHREEDRUG",
            active_ingredient="ALLTHREEINGR",
            application_number="NDA-33333",
            all_supplement_records=records,
        )

        assert result.latest_labeling_change_date == "08/15/2026"
        # Primary: AR
        assert result.sections.adverse_reactions.found is True
        assert "anaphylaxis, erythema multiforme" in result.sections.adverse_reactions.content
        # Secondary: WP
        assert result.sections.warnings_and_precautions.found is True
        assert "Severe Cutaneous Adverse Reactions" in result.sections.warnings_and_precautions.content
        # Secondary: Pregnancy
        assert result.sections.pregnancy.found is True
        assert "May cause fetal harm" in result.sections.pregnancy.content

    @pytest.mark.asyncio
    async def test_04_pregnancy_in_older_date_not_taken(self):
        """
        TEST 4: Latest date has AR and Warnings. Pregnancy exists only in an older update.
        Pregnancy must NOT be taken from the older update.
        """
        extractor = FDASrLCExtractor()
        d_name, ingr, app, records = extractor.parse_supplement_records_from_detail_html(HTML_PREGNANCY_IN_OLDER_ONLY)

        result = await extractor.extract_latest_update(
            drug_name="NOMIXDRUG",
            active_ingredient="NOMIXINGR",
            application_number="NDA-44444",
            all_supplement_records=records,
        )

        assert result.latest_labeling_change_date == "05/20/2026"
        assert result.sections.adverse_reactions.found is True
        assert result.sections.warnings_and_precautions.found is True

        # CRITICAL: Pregnancy must be NOT FOUND in latest applicable update
        assert result.sections.pregnancy.found is False
        assert result.sections.pregnancy.content == NOT_FOUND_MSG
        assert "animal reproduction studies" not in str(result.sections.pregnancy.content)

    @pytest.mark.asyncio
    async def test_05_latest_date_has_pregnancy_no_ar(self):
        """
        TEST 5: Latest date has Pregnancy but no Adverse Reactions.
        Identifies available sections and does NOT fabricate Adverse Reactions.
        """
        extractor = FDASrLCExtractor()
        d_name, ingr, app, records = extractor.parse_supplement_records_from_detail_html(HTML_PREGNANCY_NO_AR)

        result = await extractor.extract_latest_update(
            drug_name="PREGONLYDRUG",
            active_ingredient="PREGONLYINGR",
            application_number="NDA-55555",
            all_supplement_records=records,
        )

        assert result.latest_labeling_change_date == "09/10/2026"
        # Pregnancy found
        assert result.sections.pregnancy.found is True
        assert "Published observational studies" in result.sections.pregnancy.content

        # Adverse Reactions NOT fabricated
        assert result.sections.adverse_reactions.found is False
        assert result.sections.adverse_reactions.content == NOT_FOUND_MSG
        assert "Older adverse reaction" not in str(result.sections.adverse_reactions.content)

    @pytest.mark.asyncio
    async def test_06_multiple_records_same_latest_date_inspected(self):
        """
        TEST 6: Multiple FDA records share the same latest date.
        All relevant records for that date are inspected and aggregated.
        """
        record1 = FDASupplementRecord(
            header_text="11/12/2026 (SUPPL-01)",
            date_str="11/12/2026",
            date_obj=datetime(2026, 11, 12),
            supplement_id="SUPPL-01",
            sections=[{"raw_section": "6 Adverse Reactions", "text": "Adverse Reaction from Package A."}],
        )
        record2 = FDASupplementRecord(
            header_text="11/12/2026 (SUPPL-02)",
            date_str="11/12/2026",
            date_obj=datetime(2026, 11, 12),
            supplement_id="SUPPL-02",
            sections=[{"raw_section": "5 Warnings and Precautions", "text": "Warning from Package B."}],
        )

        extractor = FDASrLCExtractor()
        result = await extractor.extract_latest_update(
            drug_name="SAMEDATEDRUG",
            active_ingredient="SAMEDATEINGR",
            application_number="NDA-66666",
            all_supplement_records=[record1, record2],
        )

        assert result.latest_labeling_change_date == "11/12/2026"
        assert result.supplement_number == "SUPPL-01, SUPPL-02"
        # Both sections present on that same latest date must be extracted
        assert result.sections.adverse_reactions.found is True
        assert "Package A" in result.sections.adverse_reactions.content
        assert result.sections.warnings_and_precautions.found is True
        assert "Package B" in result.sections.warnings_and_precautions.content

    def test_07_no_product_match(self):
        """TEST 7: No product match -> Emits controlled empty list and logging."""
        parser = FDASrLCResultParser()
        candidates = parser.parse_search_results(
            HTML_SEARCH_RESULTS_ZYVOX, target_query="NonExistentMedicine999"
        )
        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_08_html_structure_differs_controlled_error(self):
        """TEST 8: FDA HTML structure differs from expected -> Controlled error handling."""
        extractor = FDASrLCExtractor()
        malformed_html = "<html><body><div>Unexpected FDA error or layout change</div></body></html>"
        d_name, ingr, app, records = extractor.parse_supplement_records_from_detail_html(malformed_html)

        assert len(records) == 0
        result = await extractor.extract_latest_update(
            drug_name="CORRUPTDRUG",
            active_ingredient=None,
            application_number=None,
            all_supplement_records=records,
        )

        assert result.sections.adverse_reactions.found is False
        assert result.sections.adverse_reactions.content == NOT_FOUND_MSG

    def test_09_same_fda_record_retrieved_twice_no_duplicate(self, db_session):
        """TEST 9: Same FDA record retrieved twice -> No duplicate database record."""
        drug_data = {
            "display_name": "TESTMED",
            "drug_name": "TESTMED",
            "active_ingredient": "TESTINGR",
            "application_number": "NDA-00001",
            "source": "FDA_SRLC",
        }
        drug1, is_new1 = DatabaseService.insert_or_update_drug(db_session, drug_data)
        assert is_new1 is True

        change_data = {
            "section": "Adverse Reactions",
            "change_type": "Labeling Revision",
            "source_date": datetime(2026, 6, 20),
            "updated_text": "Exact adverse reaction description.",
            "source_record_id": "SUPPL-100",
            "source": "FDA_SRLC",
        }

        # First save
        rec1, chg_new1 = DatabaseService.save_safety_change(db_session, drug1.id, change_data)
        assert chg_new1 is True

        # Second save with identical content
        rec2, chg_new2 = DatabaseService.save_safety_change(db_session, drug1.id, change_data)
        assert chg_new2 is False
        assert rec1.id == rec2.id

        # Query database to confirm strictly 1 row
        all_changes = DatabaseService.get_safety_changes_by_drug_id(db_session, drug1.id)
        assert len(all_changes) == 1

    @pytest.mark.asyncio
    async def test_10_pdf_extractor_retains_page_traceability(self):
        """TEST 10: Existing PDF extractor returns page-aware content -> Page numbers retained."""
        mock_pdf_handler = MagicMock()
        mock_pdf_handler.extract_fda_sections_from_pdf = AsyncMock(return_value={
            "section_6": {
                "content": "[Page 8] 6 ADVERSE REACTIONS\n\nPostmarketing reports...",
                "start_page": 8,
                "end_page": 9,
                "tables": [{"page": 8, "data": []}],
            },
            "section_5": None,
            "section_8": None,
        })

        record = FDASupplementRecord(
            header_text="06/09/2026 (SUPPL-50)",
            date_str="06/09/2026",
            date_obj=datetime(2026, 6, 9),
            supplement_id="SUPPL-50",
            document_url="https://example.com/test_label.pdf",
            sections=[{"raw_section": "6 Adverse Reactions", "text": "Postmarketing reports..."}],
        )

        extractor = FDASrLCExtractor(pdf_handler=mock_pdf_handler)
        result = await extractor.extract_latest_update(
            drug_name="PDFTESTMED",
            active_ingredient="PDFTESTINGR",
            application_number="NDA-77777",
            all_supplement_records=[record],
        )

        assert result.sections.adverse_reactions.found is True
        assert result.sections.adverse_reactions.page == "8-9"
        assert result.sections.adverse_reactions.document_url == "https://example.com/test_label.pdf"

    @pytest.mark.asyncio
    async def test_11_faithful_html_formatting_preserved(self):
        """TEST 11: Preserves exact HTML formatting (underlines, italics, bold subsections, bullets, and [see ...])."""
        sample_amoxil_html = """
        <div id="accordion">
            <h3>11/02/2022 (SUPPL-31)</h3>
            <div>
                <p><a href="http://example.com/amoxil.pdf">Approved Drug Label (PDF)</a></p>
                <h4>5 Warnings and Precautions</h4>
                <strong>5.2 Severe Cutaneous Adverse Reactions</strong>
                <div>
                    <p><i>New subsection added</i></p>
                    <p>AMOXIL may cause severe cutaneous adverse reactions (SCAR), such as Stevens-Johnson syndrome (SJS).</p>
                </div>
                <h4>6 Adverse Reactions</h4>
                <div>
                    <p><i>Additions and/or revisions underlined:</i></p>
                    <p>The following are discussed in more detail in other sections of the labeling:</p>
                    <ul>
                        <li><p>Anaphylactic reactions <i>[see Warnings and Precautions (5.1)]</i></p></li>
                        <li><p><u>Severe Cutaneous Adverse Reactions <i>[see Warnings and Precautions (5.2)]</i></u></p></li>
                    </ul>
                    <p><b>:6.2 Postmarketing Experience</b></p>
                    <p><i>Additions and/or revisions underlined</i></p>
                </div>
                <h4>17 PCI/PI/MG (Patient Counseling Information/Patient Information/Medication Guide)</h4>
                <div>
                    <p>MEDICATION GUIDE: Should not appear.</p>
                </div>
            </div>
        </div>
        """
        extractor = FDASrLCExtractor()
        d_name, ingr, app, records = extractor.parse_supplement_records_from_detail_html(sample_amoxil_html)
        assert len(records) == 1

        result = await extractor.extract_latest_update(
            drug_name="AMOXIL",
            active_ingredient="AMOXICILLIN",
            application_number="NDA-050542",
            all_supplement_records=records,
        )

        ar = result.sections.adverse_reactions
        wp = result.sections.warnings_and_precautions

        assert ar.found is True
        assert wp.found is True

        # Check section 5 HTML
        assert wp.html_content is not None
        assert "5.2 Severe Cutaneous Adverse Reactions" in wp.html_content
        assert "<i>New subsection added</i>" in wp.html_content
        assert "AMOXIL may cause severe cutaneous adverse reactions" in wp.html_content

        # Check section 6 HTML preserves underlines, italics, and bracketed cross-references
        assert ar.html_content is not None
        assert "Additions and/or revisions underlined:" in ar.html_content
        assert "<u>Severe Cutaneous Adverse Reactions" in ar.html_content
        assert "[see Warnings and Precautions (5.2)]" in ar.html_content
        assert ":6.2 Postmarketing Experience" in ar.html_content

        # Strict regulatory exclusion: Section 17 must NOT be in AR or WP
        assert "MEDICATION GUIDE" not in ar.html_content
        assert "PCI/PI/MG" not in ar.html_content
        assert "MEDICATION GUIDE" not in wp.html_content
