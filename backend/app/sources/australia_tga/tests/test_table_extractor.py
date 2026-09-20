"""
Unit tests for Section 4.8 table extraction (table_extractor.py).
"""
import pytest

from app.sources.australia_tga.table_extractor import TGATableExtractor
from app.ui import _format_tga_prose_html


class TestTGATableExtractor:
    """Tests for TGATableExtractor."""

    def test_extract_single_page_table(self):
        mock_result = {
            "structured_content": [
                {
                    "type": "table",
                    "page": 11,
                    "caption": "Table 1: Adverse Drug Reactions",
                    "columns": ["System Organ Class", "Frequency", "Adverse Reaction"],
                    "rows": [
                        {"System Organ Class": "Eye disorders", "Frequency": "Common", "Adverse Reaction": "Ocular burning"},
                        {"System Organ Class": "Immune disorders", "Frequency": "Rare", "Adverse Reaction": "Anaphylaxis*"},
                    ],
                    "raw_rows": [
                        ["System Organ Class", "Frequency", "Adverse Reaction"],
                        ["Eye disorders", "Common", "Ocular burning"],
                        ["Immune disorders", "Rare", "Anaphylaxis*"],
                        ["* Post-marketing report", "", ""],
                    ],
                }
            ]
        }

        tables = TGATableExtractor.extract_and_format_tables(mock_result)
        assert len(tables) == 1
        t = tables[0]
        assert t.page == 11
        assert t.columns == ["System Organ Class", "Frequency", "Adverse Reaction"]
        assert len(t.rows) == 2
        assert "* Post-marketing report" in t.footnotes
        assert "| System Organ Class | Frequency | Adverse Reaction |" in t.markdown
        assert "| Eye disorders | Common | Ocular burning |" in t.markdown

    def test_merge_continuation_tables_across_pages(self):
        # Scenario from requirements:
        # Page 20 -> Page 21
        # Should combine the complete table while preserving page references
        mock_result = {
            "structured_content": [
                {
                    "type": "table",
                    "page": 20,
                    "caption": "Table 3: Adverse Reactions",
                    "columns": ["SOC", "Frequency", "Reaction"],
                    "rows": [
                        {"SOC": "Gastrointestinal", "Frequency": "Very common", "Reaction": "Nausea"},
                    ],
                    "raw_rows": [
                        ["SOC", "Frequency", "Reaction"],
                        ["Gastrointestinal", "Very common", "Nausea"],
                    ],
                },
                {
                    "type": "table",
                    "page": 21,
                    "caption": "Table 3: Adverse Reactions (continued)",
                    "columns": ["SOC", "Frequency", "Reaction"],
                    "rows": [
                        {"SOC": "Gastrointestinal", "Frequency": "Common", "Reaction": "Vomiting"},
                        {"SOC": "Nervous system", "Frequency": "Common", "Reaction": "Headache"},
                    ],
                    "raw_rows": [
                        ["SOC", "Frequency", "Reaction"],
                        ["Gastrointestinal", "Common", "Vomiting"],
                        ["Nervous system", "Common", "Headache"],
                    ],
                },
            ]
        }

        tables = TGATableExtractor.extract_and_format_tables(mock_result)
        assert len(tables) == 1
        merged_table = tables[0]
        assert merged_table.page == 20
        assert "continued on Page 21" in merged_table.caption
        assert len(merged_table.rows) == 3
        assert "| Nervous system | Common | Headache |" in merged_table.markdown

    def test_format_markdown_table(self):
        cols = ["Col A", "Col B"]
        rows = [["Val 1", "Val 2"], ["Val 3", "Val 4"]]
        md = TGATableExtractor.format_markdown_table(cols, rows)
        expected = (
            "| Col A | Col B |\n"
            "| --- | --- |\n"
            "| Val 1 | Val 2 |\n"
            "| Val 3 | Val 4 |"
        )
        assert md == expected

    def test_clean_and_prune_ghost_columns_and_multiline_headers(self):
        # Simulates Eliquis Page 15 where pdfplumber has 5 columns, but cols 1 and 3 are empty ghost columns,
        # and rows 0, 1, 2 are multi-line headers
        raw_cols = ["SOC / Preferred Term", "Column_2", "Apixaban", "Column_4", "Enoxaparin"]
        raw_rows = [
            ["SOC / Preferred Term", "", "Apixaban", "", "Enoxaparin"],
            ["", "", "2.5 mg po twice daily", "", "40 mg sc once daily"],
            ["", "", "n (%)", "", "n (%)"],
            ["Number treated", "", "4174 (100)", "", "4167 (100)"],
            ["Gastrointestinal disorders", "", "", "", ""],
            ["Nausea", "", "587 (14.1)", "", "649 (15.6)"],
        ]

        cols, data_rows = TGATableExtractor.clean_and_prune_table(raw_cols, raw_rows)
        assert cols == [
            "SOC / Preferred Term",
            "Apixaban 2.5 mg po twice daily n (%)",
            "Enoxaparin 40 mg sc once daily n (%)",
        ]
        assert len(data_rows) == 3
        assert data_rows[0] == ["Number treated", "4174 (100)", "4167 (100)"]
        assert data_rows[1] == ["Gastrointestinal disorders", "", ""]
        assert data_rows[2] == ["Nausea", "587 (14.1)", "649 (15.6)"]

    def test_merge_continuation_table_with_soc_row_header(self):
        # Simulates Apixaban Viatris Table 1 across Page 13 & 14
        mock_result = {
            "structured_content": [
                {
                    "type": "table",
                    "page": 13,
                    "caption": "Table 1: Common adverse events",
                    "columns": ["SOC / Preferred Term", "Apixaban 2.5 mg", "Enoxaparin 40 mg"],
                    "rows": [],
                    "raw_rows": [
                        ["SOC / Preferred Term", "Apixaban 2.5 mg", "Enoxaparin 40 mg"],
                        ["Number treated", "4174 (100)", "4167 (100)"],
                        ["Gastrointestinal disorders", "", ""],
                        ["Nausea", "587 (14.1)", "649 (15.6)"],
                    ],
                },
                {
                    "type": "table",
                    "page": 14,
                    "caption": "Table 1: Common adverse events (continued)",
                    # The extractor saw the first SOC on Page 14 as the header:
                    "columns": ["Injury, poisoning and procedural complications", "Column_2", "Column_3"],
                    "rows": [],
                    "raw_rows": [
                        ["Injury, poisoning and procedural complications", "", ""],
                        ["Procedural pain", "431 (10.3)", "433 (10.4)"],
                    ],
                },
            ]
        }

        tables = TGATableExtractor.extract_and_format_tables(mock_result)
        assert len(tables) == 1
        t = tables[0]
        assert t.page == 13
        assert t.columns == ["SOC / Preferred Term", "Apixaban 2.5 mg", "Enoxaparin 40 mg"]
        assert "| **Gastrointestinal disorders** |" in t.markdown
        assert "| **Injury, poisoning and procedural complications** |" in t.markdown
        assert "| Procedural pain | 431 (10.3) | 433 (10.4) |" in t.markdown

    def test_integrate_merged_tables_into_text(self):
        raw_text = (
            "Introductory text.\n\n"
            "Table 1: Adverse Reactions\n\n"
            "[Page 13 Table]\n"
            "| Col A | Col B |\n"
            "| --- | --- |\n"
            "| Val 1 | 10% |\n\n"
            "[Page 14 Table]\n"
            "| Col A | Col B |\n"
            "| --- | --- |\n"
            "| Val 2 | 20% |\n\n"
            "Subsequent text after table."
        )

        table = TGATableExtractor.extract_and_format_tables({
            "structured_content": [{
                "type": "table",
                "page": 13,
                "caption": "Table 1",
                "columns": ["Col A", "Col B"],
                "rows": [],
                "raw_rows": [
                    ["Col A", "Col B"],
                    ["Val 1", "10%"],
                    ["Val 2", "20%"],
                ],
            }]
        })[0]

        integrated = TGATableExtractor.integrate_merged_tables_into_text(raw_text, [table])
        assert "[Page 13 Table]" not in integrated
        assert "[Page 14 Table]" not in integrated
        assert "Introductory text." in integrated
        assert "Subsequent text after table." in integrated
        assert "| Val 1 | 10% |" in integrated
        assert "| Val 2 | 20% |" in integrated

    def test_render_tga_prose_html_with_table(self):
        sample_text = (
            "4.8 ADVERSE EFFECTS\n\n"
            "Clinical trial text.\n\n"
            "Table 1: Common Adverse Events\n\n"
            "| System Organ Classification / Preferred Term | Drug A n (%) | Drug B n (%) |\n"
            "| --- | --- | --- |\n"
            "| Number treated | 100 (100) | 100 (100) |\n"
            "| **Gastrointestinal disorders** | | |\n"
            "| Nausea | 15 (15.0) | 12 (12.0) |\n\n"
            "Post-marketing text."
        )

        html_out = _format_tga_prose_html(sample_text)
        assert '<table class="tga-table">' in html_out
        assert '<th class="text-left">System Organ Classification / Preferred Term</th>' in html_out
        assert '<tr class="tga-subtotal-row">' in html_out
        assert '<strong>Number treated</strong>' in html_out
        assert '<tr class="tga-soc-row"><td colspan="3"><strong>Gastrointestinal disorders</strong></td></tr>' in html_out
        assert '<tr class="tga-data-row">' in html_out
        assert '<td class="tga-term-cell">Nausea</td>' in html_out
        assert '<td class="tga-freq-cell">15 (15.0)</td>' in html_out
        assert '<h4 class="tga-table-title">Table 1: Common Adverse Events</h4>' in html_out
        assert '<p class="tga-text">Post-marketing text.</p>' in html_out


