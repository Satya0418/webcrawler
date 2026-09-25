import asyncio
import datetime
import hashlib
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

import fitz  # PyMuPDF

from backend.config import (
    WATCH_DIR,
    SCAN_INTERVAL_MINUTES,
    SCAN_ON_STARTUP,
    DEFAULT_TARGET_SECTION,
)
from backend.database.db import get_db_session
from backend.database.models import ProductSectionRecord, ScannerLogRecord
from backend.extraction.section_extractor import SectionExtractor
from backend.services.export_service import ExportService

logger = logging.getLogger("pdf_extractor.scanner")


def normalize_product_name(name: str) -> str:
    """Creates a normalized alphanumeric string for flexible, case-insensitive querying."""
    if not name:
        return ""
    # Strip special characters and normalize whitespace
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", name).lower()
    return " ".join(cleaned.split())


def extract_product_name_from_file(file_path: Path) -> str:
    """
    Intelligently determines the product/medicine name:
    1. First analyzes the PDF first page title/header using PyMuPDF font/layout heuristics.
    2. Falls back to clean regex-based parsing of the filename.
    """
    # Heuristic 1: Extract from first page of PDF if possible
    try:
        doc = fitz.open(file_path)
        if len(doc) > 0:
            first_page = doc[0]
            blocks = first_page.get_text("blocks")
            for b in blocks[:5]:
                text = b[4].strip()
                if not text or len(text) < 3:
                    continue
                first_line = text.split("\n")[0].strip()
                if any(k in first_line.upper() for k in [
                    "HIGHLIGHTS OF PRESCRIBING",
                    "PACKAGE INSERT",
                    "PRODUCT INFORMATION",
                    "CONSUMER MEDICINE",
                    "TABLE OF CONTENTS",
                    "NDA ",
                    "BLA ",
                ]):
                    continue
                brand_match = re.match(r"^([A-Z0-9\s\-\']{3,40})(?:\s*\(|$)", first_line)
                if brand_match:
                    candidate = brand_match.group(1).strip()
                    if len(candidate) >= 3 and not candidate.isdigit():
                        doc.close()
                        return candidate.title()
        doc.close()
    except Exception as exc:
        logger.debug("First page inspection skipped for %s: %s", file_path.name, exc)

    # Heuristic 2: Clean filename
    stem = file_path.stem
    # Iteratively strip common trailing suffixes (dosages, labels, pi, etc.)
    for _ in range(3):
        stem = re.sub(r"(?i)[_\-]?(pi|cmi|label|lbl|monograph|fda|package[_\-]insert|tablets?|capsules?|solution|injection|\d+mg|\d+ml)$", "", stem).strip()

    cleaned = stem.replace("_", " ").replace("-", " ").strip()
    # Strip trailing helper words like "Sample"
    cleaned = re.sub(r"(?i)\s+(sample|test\d*)$", "", cleaned).strip()

    if cleaned:
        words = cleaned.split()
        return " ".join(w.capitalize() for w in words)
    return file_path.stem


def compute_file_sha256(file_path: Path) -> str:
    """Calculates SHA-256 hash of a file efficiently using chunked reads."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class ScannerService:
    """
    Automated background folder watcher and section extractor.
    Scans WATCH_DIR every 30 minutes, detects new or modified PDFs using delta hashing,
    and extracts Section 16 data into PostgreSQL for immediate client retrieval.
    """

    def __init__(
        self,
        watch_dir: Path = WATCH_DIR,
        interval_minutes: int = SCAN_INTERVAL_MINUTES,
        target_section: str = DEFAULT_TARGET_SECTION,
    ):
        self.watch_dir = watch_dir
        self.interval_seconds = interval_minutes * 60
        self.target_section = target_section
        self.extractor = SectionExtractor()
        
        # State tracking
        self.is_running = False
        self.is_scanning = False
        self._task: Optional[asyncio.Task] = None
        self.last_scan_time: Optional[datetime.datetime] = None
        self.next_scan_time: Optional[datetime.datetime] = None
        
        # Cumulative metrics
        self.total_scans_completed = 0
        self.total_files_indexed = 0
        self.last_scan_stats: Dict[str, Any] = {}
        self.last_error: Optional[str] = None

    def start(self):
        """Starts the automated background scanner task."""
        if self.is_running:
            logger.info("ScannerService is already running.")
            return

        self.is_running = True
        self._task = asyncio.create_task(self._background_loop(), name="pdf_folder_scanner")
        logger.info(
            "ScannerService started. Watching '%s' every %d minutes (Target Section: %s).",
            self.watch_dir,
            SCAN_INTERVAL_MINUTES,
            self.target_section,
        )

    async def stop(self):
        """Gracefully stops the background scanner task."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ScannerService stopped.")

    async def _background_loop(self):
        """Continuous background loop running every 30 minutes."""
        if SCAN_ON_STARTUP:
            logger.info("Performing initial startup folder scan...")
            try:
                await self.scan_once_async()
            except Exception as e:
                logger.error("Error during startup folder scan: %s", e)

        while self.is_running:
            self.next_scan_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                seconds=self.interval_seconds
            )
            try:
                await asyncio.sleep(self.interval_seconds)
                if self.is_running:
                    await self.scan_once_async()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Unexpected error in scanner loop: %s", exc)
                self.last_error = str(exc)
                await asyncio.sleep(10)  # Brief pause before retrying loop

    async def scan_once_async(self) -> Dict[str, Any]:
        """Runs scan in a separate thread so CPU-heavy PDF parsing doesn't block the async event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.scan_once)

    def scan_once(self) -> Dict[str, Any]:
        """
        Executes a single synchronous scan of the watch directory.
        Finds all PDFs, filters for new or modified files via mtime & SHA-256,
        and extracts Section 16 into the database.
        """
        if self.is_scanning:
            logger.warning("Scan already in progress. Skipping overlapping request.")
            return {"status": "skipped", "message": "Scan already in progress"}

        self.is_scanning = True
        start_time = time.time()
        scan_id = uuid.uuid4().hex[:8]
        scanned_at = datetime.datetime.now(datetime.timezone.utc)

        self.watch_dir.mkdir(parents=True, exist_ok=True)
        pdf_files: List[Path] = [
            f for f in self.watch_dir.rglob("*.pdf")
            if f.is_file() and not f.name.startswith(".")
        ]

        total_found = len(pdf_files)
        files_processed = 0
        files_skipped = 0
        files_errored = 0
        processed_details = []

        logger.info(
            "[Scan %s] Scanning watch folder '%s'. Found %d PDF(s).",
            scan_id,
            self.watch_dir,
            total_found,
        )

        with get_db_session() as session:
            for p in pdf_files:
                try:
                    stat = p.stat()
                    mtime = stat.st_mtime
                    size_bytes = stat.st_size

                    # Check DB for existing record
                    existing = session.query(ProductSectionRecord).filter_by(
                        filename=p.name,
                        target_section=self.target_section
                    ).first()

                    # Delta check: if file unmodified and previously successfully processed, SKIP
                    if existing and existing.file_mtime == mtime and existing.file_size_bytes == size_bytes:
                        files_skipped += 1
                        continue

                    # If mtime or size changed, verify with SHA-256 hash
                    file_hash = compute_file_sha256(p)
                    if existing and existing.file_hash == file_hash and existing.status in ("success", "not_found"):
                        existing.file_mtime = mtime
                        files_skipped += 1
                        continue

                    # File is new or changed: Extract Section 16
                    logger.info("[Scan %s] Extracting Section %s for: %s", scan_id, self.target_section, p.name)
                    doc_name = p.name
                    product_name = extract_product_name_from_file(p)
                    norm_name = normalize_product_name(product_name)

                    # Total pages count
                    total_pages = 0
                    try:
                        with fitz.open(p) as doc:
                            total_pages = len(doc)
                    except Exception:
                        pass

                    # Run extraction
                    extraction = self.extractor.extract(
                        file_path_or_bytes=p,
                        main_section=self.target_section,
                        target_subsection=None,
                        doc_name=doc_name,
                        include_tables=True,
                    )

                    # Generate clean, semantic structured HTML
                    html_content = ExportService.generate_structured_html(
                        result=extraction,
                        product_name=product_name,
                        standalone=True,
                    )

                    # Extract section title from extraction
                    section_title = None
                    if extraction.blocks:
                        for blk in extraction.blocks:
                            if blk.block_type == "heading":
                                section_title = blk.text
                                break
                    if not section_title:
                        section_title = f"Section {self.target_section} - How Supplied / Storage and Handling"

                    # Collect tables from blocks
                    tables_list = []
                    for blk in extraction.blocks:
                        if blk.block_type == "table":
                            tables_list.append({
                                "id": blk.id,
                                "page": blk.page,
                                "columns": blk.table_columns or [],
                                "rows": blk.table_rows or [],
                                "markdown": blk.table_markdown or "",
                            })

                    tables_json = json.dumps(tables_list)
                    
                    # Detailed structured subsections breakdown
                    subsections_data = ExportService.extract_subsections_data(extraction, product_name=product_name)
                    subsections_json = json.dumps(subsections_data)

                    confidence = getattr(extraction.validation, "confidence_score", 1.0)
                    metadata_json = json.dumps({
                        "doc_name": doc_name,
                        "total_pages": total_pages,
                        "confidence_score": confidence,
                        "has_tables": len(tables_list) > 0,
                        "subsections_count": len(subsections_data),
                    })


                    now = datetime.datetime.now(datetime.timezone.utc)

                    if existing:
                        existing.product_name = product_name
                        existing.product_normalized = norm_name
                        existing.file_path = str(p.resolve())
                        existing.file_hash = file_hash
                        existing.file_mtime = mtime
                        existing.file_size_bytes = size_bytes
                        existing.total_pages = total_pages
                        existing.section_title = section_title
                        existing.start_page = extraction.start_page
                        existing.end_page = extraction.end_page
                        existing.status = extraction.status
                        existing.confidence_score = confidence
                        existing.extracted_text = extraction.content
                        existing.extracted_html = html_content
                        existing.tables_json = tables_json
                        existing.subsections_json = subsections_json
                        existing.metadata_json = metadata_json
                        existing.updated_at = now
                    else:
                        new_record = ProductSectionRecord(
                            id=str(uuid.uuid4()),
                            product_name=product_name,
                            product_normalized=norm_name,
                            filename=p.name,
                            file_path=str(p.resolve()),
                            file_hash=file_hash,
                            file_mtime=mtime,
                            file_size_bytes=size_bytes,
                            total_pages=total_pages,
                            target_section=self.target_section,
                            section_title=section_title,
                            start_page=extraction.start_page,
                            end_page=extraction.end_page,
                            status=extraction.status,
                            confidence_score=confidence,
                            extracted_text=extraction.content,
                            extracted_html=html_content,
                            tables_json=tables_json,
                            subsections_json=subsections_json,
                            metadata_json=metadata_json,
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(new_record)

                    files_processed += 1
                    processed_details.append({
                        "filename": p.name,
                        "product_name": product_name,
                        "status": extraction.status,
                        "pages": f"{extraction.start_page}-{extraction.end_page}",
                    })

                except Exception as file_err:
                    files_errored += 1
                    logger.error("[Scan %s] Failed processing '%s': %s", scan_id, p.name, file_err)
                    processed_details.append({
                        "filename": p.name,
                        "status": "error",
                        "error": str(file_err),
                    })

            # Record scan audit log
            duration = round(time.time() - start_time, 2)
            scan_log = ScannerLogRecord(
                id=str(uuid.uuid4()),
                scanned_at=scanned_at,
                duration_seconds=duration,
                files_scanned=total_found,
                files_processed=files_processed,
                files_skipped=files_skipped,
                files_errored=files_errored,
                status="completed" if files_errored == 0 else "completed_with_errors",
                error_message=f"{files_errored} errors encountered" if files_errored > 0 else None,
                details_json=json.dumps(processed_details[:50]),
            )
            session.add(scan_log)

            # Update metrics
            self.total_files_indexed = session.query(ProductSectionRecord).count()

        duration = round(time.time() - start_time, 2)
        self.last_scan_time = scanned_at
        self.total_scans_completed += 1
        self.is_scanning = False

        stats = {
            "scan_id": scan_id,
            "status": "completed",
            "duration_seconds": duration,
            "files_scanned": total_found,
            "files_processed": files_processed,
            "files_skipped": files_skipped,
            "files_errored": files_errored,
            "total_products_in_db": self.total_files_indexed,
            "scanned_at": scanned_at.isoformat(),
        }
        self.last_scan_stats = stats
        logger.info(
            "[Scan %s Finished] Scanned: %d | Processed: %d | Skipped: %d | Errored: %d | Time: %.2fs",
            scan_id,
            total_found,
            files_processed,
            files_skipped,
            files_errored,
            duration,
        )
        return stats

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive diagnostic and operational metrics for the scanner."""
        with get_db_session() as session:
            total_records = session.query(ProductSectionRecord).count()
            success_records = session.query(ProductSectionRecord).filter_by(status="success").count()

        return {
            "status": "running" if self.is_running else "stopped",
            "is_scanning_now": self.is_scanning,
            "watch_directory": str(self.watch_dir.resolve()),
            "scan_interval_minutes": self.interval_seconds // 60,
            "target_section": self.target_section,
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "next_scan_time": self.next_scan_time.isoformat() if self.next_scan_time else None,
            "total_scans_completed": self.total_scans_completed,
            "total_products_indexed": total_records,
            "successful_extractions": success_records,
            "last_scan_summary": self.last_scan_stats,
            "last_error": self.last_error,
        }


# Global singleton scanner instance
scanner_service = ScannerService()
