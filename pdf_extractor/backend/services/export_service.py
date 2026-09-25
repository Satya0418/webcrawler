import re
import json
import csv
import html
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from backend.models.schemas import ExtractionResult, BatchExtractionResponse
from backend.config import OUTPUT_DIR


class ExportService:
    """Provides exports in HTML, JSON, TXT, CSV, and Excel formats."""

    @staticmethod
    def _clean_section_heading(text: str) -> str:
        """
        Strips leading section numbers (e.g. '16', '16.1', 'Section 16.1:', 'Table 16.1:', '16 Safety Information')
        from headings, titles, and captions so section numbers are not displayed in the HTML output.
        """
        if not text:
            return ""
        cleaned = re.sub(
            r'^(?:(?:section|table)\s+)?\(?\d+(?:\.\d+)*\)?(?:\s*[:\-\.\)]+)*\s*',
            '',
            text.strip(),
            flags=re.IGNORECASE
        )
        return cleaned.strip()

    @classmethod
    def generate_html_content(cls, result: ExtractionResult, title: Optional[str] = None) -> str:
        """
        Generates clean, semantic, browser-renderable HTML according to strict rules:
        - Centralized CSS in <head><style>
        - Consecutive bullet items grouped into single <ul> containing multiple <li> elements
        - Consecutive numbered items grouped into single <ol> containing multiple <li> elements
        - Headings rendered semantically (<h2>, <h3>)
        - Paragraphs rendered as <p> preserving exact text
        - Tables rendered with <table>, <thead>, <tbody> only when real tables exist in extracted content
        - Table CSS included ONLY if <table> exists in generated HTML
        - Clean indentation and readability (not single-line minified)
        - Exact text preservation without alterations
        """
        if title:
            clean_t = cls._clean_section_heading(title)
            page_title = clean_t or "Extracted Document"
        elif result.document and result.document != "document.pdf":
            stem = Path(result.document).stem.replace("_", " ").title()
            clean_stem = cls._clean_section_heading(stem)
            page_title = clean_stem or "Extracted Document"
        else:
            page_title = "Extracted Document"

        is_neglect_mode = getattr(result, "table_mode", "add") == "neglect"
        structured_items = result.structured_content or []

        # Check if actual tables should be rendered
        table_items = [it for it in structured_items if it.type == "table"]
        has_table = bool(table_items) and not is_neglect_mode

        body_elements: List[str] = []

        # Iterate through structured items and group consecutive list items
        i = 0
        n = len(structured_items)

        while i < n:
            item = structured_items[i]

            if item.type == "heading":
                raw_h = item.title or item.text or ""
                h_text = cls._clean_section_heading(raw_h)
                if h_text:
                    tag = "h2" if (item.level is None or item.level <= 2) else "h3"
                    body_elements.append(f"<{tag}>{html.escape(h_text)}</{tag}>")
                i += 1

            elif item.type in ("bullet_list", "numbered_list"):
                list_type = item.type
                accumulated_items: List[str] = []

                # Group consecutive list items of the same type
                while i < n and structured_items[i].type == list_type:
                    curr = structured_items[i]
                    if curr.items:
                        accumulated_items.extend(curr.items)
                    elif curr.text:
                        accumulated_items.append(curr.text)
                    i += 1

                tag = "ul" if list_type == "bullet_list" else "ol"
                li_elements = "\n".join(f"    <li>{html.escape(str(it))}</li>" for it in accumulated_items if str(it).strip())
                if li_elements:
                    body_elements.append(f"<{tag}>\n{li_elements}\n</{tag}>")

            elif item.type == "table":
                if not is_neglect_mode:
                    caption = ""
                    if item.caption:
                        caption = cls._clean_section_heading(item.caption)

                    cols = item.columns or []
                    th_cells = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
                    thead = f"    <thead>\n        <tr>{th_cells}</tr>\n    </thead>" if th_cells else ""

                    rows_html = []
                    if item.rows:
                        for row_dict in item.rows:
                            td_cells = "".join(f"<td>{html.escape(str(row_dict.get(c, '')))}</td>" for c in cols)
                            rows_html.append(f"        <tr>{td_cells}</tr>")
                    elif item.raw_rows:
                        # Skip header row if it matches cols
                        start_idx = 1 if (len(item.raw_rows) > 1 and item.raw_rows[0] == cols) else 0
                        for r_list in item.raw_rows[start_idx:]:
                            td_cells = "".join(f"<td>{html.escape(str(val))}</td>" for val in r_list)
                            rows_html.append(f"        <tr>{td_cells}</tr>")

                    tbody = f"    <tbody>\n" + "\n".join(rows_html) + "\n    </tbody>" if rows_html else "    <tbody></tbody>"
                    table_str = f"<table>\n{thead}\n{tbody}\n</table>"
                    if caption:
                        body_elements.append(f"<h2>{html.escape(caption)}</h2>\n{table_str}")
                    else:
                        body_elements.append(table_str)
                i += 1

            else:
                # Paragraph or other content
                p_text = html.escape(item.text or "").replace("\n", "<br>\n    ")
                if p_text.strip():
                    body_elements.append(f"<p>\n    {p_text}\n</p>")
                i += 1

        # Fallback if no structured items found but raw content exists
        if not body_elements and result.content:
            p_text = html.escape(result.content).replace("\n", "<br>\n    ")
            body_elements.append(f"<p>\n    {p_text}\n</p>")

        # Construct centralized CSS - only include table rules if a table is actually present
        css_rules = [
            "body { font-family: Arial, sans-serif; margin: 40px; background-color: #f9f9f9; }",
            "h2, h3 { color: #333; }",
            "p { margin: 12px 0; color: #333; line-height: 1.6; }",
            "ul, ol { margin: 10px 0 10px 24px; color: #333; }",
            "li { margin-bottom: 4px; }",
        ]

        if has_table:
            css_rules.extend([
                "table { width: 100%; border-collapse: collapse; margin-top: 20px; background-color: #ffffff; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }",
                "th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #ddd; }",
                "th { background-color: #007BFF; color: white; font-weight: bold; }",
                "tr:hover { background-color: #f5f5f5; }",
            ])

        formatted_css = "\n    ".join(css_rules)
        inner_body = "\n\n".join(body_elements)
        # Indent inner body nicely
        indented_body = "\n".join("    " + line if line.strip() else "" for line in inner_body.splitlines())

        html_content = (
            f"<!DOCTYPE html>\n"
            f'<html lang="en">\n'
            f"<head>\n"
            f'    <meta charset="UTF-8">\n'
            f'    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f"    <title>{html.escape(page_title)}</title>\n"
            f"    <style>\n"
            f"    {formatted_css}\n"
            f"    </style>\n"
            f"</head>\n"
            f"<body>\n"
            f"{indented_body}\n"
            f"</body>\n"
            f"</html>"
        )
        return html_content

    @classmethod
    def generate_structured_html(
        cls,
        result: ExtractionResult,
        product_name: Optional[str] = None,
        target_subsection: Optional[str] = None,
        standalone: bool = True,
    ) -> str:
        """
        Generates production-grade, highly structured semantic HTML5.
        Organizes content into <section>, <article class="med-subsection">,
        <div class="table-responsive">, and scoped CSS classes.
        
        Args:
            result: ExtractionResult object
            product_name: Optional brand or product display name
            target_subsection: If set (e.g. '16.1'), filters strictly to that subsection
            standalone: If True, wraps in full <!DOCTYPE html> with scoped stylesheet.
                        If False, returns embeddable <section> snippet for client websites.
        """
        p_name = product_name or Path(result.document).stem.replace("_", " ").title()
        
        # Filter blocks if specific subsection requested
        all_blocks = result.blocks or []
        if target_subsection:
            sub_prefix = f"{target_subsection}."
            blocks = [b for b in all_blocks if b.section == target_subsection or (b.section and b.section.startswith(sub_prefix))]
            display_title = f"{p_name} - Section {target_subsection}"
        else:
            blocks = all_blocks
            display_title = f"{p_name} - Section {result.requested_section}"

        # Group blocks by section
        grouped: Dict[str, List] = {}
        order: List[str] = []
        for b in blocks:
            sec_num = b.section or result.requested_section
            if sec_num not in grouped:
                grouped[sec_num] = []
                order.append(sec_num)
            grouped[sec_num].append(b)

        # Helper to render a group of blocks
        def render_block_group(sec_blocks: List) -> Tuple[str, str]:
            group_title = ""
            elements: List[str] = []
            k = 0
            m = len(sec_blocks)
            while k < m:
                blk = sec_blocks[k]
                btype = getattr(blk, "block_type", "paragraph")
                
                if btype == "heading":
                    if not group_title:
                        group_title = blk.text
                    else:
                        elements.append(f'<h4 class="med-subheading">{html.escape(blk.text)}</h4>')
                    k += 1

                elif btype in ("bullet_list", "numbered_list"):
                    l_type = btype
                    accum_items = []
                    while k < m and getattr(sec_blocks[k], "block_type", "") == l_type:
                        c_blk = sec_blocks[k]
                        if getattr(c_blk, "bullet_items", None):
                            accum_items.extend(c_blk.bullet_items)
                        elif c_blk.text:
                            accum_items.append(c_blk.text)
                        k += 1
                    tag = "ul" if l_type == "bullet_list" else "ol"
                    items_str = "\n".join(f'        <li>{html.escape(it)}</li>' for it in accum_items if it.strip())
                    if items_str:
                        elements.append(f'    <{tag} class="med-list">\n{items_str}\n    </{tag}>')

                elif btype == "table":
                    cols = getattr(blk, "table_columns", None) or []
                    rows = getattr(blk, "table_rows", None) or []
                    th_html = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
                    thead_html = f"            <thead>\n                <tr>{th_html}</tr>\n            </thead>\n" if th_html else ""
                    
                    tr_html_list = []
                    for r_dict in rows:
                        td_html = "".join(f"<td>{html.escape(str(r_dict.get(c, '')))}</td>" for c in cols)
                        tr_html_list.append(f"                <tr>{td_html}</tr>")
                    tbody_html = "            <tbody>\n" + "\n".join(tr_html_list) + "\n            </tbody>" if tr_html_list else "            <tbody></tbody>"
                    
                    table_html = (
                        f'    <div class="table-responsive">\n'
                        f'        <table class="med-table">\n'
                        f'{thead_html}'
                        f'{tbody_html}\n'
                        f'        </table>\n'
                        f'    </div>'
                    )
                    elements.append(table_html)
                    k += 1

                else:
                    # Paragraph
                    p_txt = html.escape(blk.text or "").replace("\n", "<br>\n        ")
                    if p_txt.strip():
                        elements.append(f'    <p class="med-paragraph">\n        {p_txt}\n    </p>')
                    k += 1

            return group_title, "\n".join(elements)

        # Assemble the semantic HTML hierarchy
        main_sec_num = result.requested_section
        html_cards: List[str] = []

        # If full section requested, render root section intro first
        if not target_subsection and main_sec_num in grouped:
            root_title, root_content = render_block_group(grouped[main_sec_num])
            root_display = root_title or f"Section {main_sec_num}"
            if root_content.strip():
                html_cards.append(
                    f'    <div class="med-root-content">\n'
                    f'{root_content}\n'
                    f'    </div>'
                )

        # Render subsections as distinct semantic <article> cards
        for sec_num in order:
            if not target_subsection and sec_num == main_sec_num:
                continue  # Already rendered as root
            sub_title, sub_content = render_block_group(grouped[sec_num])
            sub_header = sub_title or f"Section {sec_num}"
            safe_id = f"sec-{sec_num.replace('.', '-')}"
            card_html = (
                f'    <article class="med-subsection-card" id="{safe_id}" data-subsection="{sec_num}">\n'
                f'        <header class="med-sub-header">\n'
                f'            <span class="med-badge">Section {sec_num}</span>\n'
                f'            <h3 class="med-subsection-title">{html.escape(sub_header)}</h3>\n'
                f'        </header>\n'
                f'        <div class="med-sub-body">\n'
                f'{sub_content}\n'
                f'        </div>\n'
                f'    </article>'
            )
            html_cards.append(card_html)

        body_inner = "\n\n".join(html_cards)
        if not body_inner.strip() and result.content:
            body_inner = f'    <p class="med-paragraph">{html.escape(result.content)}</p>'

        container_html = (
            f'<section class="med-section-container" id="med-sec-{main_sec_num}">\n'
            f'    <header class="med-main-header">\n'
            f'        <div class="med-brand-tag">{html.escape(p_name)}</div>\n'
            f'        <h2 class="med-section-main-title">{html.escape(display_title)}</h2>\n'
            f'    </header>\n'
            f'    <div class="med-section-content">\n'
            f'{body_inner}\n'
            f'    </div>\n'
            f'</section>'
        )

        if not standalone:
            return container_html

        # CSS Stylesheet for standalone viewing
        css_style = """
        :root {
            --med-primary: #0284c7;
            --med-primary-dark: #0369a1;
            --med-primary-light: #e0f2fe;
            --med-text-main: #1e293b;
            --med-text-muted: #64748b;
            --med-bg-page: #f8fafc;
            --med-bg-card: #ffffff;
            --med-border: #e2e8f0;
            --med-radius: 8px;
            --med-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
        }
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 32px 16px;
            background-color: var(--med-bg-page);
            color: var(--med-text-main);
            line-height: 1.6;
        }
        .med-section-container {
            max-width: 920px;
            margin: 0 auto;
            background: var(--med-bg-card);
            border-radius: var(--med-radius);
            box-shadow: var(--med-shadow);
            border: 1px solid var(--med-border);
            padding: 32px;
        }
        .med-main-header {
            border-bottom: 2px solid var(--med-primary);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }
        .med-brand-tag {
            display: inline-block;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            background: var(--med-primary-light);
            color: var(--med-primary-dark);
            padding: 3px 10px;
            border-radius: 9999px;
            margin-bottom: 8px;
        }
        .med-section-main-title {
            margin: 0;
            font-size: 22px;
            font-weight: 700;
            color: #0f172a;
        }
        .med-subsection-card {
            background: #ffffff;
            border: 1px solid var(--med-border);
            border-radius: var(--med-radius);
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        }
        .med-sub-header {
            display: flex;
            align-items: center;
            gap: 10px;
            border-bottom: 1px solid var(--med-border);
            padding-bottom: 10px;
            margin-bottom: 14px;
        }
        .med-badge {
            background: #f1f5f9;
            color: #475569;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 4px;
            border: 1px solid #cbd5e1;
        }
        .med-subsection-title {
            margin: 0;
            font-size: 17px;
            font-weight: 600;
            color: var(--med-primary-dark);
        }
        .med-subheading {
            font-size: 15px;
            font-weight: 600;
            color: #334155;
            margin: 14px 0 6px 0;
        }
        .med-paragraph {
            margin: 10px 0;
            font-size: 14.5px;
            color: var(--med-text-main);
        }
        .med-list {
            margin: 10px 0 10px 24px;
            padding-left: 0;
        }
        .med-list li {
            margin-bottom: 5px;
            font-size: 14.5px;
        }
        .table-responsive {
            overflow-x: auto;
            margin: 16px 0;
            border-radius: 6px;
            border: 1px solid var(--med-border);
        }
        .med-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13.5px;
            text-align: left;
            background: #ffffff;
        }
        .med-table th {
            background-color: #f8fafc;
            color: #334155;
            font-weight: 600;
            padding: 10px 14px;
            border-bottom: 2px solid var(--med-border);
        }
        .med-table td {
            padding: 9px 14px;
            border-bottom: 1px solid var(--med-border);
            color: #1e293b;
        }
        .med-table tr:last-child td {
            border-bottom: none;
        }
        .med-table tr:hover {
            background-color: #f8fafc;
        }
        """

        full_html = (
            f"<!DOCTYPE html>\n"
            f'<html lang="en">\n'
            f"<head>\n"
            f'    <meta charset="UTF-8">\n'
            f'    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f"    <title>{html.escape(display_title)}</title>\n"
            f"    <style>\n{css_style}\n    </style>\n"
            f"</head>\n"
            f"<body>\n"
            f"{container_html}\n"
            f"</body>\n"
            f"</html>"
        )
        return full_html

    @classmethod
    def extract_subsections_data(
        cls,
        result: ExtractionResult,
        product_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Extracts each discovered subsection (e.g. 16.1, 16.2) into a structured dictionary
        with its own subsection number, title, text, tables list, and embeddable HTML snippet.
        """
        all_blocks = result.blocks or []
        main_sec = result.requested_section
        
        # Group blocks by subsection (ignoring root section)
        sub_groups: Dict[str, List] = {}
        for b in all_blocks:
            sec = b.section
            if sec and sec != main_sec:
                sub_groups.setdefault(sec, []).append(b)

        subsections_data: List[Dict[str, Any]] = []
        for sec_num, blist in sub_groups.items():
            # Find title
            title = f"Section {sec_num}"
            for b in blist:
                if getattr(b, "block_type", "") == "heading":
                    title = b.text
                    break
            
            # Text
            text_parts = [b.text for b in blist if getattr(b, "block_type", "") != "heading" and b.text]
            combined_text = "\n\n".join(text_parts)

            # Tables
            tables = []
            for b in blist:
                if getattr(b, "block_type", "") == "table":
                    tables.append({
                        "id": b.id,
                        "page": b.page,
                        "columns": getattr(b, "table_columns", None) or [],
                        "rows": getattr(b, "table_rows", None) or [],
                        "markdown": getattr(b, "table_markdown", "") or "",
                    })

            # Embeddable HTML snippet for this subsection
            sub_html = cls.generate_structured_html(
                result=result,
                product_name=product_name,
                target_subsection=sec_num,
                standalone=False,
            )

            subsections_data.append({
                "subsection_number": sec_num,
                "title": title,
                "text": combined_text,
                "tables": tables,
                "html_snippet": sub_html,
            })

        return subsections_data

    @classmethod
    def export_html(cls, result: ExtractionResult, output_path: Path) -> Path:
        """Generates semantic standalone HTML with styled headings, paragraphs, lists, and tables."""
        html_content = cls.generate_html_content(result)
        output_path.write_text(html_content, encoding="utf-8")
        return output_path


    @staticmethod
    def export_json(result: ExtractionResult, output_path: Path) -> Path:
        """Saves complete structured JSON exactly matching the ExtractionResult schema and UI view."""
        data = result.model_dump(mode="json", exclude={"download_urls"})
        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return output_path

    @staticmethod
    def export_txt(result: ExtractionResult, output_path: Path) -> Path:
        """Saves result as human-readable plain text."""
        lines = [
            "=" * 65,
            f"DOCUMENT: {result.document}",
            f"REQUESTED SECTION: {result.requested_section}"
            + (f" -> {result.requested_subsection}" if result.requested_subsection else ""),
            f"PAGE RANGE: {result.start_page} - {result.end_page}",
            f"STATUS: {result.status.upper()}",
            "=" * 65,
            "",
            "VALIDATION AUDIT:",
            f"  - Main Section Found: {result.validation.was_main_section_found}",
            f"  - Target Subsection Found: {result.validation.was_target_subsection_found}",
            f"  - Included Sections: {', '.join(result.validation.included_sections)}",
            f"  - Excluded Sections: {', '.join(result.validation.excluded_sections[:8])}",
            f"  - Table Option Mode: {getattr(result, 'table_mode', 'add').upper()}",
            f"  - Tables Included: {result.validation.tables_included_count}",
            f"  - Tables Neglected: {getattr(result.validation, 'tables_neglected_count', 0)}",
            f"  - Confidence Score: {result.validation.confidence_score * 100:.0f}%",
            "-" * 65,
            "",
            "EXTRACTED CONTENT:",
            result.content,
            "",
            "=" * 65,
        ]
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path

    @staticmethod
    def export_csv(result: ExtractionResult, output_path: Path) -> Path:
        """Saves element-by-element traceability as CSV."""
        fieldnames = ["id", "page", "section", "type", "text_or_caption", "bbox"]
        with open(output_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for idx, item in enumerate(result.structured_content):
                txt_val = item.text or item.title or (f"Table: {len(item.rows or [])} rows" if item.type == "table" else "")
                writer.writerow({
                    "id": f"elem_{idx + 1}",
                    "page": item.page,
                    "section": item.section_number or "",
                    "type": item.type,
                    "text_or_caption": txt_val.replace("\n", " "),
                    "bbox": str(item.bbox) if item.bbox else "",
                })
        return output_path

    @staticmethod
    def export_excel(result: ExtractionResult, output_path: Path) -> Path:
        """Generates a styled Excel workbook with Summary and native spreadsheet tables."""
        wb = Workbook()

        # Styles
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        title_font = Font(name="Calibri", size=14, bold=True, color="0F172A")
        table_header_fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        bold_font = Font(name="Calibri", size=10, bold=True)
        regular_font = Font(name="Calibri", size=10)
        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )

        # Tab 1: Summary & Audit
        ws_summary = wb.active
        ws_summary.title = "Summary & Audit"
        ws_summary.views.sheetView[0].showGridLines = True

        ws_summary.cell(row=1, column=1, value="PDF Section Extraction Audit Report").font = title_font

        summary_rows = [
            ("Document Name", result.document),
            ("Requested Section", result.requested_section),
            ("Target Subsection", result.requested_subsection or "All Subsections"),
            ("Start Page", result.start_page),
            ("End Page", result.end_page),
            ("Extraction Status", result.status.upper()),
            ("Confidence Score", f"{result.validation.confidence_score * 100:.0f}%"),
            ("Included Sections", ", ".join(result.validation.included_sections)),
            ("Excluded Boundaries", ", ".join(result.validation.excluded_sections[:10])),
            ("Table Option Mode", getattr(result, "table_mode", "add").upper()),
            ("Tables Included", result.validation.tables_included_count),
            ("Tables Neglected", getattr(result.validation, "tables_neglected_count", 0)),
            ("Structured Elements", len(result.structured_content)),
            ("Status Message", result.validation.status_message),
        ]

        for r_idx, (k, v) in enumerate(summary_rows, start=3):
            cell_k = ws_summary.cell(row=r_idx, column=1, value=k)
            cell_k.font = bold_font
            cell_v = ws_summary.cell(row=r_idx, column=2, value=str(v))
            cell_v.font = regular_font

        ws_summary.column_dimensions["A"].width = 25
        ws_summary.column_dimensions["B"].width = 65

        # Tab 2: Extracted Tables (native spreadsheet tables)
        table_items = [it for it in result.structured_content if it.type == "table" and it.columns]
        if table_items:
            ws_tables = wb.create_sheet(title="Extracted Tables")
            ws_tables.views.sheetView[0].showGridLines = True
            current_row = 1

            for t_idx, tb in enumerate(table_items, start=1):
                caption_str = tb.caption or f"Table {t_idx} (Page {tb.page})"
                ws_tables.cell(row=current_row, column=1, value=caption_str).font = bold_font
                current_row += 1

                # Header Row
                for c_idx, col in enumerate(tb.columns, start=1):
                    cell = ws_tables.cell(row=current_row, column=c_idx, value=col)
                    cell.fill = table_header_fill
                    cell.font = header_font
                    cell.border = thin_border
                    cell.alignment = Alignment(horizontal="center")
                current_row += 1

                # Data Rows
                for row_dict in (tb.rows or []):
                    for c_idx, col in enumerate(tb.columns, start=1):
                        cell_val = row_dict.get(col, "")
                        cell = ws_tables.cell(row=current_row, column=c_idx, value=str(cell_val))
                        cell.font = regular_font
                        cell.border = thin_border
                    current_row += 1
                current_row += 2

            for c in range(1, 10):
                col_letter = chr(64 + c)
                ws_tables.column_dimensions[col_letter].width = 35

        # Tab 3: Content Elements
        ws_content = wb.create_sheet(title="Content Elements")
        ws_content.views.sheetView[0].showGridLines = True
        c_headers = ["Index", "Type", "Page", "Section", "Content"]
        for c_i, h in enumerate(c_headers, start=1):
            cell = ws_content.cell(row=1, column=c_i, value=h)
            cell.fill = header_fill
            cell.font = header_font

        for r_idx, item in enumerate(result.structured_content, start=2):
            ws_content.cell(row=r_idx, column=1, value=r_idx - 1).font = regular_font
            ws_content.cell(row=r_idx, column=2, value=item.type).font = regular_font
            ws_content.cell(row=r_idx, column=3, value=item.page).font = regular_font
            ws_content.cell(row=r_idx, column=4, value=item.section_number or "").font = bold_font
            txt = item.text or item.title or (f"Table ({len(item.rows or [])} rows)" if item.type == "table" else "")
            c_text = ws_content.cell(row=r_idx, column=5, value=txt)
            c_text.font = regular_font
            c_text.alignment = Alignment(wrap_text=True)

        ws_content.column_dimensions["A"].width = 8
        ws_content.column_dimensions["B"].width = 15
        ws_content.column_dimensions["C"].width = 10
        ws_content.column_dimensions["D"].width = 15
        ws_content.column_dimensions["E"].width = 80

        wb.save(output_path)
        return output_path

    @classmethod
    def export_all(cls, result: ExtractionResult, doc_id: str) -> Dict[str, str]:
        """Generates all 5 export formats and returns access URLs."""
        base_name = f"{doc_id}_{Path(result.document).stem}"
        txt_path = OUTPUT_DIR / f"{base_name}.txt"
        json_path = OUTPUT_DIR / f"{base_name}.json"
        csv_path = OUTPUT_DIR / f"{base_name}.csv"
        xlsx_path = OUTPUT_DIR / f"{base_name}.xlsx"
        html_path = OUTPUT_DIR / f"{base_name}.html"

        cls.export_txt(result, txt_path)
        cls.export_json(result, json_path)
        cls.export_csv(result, csv_path)
        cls.export_excel(result, xlsx_path)
        cls.export_html(result, html_path)
        result.Data = cls.generate_html_content(result)

        return {
            "txt": f"/api/download/{txt_path.name}",
            "json": f"/api/download/{json_path.name}",
            "csv": f"/api/download/{csv_path.name}",
            "excel": f"/api/download/{xlsx_path.name}",
            "html": f"/api/download/{html_path.name}",
        }

    @classmethod
    def export_batch_summary(cls, batch: BatchExtractionResponse, batch_id: str) -> Tuple[str, str]:
        """Creates CSV and Excel summary reports for a batch run."""
        csv_path = OUTPUT_DIR / f"batch_{batch_id}_summary.csv"
        xlsx_path = OUTPUT_DIR / f"batch_{batch_id}_summary.xlsx"

        records = []
        for r in batch.results:
            records.append({
                "PDF Name": r.document,
                "Section": r.requested_section,
                "Subsection": r.requested_subsection or "",
                "Start Page": r.start_page,
                "End Page": r.end_page,
                "Status": r.status,
                "Confidence": f"{r.validation.confidence_score * 100:.0f}%",
                "Blocks Extracted": r.validation.total_blocks_extracted,
                "Tables Extracted": r.validation.tables_included_count,
                "Subsections Found": ", ".join(r.subsections_found),
                "Error Message": r.error_message or "",
            })

        df = pd.DataFrame(records)
        df.to_csv(csv_path, index=False)
        df.to_excel(xlsx_path, index=False, sheet_name="Batch Summary")

        return f"/api/download/{csv_path.name}", f"/api/download/{xlsx_path.name}"
