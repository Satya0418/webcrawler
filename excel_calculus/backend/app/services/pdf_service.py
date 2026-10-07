import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to compute and render total page numbers,
    official running headers, and footers on each page.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, total_pages):
        self.saveState()
        self.setFont("Times-Roman", 9)
        self.setFillColor(colors.HexColor("#0f172a"))

        product = getattr(self, "report_product", "Abiraterone")
        page_w, page_h = A4

        # Top Header (starts around y = page_h - 36)
        self.setFont("Times-Bold", 9.5)
        self.drawString(48, page_h - 34, "Apotex Inc.")
        self.drawRightString(page_w - 48, page_h - 34, product)

        self.setFont("Times-Italic", 8)
        self.setFillColor(colors.HexColor("#334155"))
        self.drawString(48, page_h - 45, "Periodic Benefit-Risk Evaluation Report / Periodic Safety Update Report")

        # Top rule
        self.setStrokeColor(colors.HexColor("#94a3b8"))
        self.setLineWidth(0.6)
        self.line(48, page_h - 49, page_w - 48, page_h - 49)

        # Bottom Footer (y = 30)
        self.line(48, 42, page_w - 48, 42)
        self.setFont("Times-Bold", 8.5)
        self.setFillColor(colors.HexColor("#475569"))
        self.drawString(48, 28, "CONFIDENTIAL")

        # Page numbering
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(page_w - 48, 28, page_str)

        self.restoreState()


class PDFReportService:
    def __init__(self, db_session=None):
        self.db = db_session

    def generate_section_16_1_pdf(self, report_data: dict) -> bytes:
        """
        Renders the official PBRER Section 16.1 table as a formal regulatory PDF.
        Strictly follows the visual layout, typography, borders, and margins of the Apotex reference document.
        """
        buffer = io.BytesIO()

        # Margins: ~0.67 in left/right (48 pt), ~0.72 in top/bottom (52 pt)
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=48,
            rightMargin=48,
            topMargin=56,
            bottomMargin=50
        )

        product_name = report_data.get("product_name", "Abiraterone")
        reporting_period = report_data.get("reporting_period", "")
        intro_text = report_data.get(
            "intro_text",
            "No literature articles relevant to the risks were retrieved during the reporting period. "
            "The number of case reports received by the MAH pertaining to the above mentioned safety concerns "
            "are presented in the table below. These case reports are discussed in detail in Section 16.3."
        )

        styles = getSampleStyleSheet()

        # Styles matching formal Times regulatory report
        title_style = ParagraphStyle(
            "SectionTitle",
            parent=styles["Normal"],
            fontName="Times-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=8
        )

        h2_style = ParagraphStyle(
            "SubSectionTitle",
            parent=styles["Normal"],
            fontName="Times-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=14,
            spaceAfter=6
        )

        body_style = ParagraphStyle(
            "ReportBody",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=10
        )

        th_left_style = ParagraphStyle(
            "TableHeaderLeft",
            parent=styles["Normal"],
            fontName="Times-Bold",
            fontSize=9.5,
            leading=12,
            alignment=0,
            textColor=colors.HexColor("#0f172a")
        )

        th_center_style = ParagraphStyle(
            "TableHeaderCenter",
            parent=styles["Normal"],
            fontName="Times-Bold",
            fontSize=9.5,
            leading=12,
            alignment=1,
            textColor=colors.HexColor("#0f172a")
        )

        category_header_style = ParagraphStyle(
            "CategoryHeader",
            parent=styles["Normal"],
            fontName="Times-Bold",
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#0f172a")
        )

        cell_left_style = ParagraphStyle(
            "CellLeft",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=9.5,
            leading=12,
            textColor=colors.HexColor("#0f172a")
        )

        cell_center_style = ParagraphStyle(
            "CellCenter",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=9.5,
            leading=12,
            alignment=1,
            textColor=colors.HexColor("#0f172a")
        )

        story = []

        # 1. Section 16.1 Title
        story.append(Paragraph("16.1 Summary of Safety Concerns", title_style))
        story.append(Paragraph(intro_text, body_style))
        story.append(Spacer(1, 4))

        # 2. Build the Official Regulatory 2-Column Table
        # Usable width: 595.27 - 96 = 499.27 pt
        col1_w = 360.0
        col2_w = 139.0

        table_data = []

        # Table Header Row (Repeats across pages if broken)
        th_term = Paragraph("Risk Term", th_left_style)
        th_count = Paragraph("Number of Relevant<br/>Case Reports", th_center_style)
        table_data.append([th_term, th_count])

        table_style_commands = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#475569")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]

        curr_row = 1

        for section in report_data.get("table_sections", []):
            cat_name = section.get("category_name", "").upper()
            # Category Header Row (spans 2 columns)
            cat_p = Paragraph(f"<b>{cat_name}</b>", category_header_style)
            table_data.append([cat_p, ""])

            table_style_commands.append(("SPAN", (0, curr_row), (1, curr_row)))
            table_style_commands.append(("BACKGROUND", (0, curr_row), (1, curr_row), colors.HexColor("#f8fafc")))
            table_style_commands.append(("LINEBEFORE", (0, curr_row), (-1, curr_row), 0.75, colors.HexColor("#475569")))
            table_style_commands.append(("LINEAFTER", (0, curr_row), (-1, curr_row), 0.75, colors.HexColor("#475569")))
            table_style_commands.append(("LINEABOVE", (0, curr_row), (-1, curr_row), 0.75, colors.HexColor("#64748b")))
            table_style_commands.append(("LINEBELOW", (0, curr_row), (-1, curr_row), 0.5, colors.HexColor("#94a3b8")))
            table_style_commands.append(("TOPPADDING", (0, curr_row), (-1, curr_row), 6))
            table_style_commands.append(("BOTTOMPADDING", (0, curr_row), (-1, curr_row), 6))

            curr_row += 1

            for risk in section.get("risks", []):
                risk_term = risk.get("risk_term", "")
                rel_count = str(risk.get("number_of_relevant_cases", 0))

                risk_p = Paragraph(risk_term, cell_left_style)
                count_p = Paragraph(rel_count, cell_center_style)

                table_data.append([risk_p, count_p])
                table_style_commands.append(("LEFTPADDING", (0, curr_row), (0, curr_row), 18))
                table_style_commands.append(("TOPPADDING", (0, curr_row), (-1, curr_row), 4.5))
                table_style_commands.append(("BOTTOMPADDING", (0, curr_row), (-1, curr_row), 4.5))
                curr_row += 1

        reg_table = Table(
            table_data,
            colWidths=[col1_w, col2_w],
            repeatRows=1  # Automatically repeats header row if table splits across pages
        )
        reg_table.setStyle(TableStyle(table_style_commands))
        story.append(reg_table)
        story.append(Spacer(1, 16))

        # 3. Subsequent Official PBRER Sections
        story.append(Paragraph("16.2 Signal Evaluation", h2_style))
        story.append(Paragraph(
            "Evaluation of safety signals identified, ongoing, or closed during the reporting period "
            f"({reporting_period}) is summarized in the relevant risk evaluation subsections.",
            body_style
        ))
        story.append(Spacer(1, 8))

        story.append(Paragraph("16.3 Evaluation of Risks and New Information", h2_style))
        story.append(Paragraph(
            "The cumulative and interval safety data retrieved from the marketing authorization holder's "
            "safety database were evaluated against the predetermined safety criteria. "
            "Individual case histories, adverse event narratives, dechallenge/rechallenge outcomes, "
            "and relevant concomitant medications were assessed.",
            body_style
        ))

        # Dynamic evidence summary for risks that have confirmed relevant cases
        assessed_risks = []
        for sec in report_data.get("table_sections", []):
            for r in sec.get("risks", []):
                if r.get("number_of_relevant_cases", 0) > 0:
                    assessed_risks.append(r)

        if assessed_risks:
            story.append(Paragraph("<b>16.3.1 Summary of Identified Safety Concerns</b>", ParagraphStyle(
                "SubSectionBold", parent=body_style, fontName="Times-Bold", fontSize=10, spaceBefore=6
            )))
            for ar in assessed_risks:
                story.append(Paragraph(
                    f"&bull; <b>{ar.get('risk_term')}</b>: During this interval review, "
                    f"<b>{ar.get('number_of_relevant_cases')}</b> distinct case report(s) were retrieved and evaluated "
                    f"using predefined {ar.get('search_method')} criteria ({ar.get('search_criteria')}).",
                    body_style
                ))

        # Custom canvas with product name injected
        def canvas_maker(*args, **kwargs):
            c = NumberedCanvas(*args, **kwargs)
            c.report_product = product_name
            return c

        doc.build(story, canvasmaker=canvas_maker)
        return buffer.getvalue()
