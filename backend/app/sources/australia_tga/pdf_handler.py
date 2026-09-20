"""
PDF Handler for Australia TGA.
Routes discovered Product Information PDFs to the EXISTING PDF extraction pipeline
(pdf_extractor subsystem) without creating duplicate PDF parsing, OCR, or table engines.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import io
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Dict, Optional, Union

import httpx

from app.sources.australia_tga.config import (
    DEFAULT_HEADERS,
    PDF_DOWNLOAD_TIMEOUT,
    PDF_EXTRACTOR_TIMEOUT,
    PDF_EXTRACTOR_URL,
    SECTION_4_6_NUM,
    SECTION_4_8_NUM,
)

logger = logging.getLogger(__name__)

# Ensure pdf_extractor is importable from project root
_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # webcrwler
_PDF_EXTRACTOR_DIR = _PROJECT_ROOT / "pdf_extractor"
if str(_PDF_EXTRACTOR_DIR) not in sys.path:
    sys.path.insert(0, str(_PDF_EXTRACTOR_DIR))


class TGAPDFHandler:
    """
    Interfaces with the project's existing PDF extraction engine.
    Hands off discovered TGA Product Information PDFs and retrieves structured results.
    """

    def __init__(
        self,
        extractor_url: str = PDF_EXTRACTOR_URL,
        timeout: float = PDF_DOWNLOAD_TIMEOUT,
        prefer_in_process: bool = True,
    ) -> None:
        self.extractor_url = os.environ.get("TGA_PDF_EXTRACTOR_URL", extractor_url)
        self.timeout = timeout
        self.prefer_in_process = prefer_in_process
        self._section_extractor = None

        # Local cache directory for downloaded PDFs
        self.cache_dir = Path(__file__).resolve().parents[3] / "data" / "pdf_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_in_process_extractor(self):
        """Lazily imports and instantiates the existing SectionExtractor."""
        if self._section_extractor is None:
            try:
                from backend.extraction.section_extractor import SectionExtractor
                self._section_extractor = SectionExtractor()
                logger.info("Successfully initialized in-process existing SectionExtractor")
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
            logger.info("Using cached PDF for %s (%d bytes)", pdf_url_or_path, cached_file.stat().st_size)
            try:
                return cached_file.read_bytes()
            except Exception as exc:
                logger.warning("Failed to read cached PDF %s: %s", cached_file, exc)

        # Remote URL with retry
        req_headers = dict(DEFAULT_HEADERS)
        req_headers["Connection"] = "close"

        for attempt in range(1, 2):
            try:
                async with httpx.AsyncClient(
                    headers=req_headers,
                    timeout=httpx.Timeout(self.timeout, connect=6.0, read=self.timeout),
                    follow_redirects=True,
                ) as client:
                    # Special handling for Australian TGA eBS document repository
                    if "ebs.tga.gov.au" in pdf_url_or_path:
                        # 1. Fetch the initial landing or license page
                        init_resp = await client.get(pdf_url_or_path)
                        if init_resp.content.startswith(b"%PDF"):
                            cached_file.write_bytes(init_resp.content)
                            return init_resp.content

                        # If HTML license agreement, extract remoteaddr and accept
                        match = re.search(r'id=["\']remoteaddr["\'][^>]*value=["\']([^"\']+)["\']', init_resp.text, re.I)
                        if not match:
                            match = re.search(r'value=["\']([^"\']+)["\'][^>]*id=["\']remoteaddr["\']', init_resp.text, re.I)
                        if not match:
                            match = re.search(r'name=["\']Remote_Addr["\'][^>]*value=["\']([^"\']+)["\']', init_resp.text, re.I)
                        if not match:
                            match = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']Remote_Addr["\']', init_resp.text, re.I)
                        if not match:
                            match = re.search(r'value=["\'](\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})["\']', init_resp.text)

                        remote_ip = match.group(1) if match else "172.31.0.101"
                        clean_ip = re.sub(r"\D", "", remote_ip)
                        utc_date = datetime.utcnow().strftime("%Y%m%d")
                        cookie_val = f"{utc_date}{clean_ip}"

                        sep = "&" if "?" in pdf_url_or_path else "?"
                        pdf_download_url = f"{pdf_url_or_path}{sep}d={cookie_val}"
                        step_headers = dict(req_headers)
                        step_headers["Cookie"] = f"PICMIIAccept={cookie_val}"

                        pdf_resp = await client.get(pdf_download_url, headers=step_headers)
                        if pdf_resp.status_code == 200 and pdf_resp.content.startswith(b"%PDF"):
                            logger.info("Successfully downloaded eBS PDF from %s (%d bytes)", pdf_download_url, len(pdf_resp.content))
                            cached_file.write_bytes(pdf_resp.content)
                            return pdf_resp.content
                        elif pdf_resp.content.startswith(b"%PDF"):
                            cached_file.write_bytes(pdf_resp.content)
                            return pdf_resp.content
                        else:
                            logger.warning("eBS download returned non-PDF (%d bytes, HTTP %d)", len(pdf_resp.content), pdf_resp.status_code)
                            return None

                    resp = await client.get(pdf_url_or_path)
                    if resp.status_code == 200 and resp.content:
                        if resp.content.startswith(b"%PDF") or "pdf" in resp.headers.get("content-type", "").lower():
                            logger.info("Successfully downloaded PDF from %s (%d bytes)", pdf_url_or_path, len(resp.content))
                            cached_file.write_bytes(resp.content)
                            return resp.content
                        logger.warning("Downloaded content from %s is not a PDF (length: %d)", pdf_url_or_path, len(resp.content))
                        return None
                    logger.warning("Failed to download PDF from %s (HTTP %d)", pdf_url_or_path, resp.status_code)
                    return None
            except Exception as exc:
                logger.warning("Network exception downloading PDF %s: %s (%s)", pdf_url_or_path, type(exc).__name__, exc)
                return None
        return None

    async def extract_sections(
        self,
        pdf_source: Union[str, Path, bytes],
        doc_name: str = "product_information.pdf",
    ) -> Dict[str, Any]:
        """
        Extracts Section 4.6 and Section 4.8 from the provided PDF using the existing PDF extractor.

        Returns a dictionary:
        {
            "section_4_6": ExtractionResult or dict,
            "section_4_8": ExtractionResult or dict,
        }
        """
        # Resolve PDF to a local temporary file or path for reliable table/text parsing
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
                logger.error("Could not obtain PDF bytes for extraction from %s", pdf_source)
                return {"section_4_6": None, "section_4_8": None, "error": "PDF download failed"}
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                tf.write(pdf_bytes)
                temp_file_path = tf.name
                target_path = Path(temp_file_path)

        if not target_path or not target_path.exists():
            return {"section_4_6": None, "section_4_8": None, "error": "Invalid PDF target path"}

        try:
            # 1. Attempt in-process extraction via existing SectionExtractor
            extractor = self._get_in_process_extractor()
            if extractor:
                logger.info("Executing extraction for Section 4.6 on %s", doc_name)
                res_4_6 = extractor.extract(
                    file_path_or_bytes=target_path,
                    main_section=SECTION_4_6_NUM,
                    target_subsection=None,
                    doc_name=doc_name,
                    include_tables=True,
                    save_to_db=False,
                )

                logger.info("Executing extraction for Section 4.8 on %s", doc_name)
                res_4_8 = extractor.extract(
                    file_path_or_bytes=target_path,
                    main_section=SECTION_4_8_NUM,
                    target_subsection=None,
                    doc_name=doc_name,
                    include_tables=True,
                    save_to_db=False,
                )

                return {
                    "section_4_6": res_4_6,
                    "section_4_8": res_4_8,
                }

            # 2. Fallback to HTTP microservice if in-process not available
            return await self._extract_via_http(target_path, doc_name)

        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception:
                    pass

    async def _extract_via_http(self, file_path: Path, doc_name: str) -> Dict[str, Any]:
        """Routes PDF to the running PDF Extractor FastAPI microservice."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res_4_6 = await client.post(
                    f"{self.extractor_url}/api/extract",
                    json={
                        "file_path": str(file_path),
                        "filename": doc_name,
                        "main_section": SECTION_4_6_NUM,
                        "include_tables": True,
                    },
                )
                res_4_8 = await client.post(
                    f"{self.extractor_url}/api/extract",
                    json={
                        "file_path": str(file_path),
                        "filename": doc_name,
                        "main_section": SECTION_4_8_NUM,
                        "include_tables": True,
                    },
                )
                return {
                    "section_4_6": res_4_6.json() if res_4_6.status_code == 200 else None,
                    "section_4_8": res_4_8.json() if res_4_8.status_code == 200 else None,
                }
        except Exception as exc:
            logger.error("HTTP call to PDF Extractor service failed: %s", exc)
            return {"section_4_6": None, "section_4_8": None, "error": str(exc)}
