"""
Comprehensive Integration and Unit Tests for FDA MedWatch Crawler & Adapter.
Tests all 12 required test cases:
1. Path A: MedWatch article -> Product Information intermediate page -> PDF -> Adverse Reactions
2. Path B: MedWatch article -> Direct 'View full prescribing information' link -> FDA PDF
3. Both links present: Authoritative document selected without duplicate processing
4. Multi-PDF version selection based on date/supplement, not link order
5. Section 6 ADVERSE REACTIONS extraction completeness
6. Adverse reaction table extraction (columns, rows, percentages, page numbers)
7. Section 5 WARNINGS AND PRECAUTIONS extraction
8. Section 8.1 PREGNANCY extraction
9. Section not found in PDF -> NOT FOUND IN THIS PRODUCT INFORMATION DOCUMENT without fabrication
10. MedWatch article found with no product PDF -> store article, mark label unavailable
11. Strict historical version isolation: NEVER mix content across versions
12. Duplicate PDF link deduplication
13. Untrusted third-party domain rejection
14. Database persistence and traceability
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
import fitz

from app.models.drug import Drug
from app.services.database_service import DatabaseService
from app.sources.fda_medwatch.adapter import FDAMedWatchAdapter
from app.sources.fda_medwatch.config import (
    NO_OFFICIAL_PRODUCT_LABEL_FOUND,
    NOT_FOUND_IN_DOC_MSG,
    SOURCE_ID,
)
from app.sources.fda_medwatch.crawler import FDAMedWatchCrawler
from app.sources.fda_medwatch.link_discovery import FDAMedWatchLinkDiscovery
from app.sources.fda_medwatch.models import (
    MedWatchArticle,
    MedWatchDocumentInfo,
    MedWatchSectionItem,
)
from app.sources.fda_medwatch.pdf_handler import FDAMedWatchPDFHandler
from app.sources.fda_medwatch.product_information import FDAMedWatchProductInformation
from app.sources.fda_medwatch.section_extractor import FDAMedWatchSectionExtractor
from app.sources.fda_medwatch.version_selector import FDAMedWatchVersionSelector

SAMPLE_AKEEGA_PDF = Path(__file__).resolve().parents[4] / "data" / "pdf_cache" / "test_akeega.pdf"


def create_mock_pdf_bytes(
    product_name: str = "AKEEGA",
    active_ingredient: str = "Niraparib",
    has_sec5: bool = True,
    has_sec6: bool = True,
    has_sec8: bool = True,
    sec6_table: bool = False,
) -> bytes:
    """Creates an in-memory PDF with precise FDA labeling sections for isolated unit testing."""
    doc = fitz.open()

    # Page 1: Title & Highlights
    p1 = doc.new_page()
    p1.insert_text((50, 50), f"HIGHLIGHTS OF PRESCRIBING INFORMATION\n{product_name} ({active_ingredient})\nThese highlights do not include all the info.\n")

    # Page 2: Table of Contents
    p2 = doc.new_page()
    p2.insert_text((50, 50), "FULL PRESCRIBING INFORMATION: CONTENTS*\n5 WARNINGS AND PRECAUTIONS\n6 ADVERSE REACTIONS\n8 USE IN SPECIFIC POPULATIONS\n")

    # Page 3: Body Sections
    p3 = doc.new_page()
    y = 50
    if has_sec5:
        p3.insert_text((50, y), "5 WARNINGS AND PRECAUTIONS\n5.1 Severe Hepatotoxicity\nMonitor liver function tests before initiating therapy.")
        y += 120

    if has_sec6:
        p3.insert_text((50, y), "6 ADVERSE REACTIONS\n6.1 Clinical Trials Experience\nThe most common adverse reactions (>10%) were nausea and fatigue.\n\n6.2 Postmarketing Experience\nRare cases of anaphylaxis have been reported.")
        y += 120

    if has_sec8:
        p3.insert_text((50, y), f"8.1 PREGNANCY\nRisk Summary: {product_name} can cause fetal harm when administered to a pregnant female.")
        y += 100

    # Stop section 10
    p3.insert_text((50, y), "10 OVERDOSAGE\nIn case of overdose, monitor patient for signs of toxicity.")

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ==============================================================================
# TEST 1: Path A - Intermediate Product Information Page -> PDF
# ==============================================================================
@pytest.mark.asyncio
async def test_1_path_a_intermediate_product_info_page():
    crawler = FDAMedWatchCrawler()

    article_html = """
    <html><body>
        <h1>FDA MedWatch Alert: Serious Risks Associated with Medicine X</h1>
        <p>Healthcare professionals should review the official product details.</p>
        <a href="https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo=216793">Product Information</a>
    </body></html>
    """

    product_info_html = """
    <html><body>
        <h2>Drugs@FDA Application Details for NDA 216793</h2>
        <a href="https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/216793s000lbl.pdf">Label (PDF)</a>
    </body></html>
    """

    async def mock_get_page(url):
        if "overview.process" in url:
            return product_info_html
        return article_html

    crawler.get_page = AsyncMock(side_effect=mock_get_page)

    mock_pdf = create_mock_pdf_bytes(product_name="Medicine X", active_ingredient="Compound X", has_sec5=True, has_sec6=True, has_sec8=True)
    crawler.pdf_handler.fetch_pdf_bytes = AsyncMock(return_value=mock_pdf)

    art = MedWatchArticle(
        title="FDA MedWatch Alert: Medicine X",
        url="https://www.fda.gov/safety/medwatch/medicine-x-alert",
        publication_date="2024-03-15",
    )

    result = await crawler.process_article_or_url(
        article=art,
        target_product="Medicine X",
        active_ingredient="Compound X",
    )

    assert result is not None
    assert result["display_name"] == "MEDICINE X"
    assert result["source"] == SOURCE_ID

    struct = result["structured_result"]
    assert struct["status"] == "SUCCESS"
    assert struct["product_information"]["found"] is True
    assert "216793s000lbl.pdf" in struct["product_information"]["pdf_url"]

    sections = struct["sections"]
    assert sections["adverse_reactions"]["found"] is True
    assert "nausea and fatigue" in sections["adverse_reactions"]["content"].lower()


# ==============================================================================
# TEST 2: Path B - Direct Prescribing Information PDF
# ==============================================================================
@pytest.mark.asyncio
async def test_2_path_b_direct_prescribing_info_pdf():
    crawler = FDAMedWatchCrawler()

    article_html = """
    <html><body>
        <h1>FDA Approves Akeega with Prednisone</h1>
        <p>The FDA approved niraparib and abiraterone acetate.</p>
        <a href="https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/216793s000lbl.pdf">View full prescribing information for Akeega.</a>
    </body></html>
    """

    crawler.get_page = AsyncMock(return_value=article_html)
    mock_pdf = create_mock_pdf_bytes(has_sec5=True, has_sec6=True, has_sec8=True)
    crawler.pdf_handler.fetch_pdf_bytes = AsyncMock(return_value=mock_pdf)

    art = MedWatchArticle(
        title="FDA Approves Akeega",
        url="https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-akeega",
        publication_date="2023-08-11",
    )

    result = await crawler.process_article_or_url(
        article=art,
        target_product="Akeega",
        active_ingredient="Niraparib / Abiraterone",
    )

    assert result is not None
    struct = result["structured_result"]
    assert struct["status"] == "SUCCESS"
    assert "216793s000lbl.pdf" in struct["product_information"]["pdf_url"]
    assert struct["sections"]["adverse_reactions"]["found"] is True


# ==============================================================================
# TEST 3: Both Links Present - Prioritize & Avoid Duplicate Processing
# ==============================================================================
@pytest.mark.asyncio
async def test_3_both_links_present_prioritize_and_deduplicate():
    crawler = FDAMedWatchCrawler()

    article_html = """
    <html><body>
        <h1>Safety Information</h1>
        <a href="https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo=216793">Product Information</a>
        <a href="https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/216793s000lbl.pdf">View full prescribing information for Akeega.</a>
    </body></html>
    """

    crawler.get_page = AsyncMock(return_value=article_html)
    mock_pdf = create_mock_pdf_bytes(has_sec5=True, has_sec6=True, has_sec8=True)
    crawler.pdf_handler.fetch_pdf_bytes = AsyncMock(return_value=mock_pdf)

    art = MedWatchArticle(
        title="Safety Info",
        url="https://www.fda.gov/safety/medwatch/article-3",
    )

    result = await crawler.process_article_or_url(
        article=art,
        target_product="Akeega",
    )

    assert result is not None
    # Verify PDF was only extracted once
    assert crawler.pdf_handler.fetch_pdf_bytes.call_count == 1


# ==============================================================================
# TEST 4: Multi-PDF Version Selection (Not Link Order)
# ==============================================================================
def test_4_multi_pdf_version_selection_not_link_order():
    docs = [
        MedWatchDocumentInfo(
            found=True,
            pdf_url="https://www.accessdata.fda.gov/drugsatfda_docs/label/2021/100000s000lbl.pdf",
            document_date="2021-01-01",
            version="2021-s000",
        ),
        MedWatchDocumentInfo(
            found=True,
            pdf_url="https://www.accessdata.fda.gov/drugsatfda_docs/label/2025/100000s002lbl.pdf",
            document_date="2025-05-15",
            version="2025-s002",
        ),
        MedWatchDocumentInfo(
            found=True,
            pdf_url="https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/100000s001lbl.pdf",
            document_date="2023-08-20",
            version="2023-s001",
        ),
    ]

    latest, historical = FDAMedWatchVersionSelector.select_latest_document(docs)
    assert latest is not None
    # 2025 document must be selected despite being listed 2nd in HTML order
    assert "2025" in latest.pdf_url
    assert latest.version == "2025-s002"
    assert len(historical) == 2


# ==============================================================================
# TEST 5: Section 6 ADVERSE REACTIONS Extraction Completeness
# ==============================================================================
@pytest.mark.asyncio
async def test_5_section_6_adverse_reactions_extraction():
    handler = FDAMedWatchPDFHandler()
    if not SAMPLE_AKEEGA_PDF.exists():
        pytest.skip("Sample Akeega PDF not available on disk")

    sections = await handler.extract_sections(
        pdf_source=SAMPLE_AKEEGA_PDF,
        doc_name="216793s000lbl.pdf",
    )

    ar = sections["adverse_reactions"]
    assert ar.found is True
    assert ar.section == "6. ADVERSE REACTIONS"
    assert "9" in ar.page  # Spans starting from page 9
    assert "Clinical Trial Experience" in ar.content
    assert len(ar.content) > 1000


# ==============================================================================
# TEST 6: Adverse Reaction Table Extraction
# ==============================================================================
@pytest.mark.asyncio
async def test_6_adverse_reaction_table_extraction():
    handler = FDAMedWatchPDFHandler()
    if not SAMPLE_AKEEGA_PDF.exists():
        pytest.skip("Sample Akeega PDF not available on disk")

    sections = await handler.extract_sections(
        pdf_source=SAMPLE_AKEEGA_PDF,
        doc_name="216793s000lbl.pdf",
    )

    ar = sections["adverse_reactions"]
    assert ar.found is True
    assert len(ar.tables) >= 2

    # Check table structure preservation
    tbl = ar.tables[0]
    assert tbl.get("page") in (11, 12) or any(p in (11, 12) for p in tbl.get("pages", []))
    assert len(tbl.get("headers", [])) > 0 or len(tbl.get("columns", [])) > 0
    assert len(tbl.get("rows", [])) > 0


# ==============================================================================
# TEST 7: Section 5 WARNINGS AND PRECAUTIONS Extraction
# ==============================================================================
@pytest.mark.asyncio
async def test_7_section_5_warnings_and_precautions():
    handler = FDAMedWatchPDFHandler()
    if not SAMPLE_AKEEGA_PDF.exists():
        pytest.skip("Sample Akeega PDF not available on disk")

    sections = await handler.extract_sections(
        pdf_source=SAMPLE_AKEEGA_PDF,
        doc_name="216793s000lbl.pdf",
    )

    wp = sections["warnings_and_precautions"]
    assert wp.found is True
    assert wp.section == "5. WARNINGS AND PRECAUTIONS"
    assert "6" in wp.page  # Spans starting from page 6
    assert "Posterior Reversible Encephalopathy Syndrome" in wp.content


# ==============================================================================
# TEST 8: Section 8.1 PREGNANCY Extraction
# ==============================================================================
@pytest.mark.asyncio
async def test_8_section_8_1_pregnancy():
    handler = FDAMedWatchPDFHandler()
    if not SAMPLE_AKEEGA_PDF.exists():
        pytest.skip("Sample Akeega PDF not available on disk")

    sections = await handler.extract_sections(
        pdf_source=SAMPLE_AKEEGA_PDF,
        doc_name="216793s000lbl.pdf",
    )

    preg = sections["pregnancy"]
    assert preg.found is True
    assert "13" in preg.page  # Located on page 13
    assert "fetal harm" in preg.content.lower()


# ==============================================================================
# TEST 9: Section Not Found in PDF - No Fabrication
# ==============================================================================
@pytest.mark.asyncio
async def test_9_section_not_found_no_fabrication():
    handler = FDAMedWatchPDFHandler()
    # Create PDF with Sec 5 and Sec 6, but NO Pregnancy
    pdf_bytes = create_mock_pdf_bytes(has_sec5=True, has_sec6=True, has_sec8=False)

    sections = await handler.extract_sections(
        pdf_source=pdf_bytes,
        doc_name="no_preg.pdf",
    )

    assert sections["adverse_reactions"].found is True
    assert sections["pregnancy"].found is False
    assert sections["pregnancy"].content == NOT_FOUND_IN_DOC_MSG


# ==============================================================================
# TEST 10: Only MedWatch Article Found - No Product PDF Available
# ==============================================================================
@pytest.mark.asyncio
async def test_10_only_medwatch_article_no_pdf():
    extractor = FDAMedWatchSectionExtractor()

    art = MedWatchArticle(
        title="MedWatch Alert: Device or Non-Label Safety Event",
        url="https://www.fda.gov/safety/medwatch/event-10",
        publication_date="2024-01-20",
        summary="Reporting instruction only, no prescribing document exists.",
    )

    result = await extractor.extract_from_document(
        product="Unlabeled Product",
        active_ingredient="Unknown",
        application_number=None,
        article=art,
        document=None,  # No PDF found
    )

    assert result.status == NO_OFFICIAL_PRODUCT_LABEL_FOUND
    assert result.sections["adverse_reactions"]["found"] is False
    assert result.sections["adverse_reactions"]["content"] == NO_OFFICIAL_PRODUCT_LABEL_FOUND
    assert result.medwatch_article["title"] == "MedWatch Alert: Device or Non-Label Safety Event"


# ==============================================================================
# TEST 11: Strict Historical Version Isolation - NEVER Mix Content
# ==============================================================================
@pytest.mark.asyncio
async def test_11_strict_historical_version_isolation_no_mixing():
    """
    If 2026 PDF has Adverse Reactions & Warnings but NO Pregnancy,
    and 2024 PDF has Pregnancy, the system must NOT backfill Pregnancy into the 2026 result.
    """
    crawler = FDAMedWatchCrawler()

    # 2026 latest document (no pregnancy)
    doc_2026 = MedWatchDocumentInfo(
        found=True,
        pdf_url="https://www.accessdata.fda.gov/drugsatfda_docs/label/2026/216793s002lbl.pdf",
        document_date="2026-01-01",
        version="2026-s002",
    )

    # Mock PDF handler returning 2026 PDF (pregnancy missing)
    pdf_2026_bytes = create_mock_pdf_bytes(product_name="Medicine 2026", active_ingredient="Ingr 2026", has_sec5=True, has_sec6=True, has_sec8=False)
    crawler.pdf_handler.fetch_pdf_bytes = AsyncMock(return_value=pdf_2026_bytes)

    art = MedWatchArticle(
        title="MedWatch Alert: Medicine 2026 Update",
        url="https://www.fda.gov/safety/medwatch/medicine-2026",
    )

    # Directly run extractor with 2026 document
    res = await crawler.section_extractor.extract_from_document(
        product="Medicine 2026",
        active_ingredient="Ingr 2026",
        application_number="NDA-2026",
        article=art,
        document=doc_2026,
    )

    assert res.sections["adverse_reactions"]["found"] is True
    assert res.sections["warnings_and_precautions"]["found"] is True
    # Pregnancy MUST be marked as NOT FOUND IN THIS PRODUCT INFORMATION DOCUMENT
    assert res.sections["pregnancy"]["found"] is False
    assert res.sections["pregnancy"]["content"] == NOT_FOUND_IN_DOC_MSG


# ==============================================================================
# TEST 12: Duplicate Link Deduplication
# ==============================================================================
def test_12_duplicate_link_deduplication():
    discovery = FDAMedWatchLinkDiscovery()

    html = """
    <html><body>
        <a href="https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/216793s000lbl.pdf">View full prescribing information</a>
        <p>Also available here:</p>
        <a href="https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/216793s000lbl.pdf">FDA-approved labeling</a>
    </body></html>
    """

    links = discovery.discover_links(html, source_page_url="https://www.fda.gov/safety")
    # Only 1 unique PDF link should be discovered
    assert len(links) == 1
    assert links[0].url == "https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/216793s000lbl.pdf"


# ==============================================================================
# TEST 13: Untrusted Third-Party Domain Rejection
# ==============================================================================
def test_13_untrusted_third_party_domain_rejection():
    discovery = FDAMedWatchLinkDiscovery()

    html = """
    <html><body>
        <a href="https://www.pharma-thirdparty-untrusted.com/labels/fake_label.pdf">Prescribing Information</a>
        <a href="https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/216793s000lbl.pdf">Official FDA Label</a>
    </body></html>
    """

    links = discovery.discover_links(html, source_page_url="https://www.fda.gov/safety")
    # Third party link rejected, only official FDA link kept
    assert len(links) == 1
    assert "accessdata.fda.gov" in links[0].url


# ==============================================================================
# TEST 14: Database Persistence & Traceability
# ==============================================================================
@pytest.mark.asyncio
async def test_14_database_persistence_and_traceability(db):
    crawler = FDAMedWatchCrawler()

    # Mock article with direct PDF
    article_html = """
    <html><body>
        <h1>FDA MedWatch Alert: Medicine Test</h1>
        <a href="https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/216793s000lbl.pdf">View full prescribing information for Medicine Test</a>
    </body></html>
    """
    crawler.get_page = AsyncMock(return_value=article_html)
    mock_pdf = create_mock_pdf_bytes(product_name="Medicine Test", active_ingredient="TESTIUM", has_sec5=True, has_sec6=True, has_sec8=True)
    crawler.pdf_handler.fetch_pdf_bytes = AsyncMock(return_value=mock_pdf)

    # Mock search client to return our test article
    art = MedWatchArticle(
        title="FDA MedWatch Alert: Medicine Test",
        url="https://www.fda.gov/safety/medwatch/medicine-test",
        publication_date="2024-02-01",
    )
    crawler.search_client.article_discovery.discover_articles = AsyncMock(return_value=[art])
    crawler.search_client.fetch_openfda_drug_metadata = AsyncMock(return_value={
        "brand_name": "MEDICINE TEST",
        "active_ingredient": "TESTIUM",
        "application_number": "NDA-999999",
        "sponsor": "TEST PHARMA INC",
    })

    adapter = FDAMedWatchAdapter(crawler=crawler)
    drugs = await adapter.search("Medicine Test", db=db, force_refresh=True)

    assert len(drugs) >= 1
    d = drugs[0]
    assert d.source == SOURCE_ID
    assert d.display_name == "MEDICINE TEST"

    changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
    assert len(changes) >= 3

    sec_names = {c.section.lower() for c in changes}
    assert any("adverse reactions" in s for s in sec_names)
    assert any("warnings" in s for s in sec_names)
    assert any("safety communication" in s for s in sec_names)

    # Verify traceability
    ar_change = next(c for c in changes if "adverse" in c.section.lower())
    assert "216793s000lbl.pdf" in ar_change.source_url
    assert "Official FDA Prescribing Information PDF" in ar_change.fda_comment


# ==============================================================================
# TEST 15: Section 6 Subsections Detection & Preservation
# ==============================================================================
@pytest.mark.asyncio
async def test_15_subsections_detection_and_preservation():
    handler = FDAMedWatchPDFHandler()
    if not SAMPLE_AKEEGA_PDF.exists():
        pytest.skip("Sample Akeega PDF not available on disk")

    sections = await handler.extract_sections(
        pdf_source=SAMPLE_AKEEGA_PDF,
        doc_name="216793s000lbl.pdf",
        target_product="AKEEGA",
    )

    ar = sections["adverse_reactions"]
    assert ar.found is True
    assert len(ar.subsections) >= 1

    # Check subsection fields
    sub = ar.subsections[0]
    assert "name" in sub
    assert "pages" in sub
    assert "content" in sub
    assert len(sub["content"]) > 0
    assert any("clinical trial" in s["name"].lower() for s in ar.subsections)


# ==============================================================================
# TEST 16: Multi-Page Section 6 Span & Multi-Page Table Continuation
# ==============================================================================
@pytest.mark.asyncio
async def test_16_multipage_section_and_table_continuation():
    handler = FDAMedWatchPDFHandler()
    if not SAMPLE_AKEEGA_PDF.exists():
        pytest.skip("Sample Akeega PDF not available on disk")

    sections = await handler.extract_sections(
        pdf_source=SAMPLE_AKEEGA_PDF,
        doc_name="216793s000lbl.pdf",
        target_product="AKEEGA",
    )

    ar = sections["adverse_reactions"]
    assert ar.found is True
    # Section 6 spans pages 9 through 12
    assert len(ar.pages) >= 3
    assert 9 in ar.pages
    assert 12 in ar.pages

    # Check that multi-page continuation tables combine pages
    multi_page_tables = [t for t in ar.tables if len(t.get("pages", [])) > 1]
    assert len(multi_page_tables) >= 1
    assert multi_page_tables[0]["pages"] == [11, 12]


# ==============================================================================
# TEST 17: Section 6 Not Found in PDF -> ADVERSE_REACTIONS_SECTION_NOT_FOUND
# ==============================================================================
@pytest.mark.asyncio
async def test_17_adverse_reactions_section_not_found():
    handler = FDAMedWatchPDFHandler()
    # Create mock PDF without section 6
    pdf_bytes = create_mock_pdf_bytes(product_name="NO_SEC6_MED", has_sec5=True, has_sec6=False, has_sec8=True)

    sections = await handler.extract_sections(
        pdf_source=pdf_bytes,
        doc_name="no_sec6.pdf",
        target_product="NO_SEC6_MED",
    )

    ar = sections["adverse_reactions"]
    assert ar.found is False
    assert ar.status == "ADVERSE_REACTIONS_SECTION_NOT_FOUND"
    assert ar.content == NOT_FOUND_IN_DOC_MSG


# ==============================================================================
# TEST 18: Corrupted PDF -> PDF_EXTRACTION_FAILED
# ==============================================================================
@pytest.mark.asyncio
async def test_18_corrupted_pdf_extraction_failed():
    handler = FDAMedWatchPDFHandler()
    corrupt_bytes = b"not a valid pdf file content"

    sections = await handler.extract_sections(
        pdf_source=corrupt_bytes,
        doc_name="corrupt.pdf",
        target_product="ANY_PRODUCT",
    )

    ar = sections["adverse_reactions"]
    assert ar.found is False
    assert ar.status == "PDF_EXTRACTION_FAILED"


# ==============================================================================
# TEST 19: Product Mismatch Rejection
# ==============================================================================
@pytest.mark.asyncio
async def test_19_product_mismatch_rejection():
    handler = FDAMedWatchPDFHandler()
    if not SAMPLE_AKEEGA_PDF.exists():
        pytest.skip("Sample Akeega PDF not available on disk")

    # Pass Akeega PDF but ask for "Ozempic" (which does not exist in Akeega's labeling)
    sections = await handler.extract_sections(
        pdf_source=SAMPLE_AKEEGA_PDF,
        doc_name="216793s000lbl.pdf",
        target_product="Ozempic",
        active_ingredient="Semaglutide",
    )

    ar = sections["adverse_reactions"]
    assert ar.found is False
    assert ar.status == "PRODUCT_MISMATCH_REJECTED"


# ==============================================================================
# TEST 20: UI Rendering of Prescribing Information Section 6
# ==============================================================================
def test_20_ui_rendering_prescribing_information():
    from app.ui import _render_fda_medwatch_drug_detail

    mock_drug = {
        "id": 101,
        "display_name": "AKEEGA",
        "active_ingredient": "Niraparib and Abiraterone Acetate",
        "sponsor": "Janssen Biotech, Inc.",
        "application_number": "NDA 216793",
        "detail_url": "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo=216793",
    }

    mock_changes = [
        {
            "section": "Adverse Reactions",
            "change_type": "Official Prescribing Information (Section 6)",
            "source_date": "2023-08-11",
            "source_url": "https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/216793s000lbl.pdf",
            "source_record_id": "MW-LBL-AKEEGA-SEC6",
            "fda_comment": "Official FDA Prescribing Information PDF: https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/216793s000lbl.pdf (Pages: 9–12 | Subsections: 2 | Tables: 2)",
            "updated_text": """### 6 ADVERSE REACTIONS

The following clinically significant adverse reactions are described elsewhere in the labeling:
• Hepatotoxicity [see Warnings and Precautions (5.1)]

### 6.1 Clinical Trials Experience

Because clinical trials are conducted under widely varying conditions, adverse reaction rates observed cannot be directly compared.

### Table 3: Adverse Reactions (≥10%) in Patients Receiving AKEEGA
| Adverse Reaction | AKEEGA (%) | Placebo (%) |
| --- | --- | --- |
| Musculoskeletal pain | 44 | 42 |
| Fatigue | 43 | 30 |

### 6.2 Postmarketing Experience

The following adverse reactions have been identified during post-approval use.""",
        },
        {
            "section": "MedWatch Safety Communication",
            "change_type": "FDA MedWatch Alert: Serious Safety Update",
            "source_date": "2024-01-15",
            "source_url": "https://www.fda.gov/safety/medwatch/alert-akeega",
            "source_record_id": "MW-ART-12345678",
            "updated_text": "FDA communicates safety notification regarding hepatic enzyme monitoring.",
        }
    ]

    html_out = _render_fda_medwatch_drug_detail(mock_drug, mock_changes)

    # 1. Verify Prescribing Information banner is rendered
    assert "mw-pi-banner" in html_out
    assert "Full Prescribing Information" in html_out
    assert "6. ADVERSE REACTIONS" in html_out
    assert "9–12" in html_out

    # 2. Verify Section headings and Subsections are rendered
    assert "mw-sec-heading" in html_out
    assert "Clinical Trials Experience" in html_out
    assert "Postmarketing Experience" in html_out

    # 3. Verify HTML table is rendered semantically
    assert "tga-table" in html_out
    assert "Musculoskeletal pain" in html_out
    assert "Fatigue" in html_out

    # 4. Verify Official FDA Source PDF link is rendered
    assert "btn-mw-source-pdf" in html_out
    assert "216793s000lbl.pdf" in html_out


# ==============================================================================
# TEST 21: API Endpoint Adverse Reactions Schema Conformance
# ==============================================================================
@pytest.mark.asyncio
async def test_21_api_adverse_reactions_schema(db):
    from unittest.mock import MagicMock
    from app.api.drugs import get_drug_adverse_reactions_report

    mock_db = MagicMock()
    mock_drug = MagicMock()
    mock_drug.id = 55
    mock_drug.display_name = "AKEEGA"
    mock_drug.source = "FDA_MEDWATCH"
    mock_drug.active_ingredient = "Niraparib / Abiraterone"
    mock_drug.detail_url = "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?ApplNo=216793"

    mock_change_pi = MagicMock()
    mock_change_pi.section = "Adverse Reactions"
    mock_change_pi.change_type = "Official Prescribing Information (Section 6)"
    mock_change_pi.source_url = "https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/216793s000lbl.pdf"
    mock_change_pi.fda_comment = "Official FDA Prescribing Information PDF: https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/216793s000lbl.pdf (Pages: 9–12 | Subsections: 2 | Tables: 1)"
    mock_change_pi.source_date = "2023-08-11"
    mock_change_pi.updated_text = """### 6 ADVERSE REACTIONS
[Page 9]
Clinical trial information text here.

### 6.1 Clinical Trials Experience
[Page 10]
Detailed trials text.

### Table 1: Adverse Reactions
| Reaction | Drug (%) | Placebo (%) |
| --- | --- | --- |
| Headache | 15 | 5 |

### 6.2 Postmarketing Experience
[Page 12]
Postmarketing details."""

    mock_change_art = MagicMock()
    mock_change_art.section = "MedWatch Safety Communication"
    mock_change_art.change_type = "FDA MedWatch Alert"
    mock_change_art.source_url = "https://www.fda.gov/safety/medwatch/article"
    mock_change_art.source_date = "2023-08-11"
    mock_change_art.updated_text = "MedWatch safety alert summary."

    with patch("app.api.drugs.DatabaseService.get_drug_by_id", return_value=mock_drug), \
         patch("app.api.drugs.DatabaseService.get_safety_changes_by_drug_id", return_value=[mock_change_pi, mock_change_art]):

        resp = await get_drug_adverse_reactions_report(drug_id=55, db=mock_db)

        assert resp["product"] == "AKEEGA"
        assert resp["source"] == "FDA MedWatch"
        assert "medwatch_article" in resp
        assert "product_information" in resp
        assert resp["product_information"]["document_found"] is True
        assert "216793s000lbl.pdf" in resp["product_information"]["pdf_url"]

        ar_data = resp["adverse_reactions"]
        assert ar_data["found"] is True
        assert "6. ADVERSE REACTIONS" in ar_data["section"]
        assert 9 in ar_data["pages"]

        # Subsections
        assert len(ar_data["subsections"]) >= 2
        sub_names = [s["name"] for s in ar_data["subsections"]]
        assert any("Clinical Trials Experience" in n for n in sub_names)
        assert any("Postmarketing Experience" in n for n in sub_names)

        # Tables
        assert len(ar_data["tables"]) >= 1
        tbl = ar_data["tables"][0]
        assert "Table 1" in tbl["title"]
        assert "Reaction" in tbl["headers"]
        assert len(tbl["rows"]) >= 1

