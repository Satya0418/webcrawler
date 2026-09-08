import os
import fitz  # PyMuPDF
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path


class PDFReader:
    """Handles PDF file opening, validation, and metadata extraction."""

    def __init__(self, file_path_or_bytes: Any):
        self.source = file_path_or_bytes
        self.doc: Optional[fitz.Document] = None
        self.metadata: Dict[str, Any] = {}
        self.page_count: int = 0
        self.toc_bookmarks: List[Tuple[int, str, int]] = []
        self._open()

    def _open(self) -> None:
        try:
            if isinstance(self.source, (str, Path)):
                path = Path(self.source)
                if not path.exists():
                    raise FileNotFoundError(f"PDF file not found: {self.source}")
                self.doc = fitz.open(str(path))
            elif isinstance(self.source, bytes):
                self.doc = fitz.open(stream=self.source, filetype="pdf")
            else:
                raise ValueError("Invalid PDF source. Must be a file path or bytes.")

            if self.doc.is_encrypted:
                raise PermissionError("PDF is password protected and cannot be read without password.")

            self.page_count = len(self.doc)
            if self.page_count == 0:
                raise ValueError("PDF is empty (contains 0 pages).")

            self.metadata = self.doc.metadata or {}
            # fitz.get_toc() returns [[level, title, page_num, ...], ...]
            raw_toc = self.doc.get_toc(simple=True) or []
            self.toc_bookmarks = [(item[0], item[1].strip(), item[2]) for item in raw_toc if len(item) >= 3]

        except Exception as e:
            if self.doc:
                self.doc.close()
            raise e

    def is_scanned(self, char_threshold_per_page: int = 40) -> Tuple[bool, float]:
        """
        Determines whether the PDF is predominantly scanned/image-based.
        Returns (is_scanned, avg_chars_per_page).
        """
        if not self.doc or self.page_count == 0:
            return False, 0.0

        sample_pages = min(self.page_count, 10)
        total_chars = 0
        for i in range(sample_pages):
            page = self.doc[i]
            text = page.get_text("text").strip()
            total_chars += len(text)

        avg_chars = total_chars / sample_pages
        is_scanned_pdf = avg_chars < char_threshold_per_page
        return is_scanned_pdf, avg_chars

    def close(self) -> None:
        if self.doc and not self.doc.is_closed:
            self.doc.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
