"""
Unit tests for latest Product Information version selector (version_selector.py & date_parser.py).
"""
from datetime import datetime
import pytest

from app.sources.australia_tga.date_parser import TGADateParser
from app.sources.australia_tga.models import TGAPIDocument
from app.sources.australia_tga.version_selector import TGAVersionSelector


class TestVersionSelectorAndDates:
    """Tests for TGAVersionSelector and TGADateParser."""

    def test_date_parser_formats(self):
        d1 = TGADateParser.parse_date("18 February 2026")
        assert d1 == datetime(2026, 2, 18)

        d2 = TGADateParser.parse_date("2024-03-10")
        assert d2 == datetime(2024, 3, 10)

        d3 = TGADateParser.parse_date("15/02/2024")
        assert d3 == datetime(2024, 2, 15)

        d4 = TGADateParser.parse_date("Invalid date text")
        assert d4 is None

    def test_amendment_date_extraction(self):
        text = "TGA Product Information. Date of most recent amendment: 18 February 2026. Approved by Delegate."
        dt = TGADateParser.extract_amendment_date(text)
        assert dt == datetime(2026, 2, 18)

        text2 = "Date of revision of the text: 2025-07-12."
        dt2 = TGADateParser.extract_amendment_date(text2)
        assert dt2 == datetime(2025, 7, 12)

    def test_parse_version_strings(self):
        v_str, v_num = TGADateParser.parse_version("Product Information Version 4.2")
        assert v_str == "Version 4.2"
        assert v_num == 4.2

        v_str2, v_num2 = TGADateParser.parse_version("Rev 3")
        assert v_str2 == "Version 3"
        assert v_num2 == 3.0

        v_str3, v_num3 = TGADateParser.parse_version("v1.0")
        assert v_str3 == "Version 1.0"
        assert v_num3 == 1.0

    def test_select_latest_multiple_dates(self):
        # Scenario from requirements:
        # PDF A -> 2024-03-10
        # PDF B -> 2025-07-12
        # PDF C -> 2026-02-18
        # Should select PDF C regardless of order!
        doc_a = TGAPIDocument(
            title="PI Version A",
            pdf_url="https://example.com/pi_a.pdf",
            revision_date=datetime(2024, 3, 10),
            document_date=datetime(2024, 3, 10),
            version_number=1.0,
        )
        doc_b = TGAPIDocument(
            title="PI Version B",
            pdf_url="https://example.com/pi_b.pdf",
            revision_date=datetime(2025, 7, 12),
            document_date=datetime(2025, 7, 12),
            version_number=2.0,
        )
        doc_c = TGAPIDocument(
            title="PI Version C",
            pdf_url="https://example.com/pi_c.pdf",
            revision_date=datetime(2026, 2, 18),
            document_date=datetime(2026, 2, 18),
            version_number=3.0,
        )

        # Shuffle order to test that search order or list order is ignored
        docs_list = [doc_b, doc_a, doc_c]
        selected = TGAVersionSelector.select_latest(docs_list)
        assert selected == doc_c
        assert selected.pdf_url == "https://example.com/pi_c.pdf"

        # Reversed order
        docs_list_rev = [doc_c, doc_b, doc_a]
        selected_rev = TGAVersionSelector.select_latest(docs_list_rev)
        assert selected_rev == doc_c

    def test_select_latest_same_date_higher_version(self):
        doc_1 = TGAPIDocument(
            title="PI v1",
            pdf_url="https://example.com/pi_v1.pdf",
            document_date=datetime(2024, 1, 1),
            version_number=1.0,
        )
        doc_2 = TGAPIDocument(
            title="PI v2",
            pdf_url="https://example.com/pi_v2.pdf",
            document_date=datetime(2024, 1, 1),
            version_number=2.0,
        )
        selected = TGAVersionSelector.select_latest([doc_1, doc_2])
        assert selected == doc_2
        assert selected.pdf_url == "https://example.com/pi_v2.pdf"

    def test_select_latest_empty_or_single(self):
        assert TGAVersionSelector.select_latest([]) is None

        single = TGAPIDocument(
            title="Single PI",
            pdf_url="https://example.com/pi.pdf",
        )
        assert TGAVersionSelector.select_latest([single]) == single
