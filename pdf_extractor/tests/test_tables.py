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
        doc_name="test8_tables.pdf"
    )

    assert result.status == "success"
    assert result.validation.tables_included_count >= 1

    # Check that Table 1 content is present
    table_blocks = [b for b in result.blocks if b.block_type == BlockType.TABLE.value]
    assert len(table_blocks) >= 1

    table_text = "\n".join(b.text for b in table_blocks)
    assert "Headache" in table_text
    assert "Drug A" in table_text

    # Check that Table 2 from 16.2 is NOT included
    assert "ALT (U/L)" not in result.content
    assert "Serum Creatinine" not in result.content
