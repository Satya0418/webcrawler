import pytest
from pathlib import Path
from backend.extraction.section_extractor import SectionExtractor
from backend.models.schemas import BlockType

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_table_extraction_and_exclusion():
    pdf_path = FIXTURES_DIR / "test8_tables.pdf"
    extractor = SectionExtractor()
    result = extractor.extract(
        file_path_or_bytes=pdf_path,
        main_section="16",
        target_subsection="16.1",
        doc_name="test8_tables.pdf",
        table_mode="add"
    )

    assert result.status == "success"
    assert result.validation.tables_included_count >= 1
    assert result.tables_detected >= 1
    assert result.tables_neglected == 0

    # Check that Table 1 content is present
    table_blocks = [b for b in result.blocks if b.block_type == BlockType.TABLE.value]
    assert len(table_blocks) >= 1

    table_text = "\n".join(b.text for b in table_blocks)
    assert "Headache" in table_text
    assert "Drug A" in table_text

    # Check that Table 2 from 16.2 is NOT included
    assert "ALT (U/L)" not in result.content
    assert "Serum Creatinine" not in result.content


def test_neglect_table_option_extracts_only_paragraphs():
    pdf_path = FIXTURES_DIR / "test8_tables.pdf"
    extractor = SectionExtractor()
    result = extractor.extract(
        file_path_or_bytes=pdf_path,
        main_section="16",
        target_subsection="16.1",
        table_mode="neglect",
        doc_name="test8_tables.pdf"
    )

    assert result.status == "success"
    assert result.table_mode == "neglect"
    assert result.tables_detected == 1
    assert result.tables_neglected == 1
    assert result.validation.tables_included_count == 0

    # Section 16 and 16.1 text paragraphs MUST be extracted
    assert "Safety information text with clinical event tables below." in result.content
    assert "Table 1 summarizes all treatment-emergent adverse reactions." in result.content

    # No structured table items
    assert not any(it.type == "table" for it in result.structured_content)
    assert not any(b.block_type == BlockType.TABLE.value for b in result.blocks)

    # CRITICAL: Table cell content must NOT leak into paragraphs or content!
    assert "Headache" not in result.content
    assert "Drug A" not in result.content
    assert "Placebo" not in result.content
    assert "Nausea" not in result.content
    assert "Dizziness" not in result.content
    assert "12 (12%)" not in result.content
    for item in result.structured_content:
        item_text = item.text or item.title or ""
        assert "Headache" not in item_text
        assert "Drug A" not in item_text


def test_natural_query_neglect_table():
    pdf_path = FIXTURES_DIR / "test8_tables.pdf"
    extractor = SectionExtractor()
    result = extractor.extract(
        file_path_or_bytes=pdf_path,
        natural_query="Extract Section 16 to 16.1 text only neglect table"
    )

    assert result.status == "success"
    assert result.table_mode == "neglect"
    assert result.tables_detected == 1
    assert result.tables_neglected == 1
    assert result.validation.tables_included_count == 0
    assert "Safety information text with clinical event tables below." in result.content
    assert "Table 1 summarizes all treatment-emergent adverse reactions." in result.content
    assert "Headache" not in result.content


def test_section_table_mode_override():
    pdf_path = FIXTURES_DIR / "test8_tables.pdf"
    extractor = SectionExtractor()
    result = extractor.extract(
        file_path_or_bytes=pdf_path,
        main_section="16",
        target_subsection="16.1",
        table_mode="add",
        section_table_mode={"16.1": "neglect"}
    )

    assert result.status == "success"
    assert result.tables_detected == 1
    assert result.tables_neglected == 1
    assert result.validation.tables_included_count == 0
    assert "Headache" not in result.content

