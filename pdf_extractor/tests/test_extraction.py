import pytest
from pathlib import Path
from backend.extraction.section_extractor import SectionExtractor

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_extraction_basic():
    pdf_path = FIXTURES_DIR / "test1_basic.pdf"
    extractor = SectionExtractor()
    result = extractor.extract(
        file_path_or_bytes=pdf_path,
        main_section="16",
        target_subsection="16.1",
        doc_name="test1_basic.pdf"
    )

    assert result.status == "success"
    assert result.validation.was_main_section_found is True
    assert result.validation.was_target_subsection_found is True
    assert "16" in result.validation.included_sections
    assert "16.1" in result.validation.included_sections
    assert "16.2" in result.validation.excluded_sections
    assert "16.2" not in result.validation.included_sections
    assert "17" not in result.validation.included_sections
    assert "Safety Information" in result.content
    assert "Adverse Events" in result.content
    assert "Laboratory Findings" not in result.content


def test_extraction_deep_subsections():
    pdf_path = FIXTURES_DIR / "test2_deep_subsections.pdf"
    extractor = SectionExtractor()
    result = extractor.extract(
        file_path_or_bytes=pdf_path,
        main_section="16",
        target_subsection="16.1",
        doc_name="test2_deep_subsections.pdf"
    )

    assert result.status == "success"
    assert "16" in result.validation.included_sections
    assert "16.1" in result.validation.included_sections
    assert "16.1.1" in result.validation.included_sections
    assert "16.1.2" in result.validation.included_sections
    assert "16.2" not in result.validation.included_sections
    assert "17" not in result.validation.included_sections
    assert "Serious Events" in result.content
    assert "Non-serious Events" in result.content
    assert "Laboratory Findings" not in result.content


def test_extraction_multipage():
    pdf_path = FIXTURES_DIR / "test3_multipage.pdf"
    extractor = SectionExtractor()
    result = extractor.extract(
        file_path_or_bytes=pdf_path,
        main_section="16",
        target_subsection="16.1",
        doc_name="test3_multipage.pdf"
    )

    assert result.status == "success"
    assert result.start_page == 2
    assert result.end_page == 5
    assert result.validation.was_main_section_found is True
    assert "16.2" in result.validation.excluded_sections
    # Pages 6 and 7 must not be included
    pages_in_blocks = {b.page for b in result.blocks}
    assert 1 not in pages_in_blocks
    assert 6 not in pages_in_blocks
    assert 7 not in pages_in_blocks


def test_extraction_same_page_boundary():
    pdf_path = FIXTURES_DIR / "test4_same_page_boundary.pdf"
    extractor = SectionExtractor()
    result = extractor.extract(
        file_path_or_bytes=pdf_path,
        main_section="16",
        target_subsection="16.1",
        doc_name="test4_same_page_boundary.pdf"
    )

    assert result.status == "success"
    assert "16" in result.validation.included_sections
    assert "16.1" in result.validation.included_sections
    assert "16.1.1" in result.validation.included_sections
    assert "16.1.2" in result.validation.included_sections
    assert "16.2" in result.validation.excluded_sections
    assert "16.2" not in result.validation.included_sections
    # Block-level check: content must have 16.1.2 but not 16.2
    assert "Non-serious Events" in result.content
    assert "Laboratory Findings" not in result.content


def test_extraction_toc_handling():
    pdf_path = FIXTURES_DIR / "test6_toc.pdf"
    extractor = SectionExtractor()
    result = extractor.extract(
        file_path_or_bytes=pdf_path,
        main_section="16",
        target_subsection="16.1",
        doc_name="test6_toc.pdf"
    )

    assert result.status == "success"
    # Page 1 was TOC, actual section starts on Page 2
    assert result.start_page == 2
    assert "16.2" in result.validation.excluded_sections
    assert "Real adverse events body text" in result.content
    assert "Pharmacology" not in result.content


def test_extraction_in_text_citation():
    pdf_path = FIXTURES_DIR / "test7_in_text_citation.pdf"
    extractor = SectionExtractor()
    result = extractor.extract(
        file_path_or_bytes=pdf_path,
        main_section="16",
        target_subsection="16.1",
        doc_name="test7_in_text_citation.pdf"
    )

    assert result.status == "success"
    assert "16" in result.validation.included_sections
    assert "16.1" in result.validation.included_sections
    assert "16.2" not in result.validation.included_sections
    assert "Official adverse events section body text" in result.content
    assert "Laboratory Findings" not in result.content
