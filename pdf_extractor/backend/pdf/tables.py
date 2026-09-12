import pdfplumber
import fitz
from typing import List, Dict, Any, Tuple, Optional, Set
from pathlib import Path
from backend.models.schemas import DocumentBlock, BlockType


class TableExtractor:
    """
    Detects and extracts tables from PDF pages using pdfplumber and/or PyMuPDF,
    formatting them into structured tabular data, row dictionaries, and markdown strings.
    """

    def __init__(self, pdf_source: Any):
        self.source = pdf_source

    @staticmethod
    def _clean_cell(cell: Any) -> str:
        """Cleans and normalizes cell content, safely handling None."""
        if cell is None:
            return ""
        return str(cell).replace("\n", " ").strip()

    def _format_markdown_table(self, rows: List[List[str]]) -> str:
        """Converts cleaned rows into a clean markdown table string."""
        if not rows or not rows[0]:
            return ""

        col_count = max(len(row) for row in rows)
        normalized = [row + [""] * (col_count - len(row)) for row in rows]

        header = normalized[0]
        separator = ["---"] * col_count
        data_rows = normalized[1:] if len(normalized) > 1 else []

        md_lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(separator) + " |",
        ]
        for row in data_rows:
            md_lines.append("| " + " | ".join(row) + " |")

        return "\n".join(md_lines)

    def extract_tables(self, target_pages: Optional[Set[int]] = None) -> List[DocumentBlock]:
        """
        Extracts tables from the PDF (optionally restricted to target_pages).
        Returns them as DocumentBlocks with BlockType.TABLE and structured column/row data.
        """
        table_blocks: List[DocumentBlock] = []

        try:
            with pdfplumber.open(self.source) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    page_num = page_idx + 1

                    # If target_pages specified, skip pages outside range
                    if target_pages and page_num not in target_pages:
                        continue

                    try:
                        extracted = page.find_tables()
                    except Exception:
                        continue

                    for t_idx, table_obj in enumerate(extracted):
                        try:
                            raw_data = table_obj.extract()
                            if not raw_data or len(raw_data) == 0:
                                continue

                            # Normalize all cells (clean None -> "")
                            cleaned_rows: List[List[str]] = [
                                [self._clean_cell(cell) for cell in row]
                                for row in raw_data
                            ]

                            # Ensure at least 2 non-empty cells
                            non_empty_cells = sum(
                                1 for row in cleaned_rows for cell in row if cell
                            )
                            if non_empty_cells < 2:
                                continue

                            # Align row lengths
                            col_count = max(len(row) for row in cleaned_rows)
                            aligned_rows = [
                                row + [""] * (col_count - len(row)) for row in cleaned_rows
                            ]

                            # Determine columns
                            raw_header = aligned_rows[0]
                            columns = []
                            for c_i, h in enumerate(raw_header):
                                col_name = h.strip() if h.strip() else f"Column_{c_i + 1}"
                                # Ensure unique column names for dict mapping
                                if col_name in columns:
                                    col_name = f"{col_name}_{c_i + 1}"
                                columns.append(col_name)

                            # Build structured row dictionaries
                            table_rows = []
                            data_rows = aligned_rows[1:] if len(aligned_rows) > 1 else []
                            for r in data_rows:
                                row_dict = {}
                                for c_i, val in enumerate(r):
                                    col_key = columns[c_i] if c_i < len(columns) else f"Column_{c_i + 1}"
                                    row_dict[col_key] = val
                                table_rows.append(row_dict)

                            bbox = table_obj.bbox  # (x0, top, x1, bottom)
                            md = self._format_markdown_table(aligned_rows)
                            block_id = f"p{page_num}_table_{t_idx}"

                            t_block = DocumentBlock(
                                block_id=block_id,
                                page_num=page_num,
                                bbox=bbox,
                                block_type=BlockType.TABLE,
                                text=md,
                                table_data=aligned_rows,
                                table_columns=columns,
                                table_rows=table_rows,
                                table_markdown=md,
                            )
                            table_blocks.append(t_block)
                        except Exception:
                            continue

        except Exception:
            # Fallback to PyMuPDF table finder
            try:
                doc = fitz.open(self.source)
                for page_idx in range(len(doc)):
                    page_num = page_idx + 1
                    if target_pages and page_num not in target_pages:
                        continue
                    page = doc[page_idx]
                    try:
                        tabs = page.find_tables()
                        for t_idx, tab in enumerate(tabs):
                            raw_data = tab.extract()
                            if not raw_data:
                                continue
                            cleaned_rows = [
                                [self._clean_cell(cell) for cell in row]
                                for row in raw_data
                            ]
                            col_count = max(len(row) for row in cleaned_rows)
                            aligned_rows = [
                                row + [""] * (col_count - len(row)) for row in cleaned_rows
                            ]
                            columns = [
                                h.strip() if h.strip() else f"Column_{i + 1}"
                                for i, h in enumerate(aligned_rows[0])
                            ]
                            table_rows = [
                                {columns[i]: cell for i, cell in enumerate(r)}
                                for r in aligned_rows[1:]
                            ]
                            md = self._format_markdown_table(aligned_rows)
                            t_block = DocumentBlock(
                                block_id=f"p{page_num}_table_{t_idx}",
                                page_num=page_num,
                                bbox=tab.bbox,
                                block_type=BlockType.TABLE,
                                text=md,
                                table_data=aligned_rows,
                                table_columns=columns,
                                table_rows=table_rows,
                                table_markdown=md,
                            )
                            table_blocks.append(t_block)
                    except Exception:
                        continue
                doc.close()
            except Exception:
                pass

        return table_blocks

    @staticmethod
    def merge_tables_with_blocks(
        text_blocks: List[DocumentBlock],
        table_blocks: List[DocumentBlock],
        include_tables: bool = True
    ) -> List[DocumentBlock]:
        """
        Merges table blocks into the document block list and filters out text blocks
        that fall inside a table's bounding box.
        If include_tables is False, table blocks are omitted from the combined list.
        """
        if not table_blocks:
            return text_blocks

        # Build index of table bboxes per page
        page_tables: Dict[int, List[DocumentBlock]] = {}
        for tb in table_blocks:
            page_tables.setdefault(tb.page_num, []).append(tb)

        filtered_text_blocks: List[DocumentBlock] = []

        for b in text_blocks:
            # Never filter out section headings
            if b.is_heading:
                filtered_text_blocks.append(b)
                continue

            # Check if block is inside any table bounding box on the same page
            is_inside_table = False
            bx0, by0, bx1, by1 = b.bbox
            b_area = max(1.0, (bx1 - bx0) * (by1 - by0))
            cx = (bx0 + bx1) / 2
            cy = (by0 + by1) / 2

            for tb in page_tables.get(b.page_num, []):
                tx0, ty0, tx1, ty1 = tb.bbox

                # Check 1: Center of text block is inside table bounds (with margin)
                if (tx0 - 5) <= cx <= (tx1 + 5) and (ty0 - 5) <= cy <= (ty1 + 5):
                    is_inside_table = True
                    break

                # Check 2: Significant bounding box overlap area (>35% of text block)
                inter_x0 = max(bx0, tx0)
                inter_y0 = max(by0, ty0)
                inter_x1 = min(bx1, tx1)
                inter_y1 = min(by1, ty1)
                if inter_x1 > inter_x0 and inter_y1 > inter_y0:
                    inter_area = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
                    if (inter_area / b_area) > 0.35:
                        is_inside_table = True
                        break

            if not is_inside_table:
                filtered_text_blocks.append(b)

        # Combine and sort by reading order: page, y0, x0
        if include_tables:
            all_blocks = filtered_text_blocks + table_blocks
        else:
            all_blocks = filtered_text_blocks

        all_blocks.sort(key=lambda x: (x.page_num, round(x.bbox[1], 1), round(x.bbox[0], 1)))
        return all_blocks
