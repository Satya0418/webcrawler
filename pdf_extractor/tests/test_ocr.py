import pytest
from pathlib import Path
from backend.pdf.reader import PDFReader
from backend.pdf.ocr import OCRProcessor

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_scanned_pdf_detection():
    # test5_scanned_mock has 0 font characters
    pdf_path = FIXTURES_DIR / "test5_scanned_mock.pdf"
    with PDFReader(pdf_path) as reader:
        is_scanned, avg_chars = reader.is_scanned(char_threshold_per_page=40)
        assert is_scanned is True
        assert avg_chars < 40.0


def test_normal_pdf_not_scanned():
    pdf_path = FIXTURES_DIR / "test1_basic.pdf"
    with PDFReader(pdf_path) as reader:
        is_scanned, avg_chars = reader.is_scanned(char_threshold_per_page=40)
        assert is_scanned is False
        assert avg_chars > 40.0


def test_ocr_processor_fallback_handling():
    ocr = OCRProcessor()
    # Whether or not tesseract binary is installed, engine check is safe and non-throwing
    avail = ocr.is_engine_available()
    assert isinstance(avail, bool)
