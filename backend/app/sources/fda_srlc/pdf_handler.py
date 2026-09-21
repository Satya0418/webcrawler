"""
PDF Handler for FDA SrLC.
Connects discovered FDA Approved Drug Label PDFs to the EXISTING PDF extraction pipeline
without creating duplicate parsers, OCR, or table engines.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union

import httpx

from app.sources.fda_srlc.config import (
    CONNECT_TIMEOUT,
    DEFAULT_HEADERS,
    DEFAULT_TIMEOUT,
    PDF_CACHE_DIR,
    SECTION_ADVERSE_REACTIONS,
    SECTION_USE_IN_SPECIFIC_POPULATIONS,
    SECTION_WARNINGS_PRECAUTIONS,
)

logger = logging.getLogger(__name__)

# Ensure pdf_extractor is importable from project root without modifying it
_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # webcrwler
_PDF_EXTRACTOR_DIR = _PROJECT_ROOT / "pdf_extractor"
if str(_PDF_EXTRACTOR_DIR) not in sys.path:
    sys.path.insert(0, str(_PDF_EXTRACTOR_DIR))


class FDASrLCPDFHandler:
    """Interfaces with the project's existing PDF extraction engine for FDA labels."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self.cache_dir = PDF_CACHE_DIR
        self._section_extractor = None

    def _get_in_process_extractor(self):
        """Lazily imports and instantiates the existing SectionExtractor."""
        if self._section_extractor is None:
            try:
                from backend.extraction.section_extractor import SectionExtractor
                self._section_extractor = SectionExtractor()
                logger.info("Successfully initialized existing SectionExtractor for FDA labels")
            except Exception as exc:
                logger.warning("Could not import in-process SectionExtractor: %s", exc)
        return self._section_extractor

    async def fetch_pdf_bytes(self, pdf_url_or_path: str) -> Optional[bytes]:
        """
        Retrieves PDF content as bytes from a local file path or remote URL.
        Caches remote PDF downloads on local disk so subsequent reads are instantaneous.
        """
        if not pdf_url_or_path:
            return None

        # Check local file
        local_p = Path(pdf_url_or_path)
        if local_p.exists() and local_p.is_file():
            try:
                return local_p.read_bytes()
            except Exception as exc:
                logger.error("Error reading local PDF file %s: %s", pdf_url_or_path, exc)
                return None

        # Check local disk cache for remote URL
        url_hash = hashlib.md5(pdf_url_or_path.encode("utf-8")).hexdigest()
        cached_file = self.cache_dir / f"{url_hash}.pdf"
        if cached_file.exists() and cached_file.stat().st_size > 1000:
            logger.info("Using cached FDA label PDF for %s (%d bytes)", pdf_url_or_path, cached_file.stat().st_size)
            try:
                return cached_file.read_bytes()
            except Exception as exc:
                logger.warning("Failed to read cached FDA PDF %s: %s", cached_file, exc)

        # Download remote PDF
        req_headers = dict(DEFAULT_HEADERS)
        req_headers["Connection"] = "close"

        try:
            async with httpx.AsyncClient(
                headers=req_headers,
                timeout=httpx.Timeout(self.timeout, connect=CONNECT_TIMEOUT, read=self.timeout),
                follow_redirects=True,
            ) as client:
                resp = await client.get(pdf_url_or_path)
                if resp.status_code == 200 and resp.content:
                    if resp.content.startswith(b"%PDF") or "pdf" in resp.headers.get("content-type", "").lower():
                        logger.info("Successfully downloaded FDA PDF from %s (%d bytes)", pdf_url_or_path, len(resp.content))
                        cached_file.write_bytes(resp.content)
                        return resp.content
                    logger.warning("Downloaded content from %s is not a PDF", pdf_url_or_path)
                    return None
                logger.warning("Failed to download FDA PDF from %s (HTTP %d)", pdf_url_or_path, resp.status_code)
                return None
        except Exception as exc:
            logger.warning("Network exception downloading FDA PDF %s: %s", pdf_url_or_path, exc)
            return None

    async def extract_fda_sections_from_pdf(
        self,
        pdf_source: Union[str, Path, bytes],
        doc_name: str = "fda_label.pdf",
    ) -> Dict[str, Any]:
        """
        Extracts Section 6 (Adverse Reactions), Section 5 (Warnings and Precautions),
        and Section 8 (Use in Specific Populations) using the existing PDF extractor.
        """
        logger.info("FDA_SRLC_DOCUMENT_EXTRACTION_STARTED: Extracting sections from %s", doc_name)

        temp_file_path = None
        target_path = None

        if isinstance(pdf_source, (str, Path)) and Path(pdf_source).exists():
            target_path = Path(pdf_source)
        elif isinstance(pdf_source, bytes):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                tf.write(pdf_source)
                temp_file_path = tf.name
                target_path = Path(temp_file_path)
        elif isinstance(pdf_source, str) and (pdf_source.startswith("http://") or pdf_source.startswith("https://")):
            pdf_bytes = await self.fetch_pdf_bytes(pdf_source)
            if not pdf_bytes:
                return {"error": "PDF download failed"}
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                tf.write(pdf_bytes)
                temp_file_path = tf.name
                target_path = Path(temp_file_path)

        if not target_path or not target_path.exists():
            return {"error": "Invalid PDF target path"}

        results: Dict[str, Any] = {
            "section_5": None,
            "section_6": None,
            "section_8": None,
        }

        try:
            extractor = self._get_in_process_extractor()
            if extractor:
                # Extract Section 6 (Adverse Reactions)
                try:
                    res_6 = extractor.extract(
                        file_path_or_bytes=target_path,
                        main_section=SECTION_ADVERSE_REACTIONS,
                        target_subsection=None,
                        doc_name=doc_name,
                        include_tables=True,
                        save_to_db=False,
                    )
                    if res_6 and getattr(res_6, "status", None) == "success":
                        results["section_6"] = {
                            "content": res_6.content,
                            "start_page": res_6.start_page,
                            "end_page": res_6.end_page,
                            "tables": getattr(res_6, "tables_detected", []),
                        }
                except Exception as e:
                    logger.warning("Error extracting Section 6 from PDF %s: %s", doc_name, e)

                # Extract Section 5 (Warnings and Precautions)
                try:
                    res_5 = extractor.extract(
                        file_path_or_bytes=target_path,
                        main_section=SECTION_WARNINGS_PRECAUTIONS,
                        target_subsection=None,
                        doc_name=doc_name,
                        include_tables=True,
                        save_to_db=False,
                    )
                    if res_5 and getattr(res_5, "status", None) == "success":
                        results["section_5"] = {
                            "content": res_5.content,
                            "start_page": res_5.start_page,
                            "end_page": res_5.end_page,
                            "tables": getattr(res_5, "tables_detected", []),
                        }
                except Exception as e:
                    logger.warning("Error extracting Section 5 from PDF %s: %s", doc_name, e)

                # Extract Section 8 (Use in Specific Populations)
                try:
                    res_8 = extractor.extract(
                        file_path_or_bytes=target_path,
                        main_section=SECTION_USE_IN_SPECIFIC_POPULATIONS,
                        target_subsection=None,
                        doc_name=doc_name,
                        include_tables=True,
                        save_to_db=False,
                    )
                    if res_8 and getattr(res_8, "status", None) == "success":
                        results["section_8"] = {
                            "content": res_8.content,
                            "start_page": res_8.start_page,
                            "end_page": res_8.end_page,
                            "tables": getattr(res_8, "tables_detected", []),
                        }
                except Exception as e:
                    logger.warning("Error extracting Section 8 from PDF %s: %s", doc_name, e)

            logger.info("FDA_SRLC_DOCUMENT_EXTRACTION_COMPLETED: Extraction finished for %s", doc_name)
            return results

        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass
