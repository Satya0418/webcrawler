"""
Unit tests for Section 4.6 and Section 4.8 extraction (section_extractor.py & pdf_handler.py).
"""
from pathlib import Path
import pytest

from app.sources.australia_tga.config import (
    MISSING_SECTION_4_6_TEXT,
    MISSING_SECTION_4_8_TEXT,
    SECTION_4_6_NUM,
    SECTION_4_8_NUM,
)
from app.sources.australia_tga.pdf_handler import TGAPDFHandler
from app.sources.australia_tga.section_extractor import TGASectionExtractor


class TestTGASectionExtractor:
    """Tests for TGASectionExtractor and TGAPDFHandler integration."""

    def test_extract_section_4_6_success(self):
        mock_raw = {
            "status": "success",
            "start_page": 8,
            "end_page": 9,
            "content": (
                "4.6. FERTILITY, PREGNANCY AND LACTATION\n\n"
                "Effects on fertility:\n"
                "Ofloxacin did not compromise fertility in male and female rats.\n\n"
                "Use in pregnancy (Category B3):\n"
                "There are no adequate studies in pregnant women.\n\n"
                "Use in lactation:\n"
                "Ofloxacin is excreted in human milk.\n\n"
                "4.7 EFFECTS ON ABILITY TO DRIVE AND USE MACHINES\n"
                "No studies on the effects on the ability to drive have been performed."
            ),
        }

        sec = TGASectionExtractor.extract_section_4_6(mock_raw)
        assert sec.is_present is True
        assert sec.section_number == SECTION_4_6_NUM
        assert sec.start_page == 8
        assert sec.end_page == 9
        assert sec.pages_str == "8–9"
        assert "Effects on fertility:" in sec.text_content
        assert "Use in pregnancy" in sec.text_content
        assert "Ofloxacin is excreted in human milk." in sec.text_content
        # Ensure 4.7 was strictly excluded
        assert "4.7" not in sec.text_content
        assert "ability to drive" not in sec.text_content

    def test_extract_section_4_6_missing(self):
        mock_missing = {
            "status": "not_found",
            "content": "",
        }
        sec = TGASectionExtractor.extract_section_4_6(mock_missing)
        assert sec.is_present is False
        assert sec.text_content == MISSING_SECTION_4_6_TEXT

        sec_none = TGASectionExtractor.extract_section_4_6(None)
        assert sec_none.is_present is False
        assert sec_none.text_content == MISSING_SECTION_4_6_TEXT

    def test_extract_section_4_8_success(self):
        mock_raw = {
            "status": "success",
            "start_page": 10,
            "end_page": 12,
            "content": (
                "4.8. ADVERSE EFFECTS (UNDESIRABLE EFFECTS)\n\n"
                "The most frequently reported adverse reaction was transient ocular burning.\n\n"
                "Table 1: Tabulated list of adverse reactions\n"
                "| System Organ Class | Frequency | Adverse Reaction |\n"
                "| --- | --- | --- |\n"
                "| Eye disorders | Common | Ocular discomfort |\n\n"
                "4.9 OVERDOSE\n"
                "In the event of an overdose, treatment should be symptomatic."
            ),
            "structured_content": [
                {
                    "type": "table",
                    "page": 11,
                    "caption": "Table 1: Tabulated list of adverse reactions",
                    "columns": ["System Organ Class", "Frequency", "Adverse Reaction"],
                    "rows": [
                        {"System Organ Class": "Eye disorders", "Frequency": "Common", "Adverse Reaction": "Ocular discomfort"}
                    ],
                    "raw_rows": [
                        ["System Organ Class", "Frequency", "Adverse Reaction"],
                        ["Eye disorders", "Common", "Ocular discomfort"]
                    ],
                }
            ],
        }

        sec = TGASectionExtractor.extract_section_4_8(mock_raw)
        assert sec.is_present is True
        assert sec.section_number == SECTION_4_8_NUM
        assert sec.start_page == 10
        assert sec.end_page == 12
        assert sec.pages_str == "10–12"
        assert "ocular burning" in sec.text_content
        assert len(sec.tables) == 1
        assert sec.tables[0].columns == ["System Organ Class", "Frequency", "Adverse Reaction"]
        # Ensure 4.9 was strictly excluded
        assert "4.9" not in sec.text_content
        assert "OVERDOSE" not in sec.text_content

    def test_extract_section_4_8_missing(self):
        mock_missing = {
            "status": "not_found",
            "content": "",
        }
        sec = TGASectionExtractor.extract_section_4_8(mock_missing)
        assert sec.is_present is False
        assert sec.text_content == MISSING_SECTION_4_8_TEXT

    @pytest.mark.asyncio
    async def test_pdf_handler_integration_with_sample_report(self):
        """Tests end-to-end integration of TGAPDFHandler with the existing sample PDF."""
        handler = TGAPDFHandler()
        sample_pdf = Path(__file__).resolve().parents[5] / "pdf_extractor" / "sample_reports" / "test8_tables.pdf"
        assert sample_pdf.exists(), f"Sample PDF not found at {sample_pdf}"

        # Run extraction using the existing PDF extractor
        res = await handler.extract_sections(sample_pdf, doc_name="test8_tables.pdf")
        assert "section_4_6" in res
        assert "section_4_8" in res

        # Process sections through TGASectionExtractor
        processed = TGASectionExtractor.process_sections(res)
        # Note: test8_tables.pdf has sections 16 and 16.1, so 4.6/4.8 will return standard NOT FOUND
        assert processed["section_4_6"].is_present is False
        assert processed["section_4_6"].text_content == MISSING_SECTION_4_6_TEXT
        assert processed["section_4_8"].is_present is False
        assert processed["section_4_8"].text_content == MISSING_SECTION_4_8_TEXT

    def test_subheading_and_paragraph_structuring(self):
        """Tests that blocks with subheadings, categories, and page-split sentences are cleanly structured."""
        class MockBlock:
            def __init__(self, text, block_type="paragraph", page=1):
                self.text = text
                self.block_type = block_type
                self.page = page

        class MockExtractionResult:
            def __init__(self, blocks, start_page=12, end_page=13):
                self.status = "success"
                self.start_page = start_page
                self.end_page = end_page
                self.blocks = blocks
                self.content = "\n".join(b.text for b in blocks)

        blocks = [
            MockBlock("[Page 12] 4.6 FERTILITY, PREGNANCY AND LACTATION", block_type="heading", page=12),
            MockBlock("Effects on Fertility", block_type="paragraph", page=12),
            MockBlock("Studies in adult rats dosed with apixaban showed no effect on fertility.", block_type="paragraph", page=12),
            MockBlock("Use in Pregnancy", block_type="paragraph", page=12),
            MockBlock("Category C", block_type="paragraph", page=12),
            MockBlock("There are limited data for the use of apixaban in pregnant women.", block_type="paragraph", page=12),
            MockBlock("Use in Lactation", block_type="paragraph", page=12),
            MockBlock("Apixaban may be concentrated in milk", block_type="paragraph", page=12),
            MockBlock("and may present a bleeding risk to newborns.", block_type="paragraph", page=13),
        ]

        mock_res = MockExtractionResult(blocks)
        sec = TGASectionExtractor.extract_section_4_6(mock_res)

        assert sec.is_present is True
        # Check subheadings are tagged
        assert "### Effects on Fertility" in sec.text_content
        assert "### Use in Pregnancy" in sec.text_content
        assert "### Category C" in sec.text_content
        assert "### Use in Lactation" in sec.text_content
        # Check cross-page sentence stitching
        assert "Apixaban may be concentrated in milk and may present a bleeding risk to newborns." in sec.text_content

        # Test HTML formatting
        from app.ui import _format_tga_prose_html
        html_out = _format_tga_prose_html(sec.text_content)
        assert '<h3 class="tga-section-header">4.6 FERTILITY, PREGNANCY AND LACTATION</h3>' in html_out
        assert '<h4 class="tga-subheading">Effects on Fertility</h4>' in html_out
        assert '<h4 class="tga-subheading">Use in Pregnancy</h4>' in html_out
        assert '<div class="tga-category-box"><span class="tga-category-badge">Category C</span></div>' in html_out
        assert '<h4 class="tga-subheading">Use in Lactation</h4>' in html_out
        assert '<p class="tga-text">Studies in adult rats dosed with apixaban showed no effect on fertility.</p>' in html_out
        assert '<p class="tga-text">Apixaban may be concentrated in milk and may present a bleeding risk to newborns.</p>' in html_out

