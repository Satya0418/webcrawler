import json
import csv
import io
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
    def export_html(result: ExtractionResult, output_path: Path) -> Path:
        """Generates semantic standalone HTML with styled headings, paragraphs, lists, and tables."""
        body_elements = []

        for item in result.structured_content:
            if item.type == "heading":
                tag = f"h{min(item.level or 1, 4)}"
                body_elements.append(
                    f'<{tag} class="section-heading" data-page="{item.page}" data-sec="{item.section_number or ""}">'
                    f'<span class="sec-num">{item.section_number or ""}</span> {item.title or item.text or ""}'
                    f'<span class="page-tag">p. {item.page}</span>'
                    f'</{tag}>'
                )
            elif item.type in ("bullet_list", "numbered_list"):
                tag = "ul" if item.type == "bullet_list" else "ol"
                li_items = "".join(f"<li>{it}</li>" for it in (item.items or []))
                body_elements.append(
                    f'<{tag} class="content-list" data-page="{item.page}">{li_items}</{tag}>'
                )
            elif item.type == "table":
                cols_html = "".join(f"<th>{col}</th>" for col in (item.columns or []))
                rows_html = ""
                for row_dict in (item.rows or []):
                    cells = "".join(f"<td>{row_dict.get(col, '')}</td>" for col in (item.columns or []))
                    rows_html += f"<tr>{cells}</tr>\n"

                caption = f'<caption>{item.caption} (Page {item.page})</caption>' if item.caption else ''
                table_html = (
                    f'<div class="table-wrap" data-page="{item.page}">'
                    f'<table class="extracted-table">{caption}'
                    f'<thead><tr>{cols_html}</tr></thead>'
                    f'<tbody>{rows_html}</tbody>'
                    f'</table></div>'
                )
                body_elements.append(table_html)
            else:
                text_clean = (item.text or "").replace("\n", "<br>")
                body_elements.append(
                    f'<p class="content-p" data-page="{item.page}">{text_clean}</p>'
                )

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{result.document} - Section {result.requested_section}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
      color: #1e293b;
      max-width: 900px;
      margin: 40px auto;
      padding: 0 20px;
      background-color: #f8fafc;
    }}
    .document-card {{
      background: #ffffff;
      padding: 32px;
      border-radius: 8px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
      border: 1px solid #e2e8f0;
    }}
    h1, h2, h3, h4 {{
      color: #0f172a;
      margin-top: 24px;
      margin-bottom: 12px;
      position: relative;
    }}
    .sec-num {{
      color: #4f46e5;
      font-weight: bold;
    }}
    .page-tag {{
      font-size: 0.75rem;
      background: #e0e7ff;
      color: #4338ca;
      padding: 2px 6px;
      border-radius: 4px;
      margin-left: 8px;
      vertical-align: middle;
    }}
    p {{
      margin-bottom: 16px;
      color: #334155;
    }}
    ul, ol {{
      margin-bottom: 16px;
      padding-left: 24px;
    }}
    li {{
      margin-bottom: 6px;
    }}
    .table-wrap {{
      overflow-x: auto;
      margin: 20px 0;
    }}
    table.extracted-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
    }}
    table.extracted-table th, table.extracted-table td {{
      border: 1px solid #cbd5e1;
      padding: 10px 12px;
      text-align: left;
    }}
    table.extracted-table th {{
      background-color: #f1f5f9;
      font-weight: 600;
      color: #0f172a;
    }}
    table.extracted-table tr:nth-child(even) td {{
      background-color: #f8fafc;
    }}
    caption {{
      font-weight: bold;
      margin-bottom: 8px;
      text-align: left;
      color: #475569;
    }}
  </style>
</head>
<body>
  <div class="document-card">
    <header style="border-bottom: 2px solid #e2e8f0; padding-bottom: 16px; margin-bottom: 24px;">
      <h2>Document: {result.document}</h2>
      <p style="margin: 0; color: #64748b;">
        Requested Section: <strong>{result.requested_section}</strong> &rarr; 
        Target Subsection: <strong>{result.requested_subsection or "All"}</strong> | 
        Pages: <strong>{result.start_page} &ndash; {result.end_page}</strong>
      </p>
    </header>
    <main>
      {"".join(body_elements)}
    </main>
  </div>
</body>
</html>
"""
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
            f"  - Tables Included: {result.validation.tables_included_count}",
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
            ("Tables Included", result.validation.tables_included_count),
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
