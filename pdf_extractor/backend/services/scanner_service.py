import asyncio
import datetime
import hashlib
import json
import logging
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Union

import fitz  # PyMuPDF

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    Observer = None
    FileSystemEventHandler = object
    HAS_WATCHDOG = False

from backend.config import (
    WATCH_DIR,
    WATCH_DIRS,
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
    1. First parses and cleans the filename (stripping upload hashes, dates, report suffixes).
    2. Inspects first page of the PDF for 'ACTIVE SUBSTANCE: <name>', 'Invented Name', or clean headings.
    """
    p = Path(file_path)

    # Heuristic 1: Clean filename
    stem = p.stem
    # Strip leading hex/hash uuid like '9c7c7ccd_'
    stem = re.sub(r"^[0-9a-f]{8,32}[_\-\s]+", "", stem, flags=re.IGNORECASE)

    # Strip trailing report identifiers, dates, dosages
    patterns = [
        r"(?i)[\s_\-]+(can\s+pbrer|can[_\-]pbrer|pbrer|psur|dsur|pi|cmi|label|lbl|monograph|fda|package[_\-]insert)[\s_\-0-9].*$",
        r"(?i)[\s_\-]+(can\s+pbrer|can[_\-]pbrer|pbrer|psur|dsur|pi|cmi|label|lbl|monograph|fda|package[_\-]insert)$",
        r"(?i)[\s_\-]+can[\s_\-]+pbrer.*$",
        r"(?i)[\s_\-]+(\d+mg|\d+ml|\d+mcg)[\s_\-].*$",
        r"(?i)[\s_\-]+(\d+mg|\d+ml|\d+mcg)$",
        r"(?i)[\s_\-]+(tablets?|capsules?|solution|injection)[\s_\-].*$",
        r"(?i)[\s_\-]+(tablets?|capsules?|solution|injection)$",
        r"(?i)[\s_\-]+(\d{8}|\d{4}[_\-]\d{2}[_\-]\d{2}).*$",
        r"(?i)[\s_\-]+(sample|test\d*)$",
    ]
    for pat in patterns:
        stem = re.sub(pat, "", stem).strip()

    cleaned_filename = stem.replace("_", " ").replace("-", " ").strip()
    cleaned_filename = re.sub(r"(?i)\s+can$", "", cleaned_filename).strip()
    generic_names = {"test", "sample", "document", "doc", "pdf", "file", "output", "input", "data"}

    if cleaned_filename and cleaned_filename.lower() not in generic_names:
        return " ".join(w.capitalize() for w in cleaned_filename.split())

    # Heuristic 2: Inspect first page of PDF
    try:
        doc = fitz.open(p)
        if len(doc) > 0:
            text = doc[0].get_text("text")

            # Check for 'ACTIVE SUBSTANCE: <name>'
            sub_match = re.search(r"ACTIVE\s+SUBSTANCE\s*:\s*([A-Za-z0-9\s\-]+)", text, re.IGNORECASE)
            if sub_match:
                sub = sub_match.group(1).split("\n")[0].strip()
                sub = re.split(r"[,;/\(\)]", sub)[0].strip()
                if len(sub) >= 3 and sub.upper() not in ("CONFIDENTIAL", "UNKNOWN", "SEE"):
                    doc.close()
                    return sub.title()

            # Check for 'Invented Name...: <name>'
            inv_match = re.search(r"Invented\s+Name[^\n]*\n+([A-Za-z0-9\s\-\'\™\®]+)", text, re.IGNORECASE)
            if inv_match:
                inv = inv_match.group(1).strip()
                inv = re.sub(r"[™®]", "", inv)
                inv = re.split(r"[,;/\(\)\n]", inv)[0].strip()
                if len(inv) >= 3 and inv.upper() not in ("CONFIDENTIAL", "UNKNOWN", "THE", "OF"):
                    doc.close()
                    return inv.title()

            # Check top lines of page 1
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            blacklist = {
                "CONFIDENTIAL", "PERIODIC", "BENEFIT", "RISK", "EVALUATION",
                "REPORT", "SAFETY", "UPDATE", "TABLE", "CONTENTS", "HIGHLIGHTS",
                "PRESCRIBING", "INFORMATION", "PACKAGE", "INSERT", "VERSION",
                "APOTEX", "INC", "SEARCHLIGHT", "PHARMA", "FOR", "CANADIAN", "SECTION"
            }
            for line in lines[:8]:
                clean_l = re.sub(r"[™®]", "", line).strip()
                if re.match(r"^(section\s+)?\d+(\.\d+)*\b", clean_l, re.IGNORECASE):
                    continue
                clean_l = re.split(r"[\(\[\{]", clean_l)[0].strip()
                words = [w for w in re.split(r"[^A-Za-z0-9]", clean_l) if w]
                if not words:
                    continue
                if words[0].upper() in blacklist:
                    continue
                if len(clean_l) >= 3 and not clean_l.isdigit():
                    doc.close()
                    return clean_l.title()
        doc.close()
    except Exception as exc:
        logger.debug("First page inspection skipped for %s: %s", p.name, exc)

    return p.stem


def compute_file_sha256(file_path: Path) -> str:
    """Calculates SHA-256 hash of a file efficiently using chunked reads."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def save_extraction_to_db(
    file_path: Path,
    extraction: Any,
    target_section: str = "16",
    product_name: Optional[str] = None,
    session: Optional[Any] = None,
) -> Optional[ProductSectionRecord]:
    """
    Saves or updates an ExtractionResult into the PostgreSQL product_sections table.
    Can be called within an existing db session or creates its own.
    """
    p = Path(file_path).resolve()
    if not p.exists():
        logger.warning("save_extraction_to_db called on non-existent path: %s", p)
        return None

    try:
        stat = p.stat()
        mtime = stat.st_mtime
        size_bytes = stat.st_size
    except Exception:
        mtime = 0.0
        size_bytes = 0

    try:
        file_hash = compute_file_sha256(p)
    except Exception:
        file_hash = ""

    if not product_name:
        product_name = extract_product_name_from_file(p)
    norm_name = normalize_product_name(product_name)

    total_pages = 0
    try:
        with fitz.open(p) as doc:
            total_pages = len(doc)
    except Exception:
        pass

    # Generate clean, semantic structured HTML
    html_content = ExportService.generate_structured_html(
        result=extraction,
        product_name=product_name,
        standalone=True,
    )

    # Extract section title from extraction
    section_title = None
    if getattr(extraction, "blocks", None):
        for blk in extraction.blocks:
            if blk.block_type == "heading":
                section_title = blk.text
                break
    if not section_title:
        section_title = f"Section {target_section} - Clinical Information"

    # Collect tables from blocks
    tables_list = []
    if getattr(extraction, "blocks", None):
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
    subsections_data = ExportService.extract_subsections_data(extraction, product_name=product_name)
    subsections_json = json.dumps(subsections_data)

    confidence = getattr(getattr(extraction, "validation", None), "confidence_score", 1.0)
    metadata_json = json.dumps({
        "doc_name": p.name,
        "total_pages": total_pages,
        "confidence_score": confidence,
        "has_tables": len(tables_list) > 0,
        "subsections_count": len(subsections_data),
    })

    now = datetime.datetime.now(datetime.timezone.utc)

    def _persist(db_sess):
        existing = db_sess.query(ProductSectionRecord).filter_by(
            filename=p.name,
            target_section=str(target_section)
        ).first()

        if existing:
            existing.product_name = product_name
            existing.product_normalized = norm_name
            existing.file_path = str(p)
            existing.file_hash = file_hash
            existing.file_mtime = mtime
            existing.file_size_bytes = size_bytes
            existing.total_pages = total_pages
            existing.section_title = section_title
            existing.start_page = getattr(extraction, "start_page", 0)
            existing.end_page = getattr(extraction, "end_page", 0)
            existing.status = getattr(extraction, "status", "success")
            existing.confidence_score = confidence
            existing.extracted_text = getattr(extraction, "content", "")
            existing.extracted_html = html_content
            existing.tables_json = tables_json
            existing.subsections_json = subsections_json
            existing.metadata_json = metadata_json
            existing.updated_at = now
            return existing
        else:
            new_record = ProductSectionRecord(
                id=str(uuid.uuid4()),
                product_name=product_name,
                product_normalized=norm_name,
                filename=p.name,
                file_path=str(p),
                file_hash=file_hash,
                file_mtime=mtime,
                file_size_bytes=size_bytes,
                total_pages=total_pages,
                target_section=str(target_section),
                section_title=section_title,
                start_page=getattr(extraction, "start_page", 0),
                end_page=getattr(extraction, "end_page", 0),
                status=getattr(extraction, "status", "success"),
                confidence_score=confidence,
                extracted_text=getattr(extraction, "content", ""),
                extracted_html=html_content,
                tables_json=tables_json,
                subsections_json=subsections_json,
                metadata_json=metadata_json,
                created_at=now,
                updated_at=now,
            )
            db_sess.add(new_record)
            return new_record

    if session:
        return _persist(session)
    else:
        with get_db_session() as new_sess:
            rec = _persist(new_sess)
            new_sess.commit()
            return rec


def is_file_ready(p: Path, retries: int = 4, delay: float = 0.5) -> bool:
    """Verifies that a file is done being written and can be read as a valid PDF."""
    if not p.exists():
        return False
    for _ in range(retries):
        try:
            s1 = p.stat().st_size
            if s1 == 0:
                time.sleep(delay)
                continue
            time.sleep(delay)
            s2 = p.stat().st_size
            if s1 == s2 and s1 > 0:
                with fitz.open(p) as doc:
                    if len(doc) >= 0:
                        return True
        except Exception:
            time.sleep(delay)
    return p.exists() and p.stat().st_size > 0


class PDFWatcherHandler(FileSystemEventHandler):
    """
    Real-time filesystem event listener that detects newly added or modified PDFs
    across watched directories and triggers automatic extraction and database ingestion.
    """
    def __init__(self, scanner: "ScannerService"):
        super().__init__()
        self.scanner = scanner
        self._debounce_lock = threading.Lock()
        self._timers: Dict[str, threading.Timer] = {}

    def _schedule_processing(self, file_path_str: str):
        if not file_path_str.lower().endswith(".pdf"):
            return
        p = Path(file_path_str)
        if p.name.startswith(".") or p.name.startswith("~"):
            return

        with self._debounce_lock:
            existing = self._timers.get(file_path_str)
            if existing:
                try:
                    existing.cancel()
                except Exception:
                    pass
            # 1.5 second debounce allows file copy / download stream completion
            timer = threading.Timer(1.5, self._execute_processing, args=[p])
            self._timers[file_path_str] = timer
            timer.daemon = True
            timer.start()

    def _execute_processing(self, path: Path):
        with self._debounce_lock:
            self._timers.pop(str(path), None)

        try:
            if not is_file_ready(path):
                logger.warning("[AutoWatcher] File '%s' not ready or corrupted. Retrying once...", path.name)
                time.sleep(1.0)
                if not is_file_ready(path):
                    logger.error("[AutoWatcher] File '%s' could not be opened.", path.name)
                    return

            logger.info("[AutoWatcher] Automatically ingesting newly added/modified PDF: %s", path.name)
            res = self.scanner.process_single_pdf(path)
            logger.info(
                "[AutoWatcher] Result for '%s': %s (Product: %s)",
                path.name,
                res.get("status"),
                res.get("product_name", "N/A"),
            )
        except Exception as exc:
            logger.error("[AutoWatcher] Failed to automatically process '%s': %s", path.name, exc)

    def on_created(self, event):
        if not event.is_directory:
            self._schedule_processing(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._schedule_processing(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._schedule_processing(event.dest_path)


class ScannerService:
    """
    Automated real-time and background folder watcher and section extractor.
    - Watches WATCH_DIRS in real-time via OS filesystem notifications (watchdog)
      so any newly added PDF is immediately extracted and stored without manual action.
    - Runs periodic background scans (every 30 mins) as a resilient fallback.
    - Employs delta hashing (mtime + SHA-256) to skip unchanged files.
    - Extracts Section 16 data into PostgreSQL for immediate client retrieval.
    """

    def __init__(
        self,
        watch_dirs: Optional[List[Path]] = None,
        watch_dir: Optional[Path] = None,
        interval_minutes: int = SCAN_INTERVAL_MINUTES,
        target_section: str = DEFAULT_TARGET_SECTION,
    ):
        if watch_dirs:
            self.watch_dirs = watch_dirs
        elif watch_dir:
            self.watch_dirs = [watch_dir]
        else:
            self.watch_dirs = WATCH_DIRS

        self.watch_dir = self.watch_dirs[0] if self.watch_dirs else WATCH_DIR
        self.interval_seconds = interval_minutes * 60
        self.target_section = target_section
        self.extractor = SectionExtractor()

        # State tracking
        self.is_running = False
        self.is_scanning = False
        self._task: Optional[asyncio.Task] = None
        self.last_scan_time: Optional[datetime.datetime] = None
        self.next_scan_time: Optional[datetime.datetime] = None

        # Real-time observer
        self._observer: Optional[Any] = None
        self._handler: Optional[Any] = None
        self._proc_lock = threading.Lock()
        self._currently_processing: Set[str] = set()

        # Cumulative metrics
        self.total_scans_completed = 0
        self.total_files_indexed = 0
        self.last_scan_stats: Dict[str, Any] = {}
        self.last_error: Optional[str] = None

    def start(self):
        """Starts the automated background scanner task and real-time filesystem watcher."""
        if self.is_running:
            logger.info("ScannerService is already running.")
            return

        self.is_running = True
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._background_loop(), name="pdf_folder_scanner")
        except RuntimeError:
            self._task = None

        dir_names = ", ".join(str(d) for d in self.watch_dirs)
        logger.info(
            "ScannerService started. Watching [%s] every %d minutes (Target Section: %s).",
            dir_names,
            SCAN_INTERVAL_MINUTES,
            self.target_section,
        )

        # Start real-time watchdog observer
        if HAS_WATCHDOG and Observer is not None:
            try:
                self._observer = Observer()
                self._handler = PDFWatcherHandler(self)
                attached_count = 0
                for d in self.watch_dirs:
                    try:
                        d.mkdir(parents=True, exist_ok=True)
                        self._observer.schedule(self._handler, str(d.resolve()), recursive=True)
                        logger.info("[AutoWatcher] Active real-time watcher on: %s", d.resolve())
                        attached_count += 1
                    except Exception as d_err:
                        logger.warning("[AutoWatcher] Could not attach observer to '%s': %s", d, d_err)
                if attached_count > 0:
                    self._observer.start()
                    logger.info("[AutoWatcher] Real-time filesystem observer started across %d directories.", attached_count)
            except Exception as obs_err:
                logger.warning("[AutoWatcher] Watchdog observer initialization skipped: %s", obs_err)

    def stop_sync(self):
        """Synchronously stops the real-time watchdog observer and cancels background tasks."""
        self.is_running = False
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=3)
            except Exception:
                pass
            self._observer = None

        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("ScannerService stopped synchronously.")

    async def stop(self):
        """Gracefully stops the background scanner task and real-time filesystem watcher."""
        self.stop_sync()
        if self._task and not self._task.done():
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

    async def scan_once_async(self, custom_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Runs scan in a separate thread so CPU-heavy PDF parsing doesn't block the async event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.scan_once, custom_dir)

    def process_single_pdf(
        self,
        file_path: Union[str, Path],
        session: Optional[Any] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Processes a single PDF:
        - Performs delta hash and mtime checks to skip unchanged files.
        - Automatically identifies the medicine / product name.
        - Deterministically extracts Section 16 (and its subsections).
        - Saves all structured content, HTML snippets, and tables to PostgreSQL.
        """
        p = Path(file_path).resolve()
        if not p.exists() or not p.is_file():
            return {"status": "error", "filename": p.name, "error": "File does not exist"}

        if not p.name.lower().endswith(".pdf"):
            return {"status": "skipped", "filename": p.name, "reason": "Not a PDF"}

        with self._proc_lock:
            if str(p) in self._currently_processing:
                logger.debug("File %s is already currently being processed.", p.name)
                return {"status": "skipped", "filename": p.name, "reason": "Already processing"}
            self._currently_processing.add(str(p))

        try:
            stat = p.stat()
            mtime = stat.st_mtime
            size_bytes = stat.st_size

            def _check_and_extract(db_sess):
                existing = db_sess.query(ProductSectionRecord).filter_by(
                    filename=p.name,
                    target_section=self.target_section
                ).first()

                if not force and existing and existing.file_mtime == mtime and existing.file_size_bytes == size_bytes:
                    return {"status": "skipped", "filename": p.name, "reason": "unmodified"}

                file_hash = compute_file_sha256(p)
                if not force and existing and existing.file_hash == file_hash and existing.status in ("success", "not_found"):
                    existing.file_mtime = mtime
                    return {"status": "skipped", "filename": p.name, "reason": "hash_match"}

                # File is new or changed: Extract Section 16
                product_name = extract_product_name_from_file(p)
                logger.info(
                    "[Scanner] Extracting Section %s for product '%s' from: %s",
                    self.target_section,
                    product_name,
                    p.name,
                )

                extraction = self.extractor.extract(
                    file_path_or_bytes=p,
                    main_section=self.target_section,
                    target_subsection=None,
                    doc_name=p.name,
                    include_tables=True,
                )

                save_extraction_to_db(
                    file_path=p,
                    extraction=extraction,
                    target_section=self.target_section,
                    product_name=product_name,
                    session=db_sess,
                )

                return {
                    "status": "processed",
                    "filename": p.name,
                    "product_name": product_name,
                    "extraction_status": extraction.status,
                    "pages": f"{extraction.start_page}-{extraction.end_page}",
                }

            if session:
                return _check_and_extract(session)
            else:
                with get_db_session() as new_session:
                    res = _check_and_extract(new_session)
                    new_session.commit()
                    self.total_files_indexed = new_session.query(ProductSectionRecord).count()
                    return res
        except Exception as exc:
            logger.error("Error processing single PDF '%s': %s", p.name, exc)
            return {"status": "error", "filename": p.name, "error": str(exc)}
        finally:
            with self._proc_lock:
                self._currently_processing.discard(str(p))

    def scan_once(self, custom_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Executes a single synchronous scan of the watch directories (or custom_dir).
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

        search_dirs: List[Path] = [Path(custom_dir).resolve()] if custom_dir else self.watch_dirs
        pdf_files: List[Path] = []
        for s_dir in search_dirs:
            try:
                s_dir.mkdir(parents=True, exist_ok=True)
                pdf_files.extend([
                    f for f in s_dir.rglob("*.pdf")
                    if f.is_file() and not f.name.startswith(".")
                ])
            except Exception as d_err:
                logger.error("Error reading directory '%s': %s", s_dir, d_err)

        # Deduplicate files by absolute path
        unique_files: List[Path] = []
        seen_paths = set()
        for f in pdf_files:
            resolved = f.resolve()
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                unique_files.append(f)
        pdf_files = unique_files

        total_found = len(pdf_files)
        files_processed = 0
        files_skipped = 0
        files_errored = 0
        processed_details = []

        logger.info(
            "[Scan %s] Scanning %d directories. Found %d PDF(s).",
            scan_id,
            len(search_dirs),
            total_found,
        )

        with get_db_session() as session:
            for p in pdf_files:
                res = self.process_single_pdf(p, session=session)
                if res.get("status") == "processed":
                    files_processed += 1
                    processed_details.append(res)
                elif res.get("status") == "skipped":
                    files_skipped += 1
                elif res.get("status") == "error":
                    files_errored += 1
                    processed_details.append(res)

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
            "realtime_watcher": "active" if (self._observer and self._observer.is_alive()) else "idle",
            "is_scanning_now": self.is_scanning,
            "watch_directory": str(self.watch_dir.resolve()),
            "watched_directories": [str(d.resolve()) for d in self.watch_dirs],
            "scan_interval_minutes": self.interval_seconds // 60,
            "target_section": self.target_section,
            "instant_automation": True,
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
