import pytest
from backend.pdf.headings import HeadingDetector
from backend.models.schemas import DocumentBlock, BlockType


def test_canonicalize_and_level():
    detector = HeadingDetector(body_font_size=11.0)
    assert detector.canonicalize_section_number("16.") == "16"
    assert detector.canonicalize_section_number("16.1") == "16.1"
    assert detector.canonicalize_section_number("16.1.1.") == "16.1.1"
    assert detector.calculate_level("16") == 1
    assert detector.calculate_level("16.1") == 2
    assert detector.calculate_level("16.1.1") == 3


def test_toc_rejection():
    detector = HeadingDetector(body_font_size=11.0)
    assert detector.is_toc_line("16. Safety Information .................... 20", 1) is True
    assert detector.is_toc_line("16.1 Adverse Events ....................... 24", 1) is True
    assert detector.is_toc_line("16. Safety Information", 2) is False


def test_in_text_citation_rejection():
    detector = HeadingDetector(body_font_size=11.0)
    assert detector.is_in_text_citation("See Section 16.1 for details.") is True
    assert detector.is_in_text_citation("In Section 16, adverse reactions were summarized.") is True
    assert detector.is_in_text_citation("16.1% of patients experienced headache.") is True
    assert detector.is_in_text_citation("16.1 Adverse Events") is False
    assert detector.is_in_text_citation("16. SAFETY INFORMATION") is False


def test_match_heading_real():
    detector = HeadingDetector(body_font_size=11.0)
    match = detector.match_heading("16. SAFETY INFORMATION", page_num=2)
    assert match is not None
    assert match[0] == "16"
    assert "SAFETY INFORMATION" in match[1]

    sub_match = detector.match_heading("16.1 Adverse Events", page_num=2)
    assert sub_match is not None
    assert sub_match[0] == "16.1"
    assert sub_match[1] == "Adverse Events"
    assert sub_match[2] == 2
