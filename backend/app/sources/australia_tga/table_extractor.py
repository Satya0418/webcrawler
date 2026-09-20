"""
Table extractor and preservation engine for Section 4.8 of Australia TGA Product Information.
Maintains headers, System Organ Classes, frequencies, multi-page continuation, and footnotes.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.sources.australia_tga.models import ExtractedTable

logger = logging.getLogger(__name__)

# Standard MedDRA System Organ Classes (SOCs) common in regulatory PI tables
MEDDRA_SOCS = [
    "blood and lymphatic system disorders",
    "cardiac disorders",
    "congenital, familial and genetic disorders",
    "ear and labyrinth disorders",
    "endocrine disorders",
    "eye disorders",
    "gastrointestinal disorders",
    "general disorders and administration site conditions",
    "hepatobiliary disorders",
    "immune system disorders",
    "infections and infestations",
    "injury, poisoning and procedural complications",
    "investigations",
    "metabolism and nutrition disorders",
    "musculoskeletal and connective tissue disorders",
    "neoplasms benign, malignant and unspecified",
    "nervous system disorders",
    "pregnancy, puerperium and perinatal conditions",
    "product issues",
    "psychiatric disorders",
    "renal and urinary disorders",
    "reproductive system and breast disorders",
    "respiratory, thoracic and mediastinal disorders",
    "skin and subcutaneous tissue disorders",
    "social circumstances",
    "surgical and medical procedures",
    "vascular disorders",
]


class TGATableExtractor:
    """
    Extracts, merges, and normalizes tabular data from Section 4.8 adverse reaction tables.
    Preserves original columns, multi-page table continuity, footnotes, and markdown formatting.
    """

    @classmethod
    def is_soc_row(cls, row: List[str]) -> bool:
        """
        Checks if a row is a System Organ Class (SOC) category header.
        In regulatory tables, SOC rows typically have text in the first cell and empty cells for data columns.
        """
        if not row:
            return False
        c0 = str(row[0] or "").strip().lower()
        c0_clean = re.sub(r"^\*+|\*+$", "", c0).strip()
        other_empty = all(str(c or "").strip() == "" for c in row[1:])

        if other_empty and c0_clean:
            if any(soc in c0_clean for soc in MEDDRA_SOCS):
                return True
            if any(w in c0_clean for w in ["disorders", "infections", "infestations", "complications", "investigations"]):
                return True
        return False

    @classmethod
    def clean_and_prune_table(
        cls, raw_cols: List[str], raw_rows: List[List[str]]
    ) -> tuple[List[str], List[List[str]]]:
        """
        Normalizes a table matrix:
        1. Filters out completely empty ghost columns produced by PDF cell spacing.
        2. Merges multi-line headers into clean, consolidated column headers.
        3. Identifies and separates header rows from actual data and SOC category rows.
        """
        if not raw_rows and not raw_cols:
            return [], []

        # Convert to grid of strings
        grid: List[List[str]] = []
        for r in raw_rows:
            grid.append([str(c or "").strip() for c in r])

        if not grid:
            return raw_cols, []

        max_cols = max(len(r) for r in grid)
        for r in grid:
            if len(r) < max_cols:
                r.extend([""] * (max_cols - len(r)))

        # Prune completely empty columns across all rows
        non_empty_cols = []
        for c_idx in range(max_cols):
            has_val = any(grid[r_idx][c_idx] != "" for r_idx in range(len(grid)))
            if has_val:
                non_empty_cols.append(c_idx)

        if not non_empty_cols:
            return [], []

        # If column 0 only had a single header word and column 1 has row labels:
        if len(non_empty_cols) >= 2 and 0 in non_empty_cols and 1 in non_empty_cols:
            col0_vals = [grid[r][0] for r in range(len(grid)) if grid[r][0]]
            col1_vals = [grid[r][1] for r in range(len(grid)) if grid[r][1]]
            if len(col0_vals) == 1 and grid[0][0] and not grid[0][1] and len(col1_vals) > 1:
                for r in range(len(grid)):
                    if r == 0:
                        grid[r][1] = grid[r][0]
                non_empty_cols.remove(0)

        pruned_grid: List[List[str]] = []
        for r in grid:
            pruned_grid.append([r[c] for c in non_empty_cols])

        # Row 0 is the primary header
        header_rows: List[List[str]] = [pruned_grid[0]]
        data_start_idx = 1

        # Check if subsequent rows are multi-line column subheaders (cell 0 is empty while other cells have text)
        for idx in range(1, min(len(pruned_grid), 3)):
            r = pruned_grid[idx]
            c0 = str(r[0] or "").strip()
            has_other_text = any(str(c or "").strip() for c in r[1:])
            if not c0 and has_other_text:
                header_rows.append(r)
                data_start_idx = idx + 1
            else:
                break

        cols: List[str] = []
        for c in range(len(header_rows[0])):
            col_parts = [header_rows[r][c] for r in range(len(header_rows)) if header_rows[r][c]]
            seen: List[str] = []
            for p in col_parts:
                if p not in seen:
                    seen.append(p)
            cols.append(" ".join(seen).strip())
        data_rows = pruned_grid[data_start_idx:]

        return cols, data_rows

    @classmethod
    def extract_and_format_tables(cls, extraction_result: Any) -> List[ExtractedTable]:
        """
        Processes an ExtractionResult (or dict) for Section 4.8 and returns a list of ExtractedTable objects.
        Merges continuation tables across consecutive pages.
        """
        if not extraction_result:
            return []

        raw_tables: List[Dict[str, Any]] = []

        # Check if extraction_result is an object (ExtractionResult) or dict
        structured_items = getattr(extraction_result, "structured_content", None)
        if structured_items is None and isinstance(extraction_result, dict):
            structured_items = extraction_result.get("structured_content", [])

        if structured_items:
            for item in structured_items:
                i_type = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)
                if i_type == "table":
                    page = getattr(item, "page", 0) or (item.get("page", 0) if isinstance(item, dict) else 0)
                    caption = getattr(item, "caption", "") or (item.get("caption", "") if isinstance(item, dict) else "")
                    cols = getattr(item, "columns", []) or (item.get("columns", []) if isinstance(item, dict) else [])
                    rows = getattr(item, "rows", []) or (item.get("rows", []) if isinstance(item, dict) else [])
                    raw_rows = getattr(item, "raw_rows", []) or (item.get("raw_rows", []) if isinstance(item, dict) else [])

                    # Skip single-column marginal artifacts (e.g. side headings detected as tables)
                    if len(cols) <= 1 and len(raw_rows) <= 3:
                        continue

                    cleaned_cols, cleaned_data_rows = cls.clean_and_prune_table(cols, raw_rows)
                    if not cleaned_cols or not cleaned_data_rows:
                        continue

                    raw_tables.append({
                        "page": page,
                        "end_page": page,
                        "caption": caption or f"Table on Page {page}",
                        "columns": cleaned_cols,
                        "rows": rows or [],
                        "raw_rows": cleaned_data_rows,
                        "original_header_cols": [str(c).strip() for c in cols if c is not None],
                    })

        # Fallback to blocks if structured_items had no tables
        if not raw_tables:
            blocks = getattr(extraction_result, "blocks", None)
            if blocks is None and isinstance(extraction_result, dict):
                blocks = extraction_result.get("blocks", [])

            for b in blocks or []:
                b_type = getattr(b, "block_type", "") or (b.get("block_type", "") if isinstance(b, dict) else "")
                if b_type == "table":
                    page = getattr(b, "page", 0) or (b.get("page", 0) if isinstance(b, dict) else 0)
                    cols = getattr(b, "table_columns", []) or (b.get("table_columns", []) if isinstance(b, dict) else [])
                    rows = getattr(b, "table_rows", []) or (b.get("table_rows", []) if isinstance(b, dict) else [])
                    raw_rows = getattr(b, "table_data", []) or (b.get("table_data", []) if isinstance(b, dict) else [])
                    md = getattr(b, "table_markdown", "") or (b.get("table_markdown", "") if isinstance(b, dict) else "")

                    if len(cols) <= 1 and len(raw_rows) <= 3:
                        continue

                    cleaned_cols, cleaned_data_rows = cls.clean_and_prune_table(cols, raw_rows)
                    if not cleaned_cols or not cleaned_data_rows:
                        continue

                    raw_tables.append({
                        "page": page,
                        "end_page": page,
                        "caption": f"Table on Page {page}",
                        "columns": cleaned_cols,
                        "rows": rows or [],
                        "raw_rows": cleaned_data_rows,
                        "original_header_cols": [str(c).strip() for c in cols if c is not None],
                        "markdown": md,
                    })

        if not raw_tables:
            return []

        # Merge continuation tables across pages
        merged_tables = cls._merge_continuation_tables(raw_tables)

        results: List[ExtractedTable] = []
        for t in merged_tables:
            cols = t.get("columns") or []
            r_rows = t.get("raw_rows") or []
            md = cls.format_markdown_table(cols, r_rows)
            footnotes = cls._extract_footnotes(r_rows)

            results.append(
                ExtractedTable(
                    caption=t.get("caption", "Adverse Reaction Table"),
                    page=t.get("page", 0),
                    columns=cols,
                    rows=t.get("rows", []),
                    raw_rows=r_rows,
                    markdown=md,
                    footnotes=footnotes,
                )
            )

        return results

    @classmethod
    def _merge_continuation_tables(cls, tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Detects tables that continue across consecutive pages and merges their data rows seamlessly.
        Preserves System Organ Class category rows if the continuation table started directly with an SOC row.
        """
        if len(tables) <= 1:
            return tables

        merged: List[Dict[str, Any]] = []
        current = tables[0]
        if "end_page" not in current:
            current["end_page"] = current.get("page", 0)

        for nxt in tables[1:]:
            curr_page = current.get("page", 0)
            curr_end_page = current.get("end_page", curr_page)
            nxt_page = nxt.get("page", 0)
            curr_cols = current.get("columns", [])
            nxt_cols = nxt.get("columns", [])

            is_consecutive_page = (nxt_page == curr_end_page + 1) or (nxt_page == curr_end_page)
            same_col_count = len(curr_cols) == len(nxt_cols) and len(curr_cols) > 0

            # Check if nxt starts with an SOC category row that was mistakenly identified as a header
            nxt_orig_cols = nxt.get("original_header_cols", [])
            starts_with_soc_header = False
            if nxt_orig_cols:
                soc_candidate = [nxt_orig_cols[0]] + [""] * (len(curr_cols) - 1)
                starts_with_soc_header = cls.is_soc_row(soc_candidate)

            has_similar_cols = (
                same_col_count
                and any(c.lower() in [nc.lower() for nc in nxt_cols] for c in curr_cols if c)
            )

            is_continuation = is_consecutive_page and (
                same_col_count
                or has_similar_cols
                or starts_with_soc_header
                or "continued" in nxt.get("caption", "").lower()
            )

            if is_continuation:
                logger.info("Merging continuation table across Page %d and Page %d", curr_end_page, nxt_page)
                nxt_raw = list(nxt.get("raw_rows", []))

                # If nxt started with an SOC that was stripped or placed in columns, restore it as a data row
                if starts_with_soc_header:
                    soc_row = [nxt_orig_cols[0]] + [""] * (len(curr_cols) - 1)
                    if not (nxt_raw and nxt_raw[0] == soc_row):
                        nxt_raw.insert(0, soc_row)

                # Filter out redundant repeated column headers or sub-headers in nxt
                filtered_nxt_rows = []
                for r in nxt_raw:
                    if r == curr_cols:
                        continue
                    if not starts_with_soc_header and r == nxt_cols:
                        continue
                    if all(c in " ".join(curr_cols) for c in r if c):
                        continue
                    filtered_nxt_rows.append(r)

                current["raw_rows"].extend(filtered_nxt_rows)
                current["rows"].extend(nxt.get("rows", []))
                current["end_page"] = nxt_page
                base_cap = current["caption"].split(" (")[0]
                current["caption"] = f"{base_cap} (continued on Page {nxt_page})"
            else:
                merged.append(current)
                current = nxt
                if "end_page" not in current:
                    current["end_page"] = current.get("page", 0)

        merged.append(current)
        return merged

    @classmethod
    def format_markdown_table(cls, columns: List[str], raw_rows: List[List[str]]) -> str:
        """Converts columns and row matrices into standard markdown table text."""
        if not columns and not raw_rows:
            return ""

        # Determine effective header and data
        if not columns and raw_rows:
            columns = raw_rows[0]
            data_rows = raw_rows[1:]
        elif columns and raw_rows:
            if raw_rows[0] == columns:
                data_rows = raw_rows[1:]
            else:
                data_rows = raw_rows
        else:
            data_rows = []

        if not columns:
            return ""

        header_line = "| " + " | ".join(str(c).replace("\n", " ").strip() for c in columns) + " |"
        sep_line = "| " + " | ".join("---" for _ in columns) + " |"

        lines = [header_line, sep_line]
        col_count = len(columns)

        for row in data_rows:
            cells = [str(c).replace("\n", " ").strip() for c in row]
            if len(cells) < col_count:
                cells.extend([""] * (col_count - len(cells)))
            elif len(cells) > col_count:
                cells = cells[:col_count]

            # If row is an SOC category header, format bold
            if cls.is_soc_row(cells):
                cells[0] = f"**{cells[0]}**"

            lines.append("| " + " | ".join(cells) + " |")

        return "\n".join(lines)

    @classmethod
    def integrate_merged_tables_into_text(
        cls, content: str, tables: List[ExtractedTable]
    ) -> str:
        """
        Replaces fragmented inline table blocks (`[Page X Table] ...`) in content with
        the unified, fully-merged, structured markdown tables.
        """
        if not content or not tables:
            return content

        # Identify all contiguous table blocks in content (including [Page X Table] headers)
        pattern = re.compile(
            r"(?:(?:\[Page\s+\d+\s+Table\]\s*\n)?\|[^\n]+\|\n?)+",
            re.MULTILINE,
        )

        matches = list(pattern.finditer(content))
        if not matches:
            # If no inline pipe tables were found in text, tables will be appended
            return content

        # Check if the matches form a sequence of table fragments
        first_start = matches[0].start()
        last_end = matches[-1].end()

        # Check if between the matches there are only blank lines or page headers
        intermediate_text = content[first_start:last_end]
        # Remove table lines and page markers to see if narrative exists
        stripped_intermediate = re.sub(
            r"(?:\[Page\s+\d+(?:\s+Table)?\]|\|[^\n]+\||\s+)", "", intermediate_text
        )

        if len(stripped_intermediate) < 60:
            # All matches are part of the table section! Replace the entire span with the merged tables
            merged_md = "\n\n".join(t.markdown for t in tables if t.markdown)
            new_content = content[:first_start].rstrip() + "\n\n" + merged_md + "\n\n" + content[last_end:].lstrip()
            return new_content.strip()

        # Otherwise replace the first matched block with merged markdown and remove subsequent fragments
        merged_md = "\n\n".join(t.markdown for t in tables if t.markdown)
        return pattern.sub(lambda m: merged_md if m.start() == first_start else "", content).strip()

    @classmethod
    def _extract_footnotes(cls, raw_rows: List[List[str]]) -> List[str]:
        """Detects footnote markers or notes (e.g. '* Indicates...', '† Post-marketing') in table rows."""
        footnotes: List[str] = []
        for row in raw_rows:
            for cell in row:
                cell_s = str(cell).strip()
                if re.match(r"^[\*\†\‡\§\1-9]\s+[A-Za-z]", cell_s) or cell_s.lower().startswith("note:"):
                    footnotes.append(cell_s)
        return footnotes
