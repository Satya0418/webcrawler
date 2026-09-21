"""
FDA MedWatch PDF Handler.
Interfaces directly with the existing project PDF extraction pipeline (pdf_extractor)
without creating duplicate parsers, OCR, or table engines.
Preserves page numbers, table structures, percentages, and subheadings.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

from app.sources.fda_medwatch.config import (
    CONNECT_TIMEOUT,
    DEFAULT_HEADERS,
    NOT_FOUND_IN_DOC_MSG,
    PDF_CACHE_DIR,
    PDF_DOWNLOAD_TIMEOUT,
    SECTION_ADVERSE_REACTIONS,
    SECTION_PREGNANCY,
    SECTION_USE_IN_SPECIFIC_POPULATIONS,
    SECTION_WARNINGS_PRECAUTIONS,
)
from app.sources.fda_medwatch.models import MedWatchSectionItem

logger = logging.getLogger(__name__)

# Ensure pdf_extractor is importable from project root without modifying it
_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # webcrwler
_PDF_EXTRACTOR_DIR = _PROJECT_ROOT / "pdf_extractor"
if str(_PDF_EXTRACTOR_DIR) not in sys.path:
    sys.path.insert(0, str(_PDF_EXTRACTOR_DIR))


class FDAMedWatchPDFHandler:
    """Extracts FDA Prescribing Information sections and tables using the existing PDF extractor."""

    def __init__(self, timeout: float = PDF_DOWNLOAD_TIMEOUT) -> None:
        self.timeout = timeout
        self.cache_dir = PDF_CACHE_DIR

    async def fetch_pdf_bytes(self, pdf_url_or_path: str) -> Optional[bytes]:
        """
        Retrieves PDF content as bytes from a local file path or remote URL.
        Caches remote PDF downloads on disk so subsequent reads are instantaneous.
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

        # Check local disk cache
        url_hash = hashlib.md5(pdf_url_or_path.encode("utf-8")).hexdigest()
        cached_file = self.cache_dir / f"{url_hash}.pdf"
        if cached_file.exists() and cached_file.stat().st_size > 1000:
            logger.info("Using cached FDA MedWatch label PDF for %s (%d bytes)", pdf_url_or_path, cached_file.stat().st_size)
            try:
                return cached_file.read_bytes()
            except Exception as exc:
                logger.warning("Failed to read cached FDA PDF %s: %s", cached_file, exc)

        # Download remote PDF
        req_headers = dict(DEFAULT_HEADERS)
        req_headers["Connection"] = "close"

        logger.info("FDA_MEDWATCH_PDF_DOWNLOAD_STARTED: Downloading %s", pdf_url_or_path)
        try:
            async with httpx.AsyncClient(
                headers=req_headers,
                timeout=httpx.Timeout(self.timeout, connect=CONNECT_TIMEOUT, read=self.timeout),
                follow_redirects=True,
            ) as client:
                resp = await client.get(pdf_url_or_path)
                if resp.status_code == 200 and resp.content:
                    if resp.content.startswith(b"%PDF") or "pdf" in resp.headers.get("content-type", "").lower():
                        logger.info("FDA_MEDWATCH_PDF_DOWNLOAD_COMPLETED: Downloaded FDA PDF from %s (%d bytes)", pdf_url_or_path, len(resp.content))
                        cached_file.write_bytes(resp.content)
                        return resp.content
                    logger.warning("FDA_MEDWATCH_ERROR: Downloaded content from %s is not a PDF", pdf_url_or_path)
                    return None
                logger.warning("FDA_MEDWATCH_ERROR: Failed to download FDA PDF from %s (HTTP %d)", pdf_url_or_path, resp.status_code)
                return None
        except Exception as exc:
            logger.warning("FDA_MEDWATCH_ERROR: Network exception downloading FDA PDF %s: %s", pdf_url_or_path, exc)
            return None

    def _validate_product_in_doc(
        self, doc: Any, target_product: Optional[str], active_ingredient: Optional[str]
    ) -> bool:
        """
        Validates that the PDF document actually belongs to the requested product
        by checking the document title, headers, or initial pages.
        Prevents extracting an unrelated product's labeling info.
        """
        if not target_product:
            return True

        prod_clean = target_product.strip().lower()
        ingr_clean = (active_ingredient or "").strip().lower()

        # Check first 5 pages for product name or active ingredient
        max_check_pages = min(5, len(doc))
        full_text = ""
        for pno in range(max_check_pages):
            full_text += " " + doc[pno].get_text()

        full_text_lower = full_text.lower()
        if prod_clean in full_text_lower:
            return True
        if ingr_clean and len(ingr_clean) > 3 and ingr_clean in full_text_lower:
            return True

        return False

    def _process_tables_with_titles_and_continuations(self, clean_blocks: List[Any]) -> List[Dict[str, Any]]:
        """
        Associates tables with their preceding titles/captions and combines
        multi-page continuation tables while preserving headers, rows, and all page references.
        """
        processed_tables: List[Dict[str, Any]] = []
        for i, b in enumerate(clean_blocks):
            if b.block_type == "table":
                # Check for preceding title block
                title = "Adverse Reactions Table"
                if i > 0 and clean_blocks[i - 1].block_type != "table":
                    prev_text = clean_blocks[i - 1].text.strip()
                    table_title_match = re.search(r"(?:Table|TABLE)\s+\d+[:\.]?\s*[^\n]+", prev_text)
                    if table_title_match:
                        title = table_title_match.group(0).strip().replace("\n", " ")
                    elif prev_text.startswith("Table") or prev_text.startswith("TABLE"):
                        title = prev_text.split("\n")[0].strip()

                cols = getattr(b, "table_columns", []) or []
                rows = getattr(b, "table_rows", []) or []
                p_num = b.page_num
                md = getattr(b, "table_markdown", "") or ""

                # Check if this table is a multi-page continuation of the immediately preceding table
                has_new_title = False
                if i > 0 and clean_blocks[i - 1].block_type != "table":
                    prev_text = clean_blocks[i - 1].text.strip()
                    if re.search(r"(?:Table|TABLE)\s+\d+", prev_text):
                        has_new_title = True

                is_continuation = (
                    bool(processed_tables)
                    and not has_new_title
                    and len(cols) == len(processed_tables[-1]["headers"])
                    and p_num > processed_tables[-1]["pages"][-1]
                )

                if is_continuation:
                    prev = processed_tables[-1]
                    if p_num not in prev["pages"]:
                        prev["pages"].append(p_num)
                    if "page" not in prev:
                        prev["page"] = prev["pages"][0]
                    # When pdfplumber processes a continuation page without headers,
                    # it treats row 0 as columns. Add that first row to rows.
                    first_row_dict = {
                        prev["headers"][ci]: col_val
                        for ci, col_val in enumerate(cols)
                        if ci < len(prev["headers"])
                    }
                    prev["rows"].append(first_row_dict)
                    for r in rows:
                        aligned_r = {
                            prev["headers"][ci]: r.get(c, "")
                            for ci, c in enumerate(cols)
                            if ci < len(prev["headers"])
                        }
                        prev["rows"].append(aligned_r)
                    if md:
                        prev["markdown"] = (prev.get("markdown", "") + "\n" + md).strip()
                else:
                    processed_tables.append({
                        "table_id": getattr(b, "block_id", ""),
                        "title": title,
                        "page": p_num,
                        "pages": [p_num],
                        "headers": cols,
                        "columns": cols,
                        "rows": rows,
                        "markdown": md,
                    })

        return processed_tables

    def extract_subsections(
        self, clean_blocks: List[Any], tables_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Detects and preserves all subsections under ADVERSE REACTIONS (e.g. 6.1 Clinical Trials Experience,
        6.2 Postmarketing Experience, Other Clinical Trial Experience, etc.) without hardcoding.
        Returns subsection name, pages list, verbatim content, and associated tables.
        """
        subsections_raw: List[Dict[str, Any]] = []
        current_sub: Optional[Dict[str, Any]] = None

        SUBSEC_HEADER_PATTERNS = [
            r"^(?:SECTION\s*)?6[\.\s]+(\d+)[\.\s]*(.*)",
            r"^(?:6[\.\s]+)?(Clinical Trials?\s+Experience.*)",
            r"^(?:6[\.\s]+)?(Postmarketing\s+Experience.*)",
            r"^(?:6[\.\s]+)?(Post-Marketing\s+Experience.*)",
            r"^(?:6[\.\s]+)?(Other\s+Clinical\s+Trial\s+Experience.*)",
            r"^(?:6[\.\s]+)?(Immunogenicity.*)",
            r"^(?:6[\.\s]+)?(Laboratory\s+Abnormalities.*)",
        ]

        i = 0
        while i < len(clean_blocks):
            b = clean_blocks[i]
            txt = b.text.strip()
            is_sub = False
            sub_name = ""

            # Check if block is "6 1" or "6.1" (split heading)
            split_m = re.match(r"^(?:SECTION\s*)?6[\.\s]+(\d+)\s*$", txt, re.IGNORECASE)
            if split_m and b.is_heading:
                num = split_m.group(1)
                next_txt = clean_blocks[i + 1].text.strip() if i + 1 < len(clean_blocks) else ""
                if next_txt and len(next_txt) < 100 and not next_txt.startswith("|"):
                    sub_name = f"6.{num} {next_txt}"
                    is_sub = True
                    i += 1  # consume the next block as title
                else:
                    sub_name = f"6.{num}"
                    is_sub = True
            else:
                for pat in SUBSEC_HEADER_PATTERNS:
                    m = re.match(pat, txt, re.IGNORECASE)
                    if m and (b.is_heading or len(txt) < 90):
                        if "6" in pat:
                            sub_name = txt
                        else:
                            sub_name = m.group(1)
                        is_sub = True
                        break

            if is_sub:
                if current_sub:
                    subsections_raw.append(current_sub)
                current_sub = {
                    "name": sub_name,
                    "pages": {b.page_num},
                    "blocks": [],
                }
            elif current_sub:
                current_sub["pages"].add(b.page_num)
                current_sub["blocks"].append(b)
            else:
                # Text before the first subsection (introductory bullets/overview)
                current_sub = {
                    "name": "6. ADVERSE REACTIONS",
                    "pages": {b.page_num},
                    "blocks": [b],
                }
            i += 1

        if current_sub:
            subsections_raw.append(current_sub)

        formatted_subsections: List[Dict[str, Any]] = []
        for s in subsections_raw:
            s_pages = sorted(list(s["pages"]))
            s_text = self.format_blocks_to_text(s["blocks"])
            # Match tables on pages in this subsection
            sub_tables = [t for t in tables_data if any(p in s_pages for p in t.get("pages", []))]
            formatted_subsections.append({
                "name": s["name"],
                "pages": s_pages,
                "content": s_text,
                "tables": sub_tables,
            })

        return formatted_subsections

    def _extract_section_blocks_and_tables(
        self,
        pdf_path: Path,
        start_section: str,
        stop_sections: List[str],
        start_keywords: List[str],
        stop_keywords: List[str],
    ) -> Tuple[List[Any], List[Dict[str, Any]], Optional[int], Optional[int]]:
        """
        Uses existing PDFReader, PDFParser, HeadingDetector, and TableExtractor
        to locate section boundaries and extract all text blocks and structured tables.
        """
        from backend.pdf.reader import PDFReader
        from backend.pdf.parser import PDFParser
        from backend.pdf.headings import HeadingDetector
        from backend.pdf.tables import TableExtractor

        with PDFReader(str(pdf_path)) as reader:
            parser = PDFParser(reader.doc)
            raw = parser.parse()
            hd = HeadingDetector(body_font_size=parser.body_font_size, toc_bookmarks=reader.toc_bookmarks)
            blocks = hd.process_blocks(raw)

            # Extract tables using existing TableExtractor
            table_extractor = TableExtractor(str(pdf_path))
            table_blocks = table_extractor.extract_tables()
            merged = TableExtractor.merge_tables_with_blocks(blocks, table_blocks)

            start_idx = None
            stop_idx = None

            # Scan after Table of Contents (page >= 3)
            for i, b in enumerate(merged):
                if b.page_num < 3:
                    continue

                txt = " ".join(b.text.strip().split()).upper()
                sec = b.section_number or ""

                # Check start boundary
                if start_idx is None:
                    is_sec_match = (
                        (b.is_heading and sec == start_section and (txt == start_section or any(k.upper() in txt for k in start_keywords)))
                        or (b.is_heading and re.match(r"^(?:SECTION\s*)?" + re.escape(start_section) + r"[\.\s]+", txt, re.IGNORECASE))
                        or (any(k.upper() in txt for k in start_keywords) and (sec == start_section or (b.is_heading and re.search(r"\b" + re.escape(start_section) + r"\b", txt))))
                    )
                    if is_sec_match:
                        start_idx = i
                    continue


                # Check stop boundary
                if start_idx is not None and stop_idx is None:
                    is_stop_sec = any(
                        (b.is_heading and sec == stop_sec)
                        or (b.is_heading and txt.startswith(stop_sec))
                        for stop_sec in stop_sections
                    )
                    is_stop_keyword = any(
                        b.is_heading and k.upper() in txt
                        for k in stop_keywords
                    )
                    if is_stop_sec or is_stop_keyword:
                        stop_idx = i
                        break

            if start_idx is None:
                return [], [], None, None

            if stop_idx is None:
                stop_idx = len(merged)

            target_slice = merged[start_idx:stop_idx]
            clean_blocks = [b for b in target_slice if b.block_type not in ("header", "footer")]

            pages = sorted(list({b.page_num for b in clean_blocks})) if clean_blocks else []
            start_page = pages[0] if pages else None
            end_page = pages[-1] if pages else None

            # Process tables with titles and multi-page continuation
            tables_data = self._process_tables_with_titles_and_continuations(clean_blocks)

            return clean_blocks, tables_data, start_page, end_page

    def format_blocks_to_text(self, blocks: List[Any]) -> str:
        """Converts extracted DocumentBlock objects into structured, readable text."""
        lines = []
        last_page = None
        i = 0

        while i < len(blocks):
            b = blocks[i]
            if b.block_type == "table":
                # Include markdown table if available
                md = getattr(b, "table_markdown", None)
                if md:
                    lines.append(f"\n{md}\n")
                i += 1
                continue

            t = b.text.strip()
            if not t:
                i += 1
                continue

            if last_page != b.page_num:
                lines.append(f"[Page {b.page_num}]")
                last_page = b.page_num

            # Merge split headings like "6 1" and "Clinical Trial Experience" or "6" and "ADVERSE REACTIONS"
            if b.is_heading:
                m_num = re.match(r"^(?:SECTION\s*)?6[\.\s]*(\d+)?\s*$", t, re.IGNORECASE)
                if m_num and i + 1 < len(blocks):
                    next_b = blocks[i + 1]
                    next_t = next_b.text.strip()
                    if next_b.block_type != "table" and len(next_t) < 100 and not next_t.startswith("|"):
                        num_part = m_num.group(1)
                        if num_part:
                            merged_head = f"6.{num_part} {next_t}"
                        else:
                            merged_head = f"6. {next_t}" if not next_t.startswith("6") else next_t
                        lines.append(f"\n### {merged_head}\n")
                        i += 2
                        continue

                lines.append(f"\n### {t}\n")
            else:
                lines.append(t)
            i += 1

        return "\n\n".join(lines).strip()


    async def extract_sections(
        self,
        pdf_source: Union[str, Path, bytes],
        doc_name: str = "fda_label.pdf",
        pdf_url: Optional[str] = None,
        document_date: Optional[str] = None,
        version: Optional[str] = None,
        target_product: Optional[str] = None,
        active_ingredient: Optional[str] = None,
    ) -> Dict[str, MedWatchSectionItem]:
        """
        Extracts Section 6 (Adverse Reactions), Section 5 (Warnings and Precautions),
        and Section 8.1 (Pregnancy) using the existing PDF extraction pipeline.
        Validates product specificity, extracts subsections, and combines multi-page tables.
        """
        logger.info("FDA_MEDWATCH_PDF_EXTRACTION_STARTED: Extracting sections from %s", doc_name)

        temp_file_path = None
        target_path = None

        if isinstance(pdf_source, (str, Path)) and Path(pdf_source).exists():
            target_path = Path(pdf_source)
            logger.info("FDA_MEDWATCH_PDF_FOUND: Using local PDF file %s", pdf_source)
        elif isinstance(pdf_source, bytes):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                tf.write(pdf_source)
                temp_file_path = tf.name
                target_path = Path(temp_file_path)
                logger.info("FDA_MEDWATCH_PDF_FOUND: Received PDF bytes (%d bytes)", len(pdf_source))
        elif isinstance(pdf_source, str) and (pdf_source.startswith("http://") or pdf_source.startswith("https://")):
            pdf_bytes = await self.fetch_pdf_bytes(pdf_source)
            if not pdf_bytes:
                logger.error("FDA_MEDWATCH_ERROR: PDF download failed for %s", pdf_source)
                return self._build_empty_sections(status="PDF_EXTRACTION_FAILED")
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                tf.write(pdf_bytes)
                temp_file_path = tf.name
                target_path = Path(temp_file_path)
                logger.info("FDA_MEDWATCH_PDF_FOUND: Successfully fetched remote PDF %s", pdf_source)

        if not target_path or not target_path.exists():
            logger.error("FDA_MEDWATCH_ERROR: PDF target path does not exist for %s", doc_name)
            return self._build_empty_sections(status="PDF_EXTRACTION_FAILED")

        source_url_str = pdf_url or (str(pdf_source) if isinstance(pdf_source, str) else "")

        try:
            # Validate product specificity against PDF content
            from backend.pdf.reader import PDFReader
            try:
                with PDFReader(str(target_path)) as rdr:
                    if target_product and not self._validate_product_in_doc(rdr.doc, target_product, active_ingredient):
                        logger.warning(
                            "FDA_MEDWATCH_ERROR: Product mismatch for '%s' (PDF does not contain requested product)",
                            target_product,
                        )
                        return self._build_empty_sections(status="PRODUCT_MISMATCH_REJECTED")
            except Exception as read_err:
                logger.error("FDA_MEDWATCH_ERROR: Failed to open PDF %s: %s", target_path, read_err)
                return self._build_empty_sections(status="PDF_EXTRACTION_FAILED")

            # 1. Section 6: Adverse Reactions
            logger.info("FDA_MEDWATCH_ADVERSE_REACTIONS_SEARCH_STARTED: Searching for Section 6 Adverse Reactions in %s", doc_name)
            s6_blocks, s6_tables, s6_start, s6_end = self._extract_section_blocks_and_tables(
                pdf_path=target_path,
                start_section=SECTION_ADVERSE_REACTIONS,
                stop_sections=["7"],
                start_keywords=["ADVERSE REACTIONS"],
                stop_keywords=["DRUG INTERACTIONS"],
            )

            if s6_blocks:
                s6_text = self.format_blocks_to_text(s6_blocks)
                s6_page = f"{s6_start}-{s6_end}" if s6_start != s6_end else str(s6_start or "")
                s6_pages_list = sorted(list({b.page_num for b in s6_blocks}))
                s6_subsections = self.extract_subsections(s6_blocks, s6_tables)

                ar_item = MedWatchSectionItem(
                    found=True,
                    status="SUCCESS",
                    content=s6_text,
                    section="6. ADVERSE REACTIONS",
                    page=s6_page,
                    pages=s6_pages_list,
                    source_pdf=source_url_str,
                    document_date=document_date,
                    version=version,
                    subsections=s6_subsections,
                    tables=s6_tables,
                )
                logger.info("FDA_MEDWATCH_ADVERSE_REACTIONS_SECTION_FOUND: Section 6 Adverse Reactions identified on pages %s", s6_page)
                if s6_tables:
                    logger.info("FDA_MEDWATCH_ADVERSE_REACTIONS_TABLE_FOUND: Found %d adverse reaction tables on pages %s", len(s6_tables), s6_page)
                logger.info(
                    "FDA_MEDWATCH_ADVERSE_REACTIONS_EXTRACTION_COMPLETED: Extracted %d chars, %d subsections, %d tables (pages %s)",
                    len(s6_text),
                    len(s6_subsections),
                    len(s6_tables),
                    s6_page,
                )
            else:
                ar_item = MedWatchSectionItem(
                    found=False,
                    status="ADVERSE_REACTIONS_SECTION_NOT_FOUND",
                    content=NOT_FOUND_IN_DOC_MSG,
                    section="6. ADVERSE REACTIONS",
                    source_pdf=source_url_str,
                    document_date=document_date,
                    version=version,
                )
                logger.info("FDA_MEDWATCH_ADVERSE_REACTIONS_SECTION_NOT_FOUND: Section 6 Adverse Reactions not present in %s", doc_name)

            # 2. Section 5: Warnings and Precautions
            s5_blocks, s5_tables, s5_start, s5_end = self._extract_section_blocks_and_tables(
                pdf_path=target_path,
                start_section=SECTION_WARNINGS_PRECAUTIONS,
                stop_sections=["6"],
                start_keywords=["WARNINGS AND PRECAUTIONS"],
                stop_keywords=["ADVERSE REACTIONS"],
            )

            if s5_blocks:
                s5_text = self.format_blocks_to_text(s5_blocks)
                s5_page = f"{s5_start}-{s5_end}" if s5_start != s5_end else str(s5_start or "")
                s5_pages_list = sorted(list({b.page_num for b in s5_blocks}))
                wp_item = MedWatchSectionItem(
                    found=True,
                    status="SUCCESS",
                    content=s5_text,
                    section="5. WARNINGS AND PRECAUTIONS",
                    page=s5_page,
                    pages=s5_pages_list,
                    source_pdf=source_url_str,
                    document_date=document_date,
                    version=version,
                    tables=s5_tables,
                )
                logger.info("FDA_MEDWATCH_WARNINGS_FOUND: Extracted %d chars (pages %s)", len(s5_text), s5_page)
            else:
                wp_item = MedWatchSectionItem(
                    found=False,
                    status=NOT_FOUND_IN_DOC_MSG,
                    content=NOT_FOUND_IN_DOC_MSG,
                    section="5. WARNINGS AND PRECAUTIONS",
                    source_pdf=source_url_str,
                    document_date=document_date,
                    version=version,
                )
                logger.info("FDA_MEDWATCH_SECTION_NOT_FOUND: Section 5 Warnings and Precautions not present in %s", doc_name)

            # 3. Section 8 / 8.1: Pregnancy / Use in Specific Populations
            s8_blocks, s8_tables, s8_start, s8_end = self._extract_section_blocks_and_tables(
                pdf_path=target_path,
                start_section="8.1",
                stop_sections=["8.2", "9", "10"],
                start_keywords=["PREGNANCY"],
                stop_keywords=["LACTATION", "DRUG ABUSE", "OVERDOSAGE"],
            )
            if not s8_blocks:
                s8_blocks, s8_tables, s8_start, s8_end = self._extract_section_blocks_and_tables(
                    pdf_path=target_path,
                    start_section=SECTION_USE_IN_SPECIFIC_POPULATIONS,
                    stop_sections=["9", "10"],
                    start_keywords=["USE IN SPECIFIC POPULATIONS"],
                    stop_keywords=["DRUG ABUSE", "OVERDOSAGE"],
                )

            if s8_blocks:
                s8_text = self.format_blocks_to_text(s8_blocks)
                s8_page = f"{s8_start}-{s8_end}" if s8_start != s8_end else str(s8_start or "")
                s8_pages_list = sorted(list({b.page_num for b in s8_blocks}))
                preg_item = MedWatchSectionItem(
                    found=True,
                    status="SUCCESS",
                    content=s8_text,
                    section="8.1 PREGNANCY" if "PREGNANCY" in s8_text.upper() else "8. USE IN SPECIFIC POPULATIONS",
                    page=s8_page,
                    pages=s8_pages_list,
                    source_pdf=source_url_str,
                    document_date=document_date,
                    version=version,
                    tables=s8_tables,
                )
                logger.info("FDA_MEDWATCH_PREGNANCY_FOUND: Extracted %d chars (pages %s)", len(s8_text), s8_page)
            else:
                preg_item = MedWatchSectionItem(
                    found=False,
                    status=NOT_FOUND_IN_DOC_MSG,
                    content=NOT_FOUND_IN_DOC_MSG,
                    section="8.1 PREGNANCY",
                    source_pdf=source_url_str,
                    document_date=document_date,
                    version=version,
                )
                logger.info("FDA_MEDWATCH_SECTION_NOT_FOUND: Pregnancy / Use in Specific Populations not present in %s", doc_name)

            logger.info("FDA_MEDWATCH_PDF_EXTRACTION_COMPLETED: Extraction completed for %s", doc_name)
            return {
                "adverse_reactions": ar_item,
                "warnings_and_precautions": wp_item,
                "pregnancy": preg_item,
            }

        except Exception as exc:
            logger.error("FDA_MEDWATCH_ERROR: Exception during PDF extraction of %s: %s", doc_name, exc, exc_info=True)
            return self._build_empty_sections(status="PDF_EXTRACTION_FAILED")

        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass

    def _build_empty_sections(self, status: str = NOT_FOUND_IN_DOC_MSG) -> Dict[str, MedWatchSectionItem]:
        return {
            "adverse_reactions": MedWatchSectionItem(
                found=False,
                status=status,
                content=NOT_FOUND_IN_DOC_MSG,
                section="6. ADVERSE REACTIONS",
            ),
            "warnings_and_precautions": MedWatchSectionItem(
                found=False,
                status=status,
                content=NOT_FOUND_IN_DOC_MSG,
                section="5. WARNINGS AND PRECAUTIONS",
            ),
            "pregnancy": MedWatchSectionItem(
                found=False,
                status=status,
                content=NOT_FOUND_IN_DOC_MSG,
                section="8.1 PREGNANCY",
            ),
        }

