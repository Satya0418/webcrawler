import re
import json
import csv
import io
import html
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
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
        Generates semantic HTML formatted with the exact styling requested:
        - Arial font, 40px margin, #f9f9f9 body background
        - Blue (#007BFF) table headers with white bold text
        - Border bottom #ddd, hover effect #f5f5f5, box-shadow on table
        - <h2> headings for tables and sections
        - Section numbers (e.g. 16, 16.1) omitted from titles, headings, and table headers
        """
        if title:
            clean_t = cls._clean_section_heading(title)
            page_title = clean_t or "Sample HTML Table"
        elif result.document and result.document != "document.pdf":
            stem = Path(result.document).stem.replace("_", " ").title()
            clean_stem = cls._clean_section_heading(stem)
            page_title = clean_stem or "Sample HTML Table"
        else:
            page_title = "Sample HTML Table"

        body_elements = []

        is_neglect_mode = getattr(result, "table_mode", "add") == "neglect"

        # First pass: check if structured tables exist
        table_items = [it for it in (result.structured_content or []) if it.type == "table"]

        if is_neglect_mode:
            # Text Only mode: Render purely semantic headings, paragraphs, and lists without any table
            for item in (result.structured_content or []):
                if item.type == "heading":
                    raw_h = item.title or item.text or ""
                    h_text = cls._clean_section_heading(raw_h)
                    if h_text:
                        body_elements.append(f"<h2>{html.escape(h_text)}</h2>")
                elif item.type in ("bullet_list", "numbered_list"):
                    lis = "".join(f"<li>{html.escape(str(it))}</li>" for it in (item.items or []))
                    body_elements.append(f"<ul style=\"margin: 10px 0 10px 24px; color: #333;\">{lis}</ul>")
                elif item.type != "table":
                    p_text = html.escape(item.text or "").replace("\n", "<br>")
                    if p_text.strip():
                        body_elements.append(f"<p style=\"margin: 12px 0; color: #333; line-height: 1.6;\">{p_text}</p>")

        elif table_items:
            for item in (result.structured_content or []):
                if item.type == "heading":
                    raw_h = item.title or item.text or ""
                    h_text = cls._clean_section_heading(raw_h)
                    if h_text:
                        body_elements.append(f"<h2>{html.escape(h_text)}</h2>")
                elif item.type == "table":
                    caption = ""
                    if item.caption:
                        caption = cls._clean_section_heading(item.caption)
                    if not caption:
                        caption = f"Extracted Table (Page {item.page})" if item.page else "Extracted Table"

                    cols = item.columns or []
                    th_cells = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
                    thead = f"<thead><tr>{th_cells}</tr></thead>" if th_cells else ""

                    rows_html = []
                    if item.rows:
                        for row_dict in item.rows:
                            td_cells = "".join(f"<td>{html.escape(str(row_dict.get(c, '')))}</td>" for c in cols)
                            rows_html.append(f"<tr>{td_cells}</tr>")
                    elif item.raw_rows:
                        for r_list in item.raw_rows:
                            td_cells = "".join(f"<td>{html.escape(str(val))}</td>" for val in r_list)
                            rows_html.append(f"<tr>{td_cells}</tr>")

                    tbody = f"<tbody>{''.join(rows_html)}</tbody>"
                    body_elements.append(f"<h2>{html.escape(caption)}</h2><table>{thead}{tbody}</table>")
                elif item.type in ("bullet_list", "numbered_list"):
                    lis = "".join(f"<li>{html.escape(str(it))}</li>" for it in (item.items or []))
                    body_elements.append(f"<ul style=\"margin: 10px 0 10px 24px; color: #333;\">{lis}</ul>")
                else:
                    p_text = html.escape(item.text or "").replace("\n", "<br>")
                    if p_text.strip():
                        body_elements.append(f"<p style=\"margin: 12px 0; color: #333; line-height: 1.6;\">{p_text}</p>")
        else:
            # No explicit table matrices found: create document narrative + structured data table
            doc_stem = Path(result.document).stem.replace("_", " ").title() if result.document and result.document != "document.pdf" else ""
            clean_doc_heading = cls._clean_section_heading(doc_stem)
            if clean_doc_heading:
                body_elements.append(f"<h2>{html.escape(clean_doc_heading)}</h2>")

            table_rows = []
            idx = 1
            for item in (result.structured_content or []):
                if item.type == "heading":
                    raw_h = item.title or item.text or ""
                    h_text = cls._clean_section_heading(raw_h)
                    if h_text:
                        body_elements.append(f"<h2>{html.escape(h_text)}</h2>")
                        table_rows.append((f"{idx:03d}", "Heading", str(item.page), h_text))
                        idx += 1
                else:
                    txt = (item.text or "").strip()
                    if txt:
                        body_elements.append(f"<p style=\"margin: 12px 0; color: #333; line-height: 1.6;\">{html.escape(txt)}</p>")
                        table_rows.append((f"{idx:03d}", "Content", str(item.page), txt[:150] + ("..." if len(txt) > 150 else "")))
                        idx += 1

            # Guarantee that a styled <table> is ALWAYS rendered matching the user's template
            if not table_rows and result.content:
                clean_content_sample = result.content[:200].strip()
                table_rows.append((f"{idx:03d}", "Content", f"{result.start_page}-{result.end_page}", clean_content_sample))

            if table_rows:
                th_cells = "<th>ID</th><th>Type</th><th>Page</th><th>Extracted Information</th>"
                tbody_rows = "".join(
                    f"<tr><td>{html.escape(r_id)}</td><td>{html.escape(t)}</td><td>{html.escape(p)}</td><td>{html.escape(info)}</td></tr>"
                    for r_id, t, p, info in table_rows
                )
                body_elements.append(f"<h2>Extracted Information Table</h2><table><thead><tr>{th_cells}</tr></thead><tbody>{tbody_rows}</tbody></table>")
            else:
                body_elements.append("<h2>Extracted Information Table</h2><table><thead><tr><th>ID</th><th>Status</th></tr></thead><tbody><tr><td>001</td><td>No extracted data available</td></tr></tbody></table>")

        css_styles = (
            "body { font-family: Arial, sans-serif; margin: 40px; background-color: #f9f9f9; } "
            "h2 { color: #333; } "
            "table { width: 100%; border-collapse: collapse; margin-top: 20px; background-color: #ffffff; box-shadow: 0 2px 5px rgba(0,0,0,0.1); } "
            "th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #ddd; } "
            "th { background-color: #007BFF; color: white; font-weight: bold; } "
            "tr:hover { background-color: #f5f5f5; }"
        )

        inner_body = "".join(body_elements)
        html_content = (
            f'<!DOCTYPE html><html lang="en"><head>'
            f'<meta charset="UTF-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            f'<title>{html.escape(page_title)}</title>'
            f'<style>{css_styles}</style>'
            f'</head><body>{inner_body}</body></html>'
        )
        return html_content

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
