import re
import json
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from backend.models.schemas import (
    ExtractionRequest,
    ExtractionResult,
    BlockTrace,
    StructuredContentItem,
    ValidationChecklist,
    BlockType,
    SectionSummary,
)
from backend.pdf.reader import PDFReader
from backend.pdf.parser import PDFParser
from backend.pdf.headings import HeadingDetector
from backend.pdf.tables import TableExtractor
from backend.pdf.sections import SectionTreeBuilder
from backend.extraction.boundary_detector import BoundaryDetector
from backend.extraction.validator import ExtractionValidator
from backend.database.db import SessionLocal
from backend.database.models import DocumentRecord, ExtractionRecord, ContentBlockRecord


class SectionExtractor:
    """
    Main extraction orchestrator that deterministically processes a PDF,
    identifies section hierarchy, extracts target subtrees, and produces structured objects.
    """

    NATURAL_QUERY_REGEX = re.compile(
        r"(?:section\s+)?(\d+(?:\.\d+)*)\s*(?:(?:to|and|->|→|\+|,)\s*(?:subsection\s+|section\s+)?(\d+(?:\.\d+)*))?",
        re.IGNORECASE
    )
    HTML_FORMAT_REGEX = re.compile(
        r"\b(?:html|htaml)\b",
        re.IGNORECASE
    )
    NEGLECT_TABLE_REGEX = re.compile(
        r"\b(?:neglect(?:ing)?\s+(?:the\s+)?tables?|no\s+tables?|without\s+tables?|text\s+only|only\s+text|strip\s+tables?|exclude\s+tables?|skip\s+tables?|omit\s+tables?|don'?t\s+want\s+tables?)\b",
        re.IGNORECASE
    )
    ADD_TABLE_REGEX = re.compile(
        r"\b(?:add(?:ing)?\s+(?:the\s+)?tables?|include\s+tables?|with\s+tables?|keep\s+tables?)\b",
        re.IGNORECASE
    )

    @classmethod
    def is_html_requested(
        cls,
        format_param: Optional[str] = None,
        response_format_param: Optional[str] = None,
        natural_query: Optional[str] = None
    ) -> bool:
        """Checks whether an HTML formatted response was requested via params or natural language query."""
        if isinstance(format_param, str) and format_param.strip().lower() in ("html", "htaml"):
            return True
        if isinstance(response_format_param, str) and response_format_param.strip().lower() in ("html", "htaml"):
            return True
        if isinstance(natural_query, str) and cls.HTML_FORMAT_REGEX.search(natural_query):
            return True
        return False

    @classmethod
    def parse_query_params(
        cls,
        main_section: Optional[str] = None,
        target_subsection: Optional[str] = None,
        natural_query: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """Parses structured or natural language queries into canonical main and sub numbers."""
        if natural_query and not (main_section and target_subsection):
            m = cls.NATURAL_QUERY_REGEX.search(natural_query)
            if m:
                main_val, sub_val = m.groups()
                main_section = main_val.strip() if main_val else main_section
                target_subsection = sub_val.strip() if sub_val else target_subsection

        main_sec = (main_section or "16").strip().strip(".:-")
        target_sub = target_subsection.strip().strip(".:-") if target_subsection else None
        return main_sec, target_sub

    def extract(
        self,
        file_path_or_bytes: Any,
        main_section: str = "16",
        target_subsection: Optional[str] = "16.1",
        natural_query: Optional[str] = None,
        doc_name: str = "document.pdf",
        save_to_db: bool = True,
        include_tables: bool = True,
        table_mode: str = "add",
        section_table_mode: Optional[Dict[str, str]] = None
    ) -> ExtractionResult:
        """Executes full structured extraction pipeline on a PDF."""
        main_sec, target_sub = self.parse_query_params(
            main_section, target_subsection, natural_query
        )
        if (doc_name == "document.pdf" or not doc_name) and isinstance(file_path_or_bytes, (str, Path)):
            doc_name = Path(file_path_or_bytes).name

        # Resolve effective table mode: "add" or "neglect"
        effective_table_mode = (table_mode or "add").lower().strip()
        if not include_tables or effective_table_mode in ("neglect", "exclude", "text_only", "false", "0"):
            effective_table_mode = "neglect"
            include_tables = False
        else:
            effective_table_mode = "add"
            include_tables = True

        if natural_query:
            if self.NEGLECT_TABLE_REGEX.search(natural_query):
                effective_table_mode = "neglect"
                include_tables = False
            elif self.ADD_TABLE_REGEX.search(natural_query):
                effective_table_mode = "add"
                include_tables = True

        try:
            # 1. Open and validate PDF
            with PDFReader(file_path_or_bytes) as reader:
                doc = reader.doc
                page_count = reader.page_count
                toc_bookmarks = reader.toc_bookmarks
                is_scanned, avg_chars = reader.is_scanned()

                # 2. Parse text blocks and typography
                parser = PDFParser(doc)
                raw_blocks = parser.parse()
                body_font_size = parser.body_font_size

                # 3. Detect headings across blocks first
                heading_detector = HeadingDetector(
                    body_font_size=body_font_size,
                    toc_bookmarks=toc_bookmarks
                )
                processed_blocks = heading_detector.process_blocks(raw_blocks)

                # 4. Preliminary check for candidate section pages to optimize table extraction
                candidate_pages = set()
                for b in processed_blocks:
                    if b.is_heading and b.section_number:
                        if b.section_number == main_sec or (
                            target_sub and b.section_number.startswith(target_sub)
                        ):
                            candidate_pages.add(b.page_num)
                            # Also include next 2-3 pages in case table/content spans across
                            candidate_pages.add(b.page_num + 1)
                            candidate_pages.add(b.page_num + 2)

                # Extract tables (target candidate pages if known, or all if document <= 35 pages)
                table_extractor = TableExtractor(file_path_or_bytes)
                if page_count > 35 and candidate_pages:
                    table_blocks = table_extractor.extract_tables(target_pages=candidate_pages)
                else:
                    table_blocks = table_extractor.extract_tables()

                # 5. Merge tables into blocks without duplicating table cell text
                merged_blocks = TableExtractor.merge_tables_with_blocks(
                    processed_blocks, table_blocks
                )

                # 6. Build section tree
                root_nodes, node_index = SectionTreeBuilder.build_tree(merged_blocks)
                all_discovered_sections = sorted(list(node_index.keys()))

                # 7. Detect stop boundary
                stop_section_num = BoundaryDetector.find_stop_section_number(
                    main_sec, target_sub, root_nodes, node_index
                )

                # 8. Extract blocks within boundary
                (
                    extracted_blocks,
                    included_sections,
                    excluded_sections,
                ) = BoundaryDetector.extract_blocks_within_boundary(
                    merged_blocks, main_sec, target_sub, stop_section_num
                )

                # 9. Run validation
                validation = ExtractionValidator.validate(
                    extracted_blocks,
                    main_sec,
                    target_sub,
                    stop_section_num,
                    all_discovered_sections,
                )

                # 10. Construct structured content items and block traces
                structured_items: List[StructuredContentItem] = []
                block_traces: List[BlockTrace] = []
                content_parts: List[str] = []

                total_detected_tables = sum(1 for b in extracted_blocks if b.block_type == BlockType.TABLE)
                section_table_status: Dict[str, str] = {}
                tables_neglected_count = 0
                tables_included_count = 0

                for b in extracted_blocks:
                    # Determine whether table block should be neglected
                    if b.block_type == BlockType.TABLE:
                        sec_key = b.section_number or main_sec
                        sec_override = (section_table_mode or {}).get(sec_key)
                        is_neglected = False
                        if sec_override:
                            is_neglected = (sec_override.lower().strip() in ("neglect", "exclude", "text_only", "false", "0"))
                        else:
                            is_neglected = (effective_table_mode == "neglect")

                        if is_neglected:
                            tables_neglected_count += 1
                            section_table_status[sec_key] = "neglected"
                            continue  # Completely neglect this table! Omit from structured items, traces, and text content
                        else:
                            tables_included_count += 1
                            section_table_status[sec_key] = "included"

                    # Build BlockTrace
                    trace = BlockTrace(
                        id=b.block_id,
                        page=b.page_num,
                        section=b.section_number,
                        block_type=b.block_type.value,
                        text=b.text,
                        bbox=list(b.bbox),
                        bullet_items=b.bullet_items,
                        table_columns=b.table_columns,
                        table_rows=b.table_rows,
                        table_data=b.table_data,
                        table_markdown=b.table_markdown,
                    )
                    block_traces.append(trace)

                    # Build StructuredContentItem
                    if b.block_type == BlockType.HEADING:
                        title_clean = b.text
                        if b.section_number and title_clean.startswith(b.section_number):
                            title_clean = title_clean[len(b.section_number):].strip(" .:-\t")

                        item = StructuredContentItem(
                            type="heading",
                            page=b.page_num,
                            bbox=list(b.bbox),
                            section_number=b.section_number,
                            title=title_clean,
                            level=b.heading_level or 1,
                            text=b.text,
                        )
                        structured_items.append(item)
                        content_parts.append(f"\n[Page {b.page_num}] {b.text}\n")

                    elif b.block_type == BlockType.TABLE:
                        item = StructuredContentItem(
                            type="table",
                            page=b.page_num,
                            bbox=list(b.bbox),
                            section_number=b.section_number,
                            table_id=b.block_id,
                            caption=f"Table on Page {b.page_num}",
                            columns=b.table_columns or (b.table_data[0] if b.table_data else []),
                            rows=b.table_rows or [],
                            raw_rows=b.table_data or [],
                        )
                        structured_items.append(item)
                        content_parts.append(f"\n[Page {b.page_num} Table]\n{b.text}\n")

                    elif b.block_type in (BlockType.BULLET_LIST, BlockType.NUMBERED_LIST):
                        item = StructuredContentItem(
                            type=b.block_type.value,
                            page=b.page_num,
                            bbox=list(b.bbox),
                            section_number=b.section_number,
                            items=b.bullet_items or [b.text],
                        )
                        structured_items.append(item)
                        if b.bullet_items:
                            bullet_str = "\n".join(f"• {it}" for it in b.bullet_items)
                            content_parts.append(bullet_str)
                        else:
                            content_parts.append(b.text)

                    else:
                        item = StructuredContentItem(
                            type="paragraph",
                            page=b.page_num,
                            bbox=list(b.bbox),
                            section_number=b.section_number,
                            text=b.text,
                        )
                        structured_items.append(item)
                        content_parts.append(b.text)

                combined_content = "\n".join(content_parts).strip()
                subsections_found = [s for s in included_sections if s != main_sec]
                tree_summaries = [r.to_summary() for r in root_nodes]

                # Update table counts in validation
                validation.tables_included_count = tables_included_count
                validation.tables_detected_count = total_detected_tables
                validation.tables_neglected_count = tables_neglected_count
                validation.table_mode = effective_table_mode

                status = "success" if validation.was_main_section_found else "not_found"
                err_msg = None
                if not validation.was_main_section_found:
                    err_msg = f"Section {main_sec} was not found in {doc_name}."

                res = ExtractionResult(
                    document=doc_name,
                    requested_section=main_sec,
                    requested_subsection=target_sub,
                    start_page=validation.start_page,
                    end_page=validation.end_page,
                    subsections_found=subsections_found,
                    content=combined_content,
                    structured_content=structured_items,
                    blocks=block_traces,
                    validation=validation,
                    table_mode=effective_table_mode,
                    tables_detected=total_detected_tables,
                    tables_neglected=tables_neglected_count,
                    section_table_status=section_table_status,
                    status=status,
                    error_message=err_msg,
                    section_tree=tree_summaries,
                    metadata={
                        "total_pages": page_count,
                        "is_scanned": is_scanned,
                        "avg_chars_per_page": round(avg_chars, 1),
                        "stop_boundary_section": stop_section_num,
                        "table_mode": effective_table_mode,
                        "tables_detected": total_detected_tables,
                        "tables_neglected": tables_neglected_count,
                        "section_table_status": section_table_status,
                    },
                )

                # 11. Optionally persist to SQLite database
                if save_to_db and isinstance(file_path_or_bytes, (str, Path)):
                    try:
                        self._persist_to_db(res, Path(file_path_or_bytes), page_count)
                    except Exception as db_err:
                        res.metadata["db_error"] = str(db_err)

                # Generate formatted HTML data representation
                try:
                    from backend.services.export_service import ExportService
                    res.Data = ExportService.generate_html_content(res)
                except Exception:
                    pass

                return res

        except Exception as e:
            err_res = ExtractionResult(
                document=doc_name,
                requested_section=main_sec,
                requested_subsection=target_sub,
                start_page=0,
                end_page=0,
                subsections_found=[],
                content="",
                structured_content=[],
                blocks=[],
                validation=ValidationChecklist(
                    status_message=f"Error during extraction: {str(e)}",
                    warnings=[str(e)],
                    confidence_score=0.0
                ),
                status="error",
                error_message=str(e),
                metadata={},
            )
            try:
                from backend.services.export_service import ExportService
                err_res.Data = ExportService.generate_html_content(err_res)
            except Exception:
                pass
            return err_res

    @staticmethod
    def _persist_to_db(res: ExtractionResult, file_path: Path, total_pages: int):
        """Persists document and extraction run to SQLite database."""
        db = SessionLocal()
        try:
            # Find or create DocumentRecord
            doc_rec = db.query(DocumentRecord).filter_by(file_path=str(file_path)).first()
            if not doc_rec:
                doc_rec = DocumentRecord(
                    id=uuid.uuid4().hex,
                    filename=file_path.name,
                    file_path=str(file_path),
                    total_pages=total_pages,
                )
                db.add(doc_rec)
                db.flush()

            ext_rec = ExtractionRecord(
                id=uuid.uuid4().hex,
                document_id=doc_rec.id,
                main_section=res.requested_section,
                target_subsection=res.requested_subsection,
                start_page=res.start_page,
                end_page=res.end_page,
                status=res.status,
                confidence_score=res.validation.confidence_score,
                included_sections=json.dumps(res.validation.included_sections),
                excluded_sections=json.dumps(res.validation.excluded_sections),
            )
            db.add(ext_rec)
            db.flush()

            for order_idx, item in enumerate(res.structured_content):
                blk_rec = ContentBlockRecord(
                    id=uuid.uuid4().hex,
                    extraction_id=ext_rec.id,
                    block_type=item.type,
                    page_num=item.page,
                    section_number=item.section_number,
                    reading_order=order_idx,
                    text=item.text or (item.title if item.type == 'heading' else None),
                    bbox_json=json.dumps(item.bbox) if item.bbox else None,
                    content_json=json.dumps(item.model_dump(), default=str),
                )
                db.add(blk_rec)

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
