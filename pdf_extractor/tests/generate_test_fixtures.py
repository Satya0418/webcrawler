import os
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


def get_styles():
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        spaceAfter=10,
        textColor=colors.black,
    )
    h2 = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        spaceAfter=8,
        textColor=colors.black,
    )
    h3 = ParagraphStyle(
        "Heading3_Custom",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        spaceAfter=6,
        textColor=colors.black,
    )
    body = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=6,
        textColor=colors.black,
    )
    toc_style = ParagraphStyle(
        "TOC_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=4,
    )
    return styles, h1, h2, h3, body, toc_style


def build_test1_basic():
    pdf_path = FIXTURES_DIR / "test1_basic.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    _, h1, h2, _, body, _ = get_styles()
    story = [
        Paragraph("16. Safety Information", h1),
        Paragraph("This is the overall safety information text for section 16.", body),
        Spacer(1, 10),
        Paragraph("16.1 Adverse Events", h2),
        Paragraph("Details regarding reported adverse events during clinical trials.", body),
        Spacer(1, 10),
        Paragraph("16.2 Laboratory Findings", h2),
        Paragraph("Clinical chemistry and hematology findings are summarized here.", body),
        Spacer(1, 10),
        Paragraph("17. Clinical Data", h1),
        Paragraph("Efficacy evaluation and clinical endpoints data.", body),
    ]
    doc.build(story)
    return pdf_path


def build_test2_deep_subsections():
    pdf_path = FIXTURES_DIR / "test2_deep_subsections.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    _, h1, h2, h3, body, _ = get_styles()
    story = [
        Paragraph("16. Safety Information", h1),
        Paragraph("Comprehensive safety overview and pharmacovigilance reports.", body),
        Spacer(1, 10),
        Paragraph("16.1 Adverse Events", h2),
        Paragraph("Adverse event categories and severity classifications.", body),
        Spacer(1, 8),
        Paragraph("16.1.1 Serious Events", h3),
        Paragraph("Serious adverse events including hospitalizations and life-threatening reactions.", body),
        Spacer(1, 8),
        Paragraph("16.1.2 Non-serious Events", h3),
        Paragraph("Mild to moderate non-serious events including mild headache and fatigue.", body),
        Spacer(1, 10),
        Paragraph("16.2 Laboratory Findings", h2),
        Paragraph("Complete blood counts and renal function test panels.", body),
        Spacer(1, 10),
        Paragraph("17. Clinical Data", h1),
        Paragraph("Overall trial findings.", body),
    ]
    doc.build(story)
    return pdf_path


def build_test3_multipage():
    pdf_path = FIXTURES_DIR / "test3_multipage.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    _, h1, h2, h3, body, _ = get_styles()
    story = [
        # Page 1
        Paragraph("15. Toxicology and Pharmacology", h1),
        Paragraph("Preclinical pharmacology and animal model data.", body),
        PageBreak(),
        # Page 2
        Paragraph("16. Safety Information", h1),
        Paragraph("General safety profile across all patient cohorts.", body),
        Paragraph("Patient population demographics and baseline characteristics.", body),
        PageBreak(),
        # Page 3
        Paragraph("16.1 Adverse Events", h2),
        Paragraph("Detailed adverse event analysis spanning multiple observation periods.", body),
        Paragraph("Patient monitoring was conducted every two weeks.", body),
        PageBreak(),
        # Page 4
        Paragraph("16.1.1 Serious Events", h3),
        Paragraph("Detailed breakdown of serious adverse events across trial arms.", body),
        PageBreak(),
        # Page 5
        Paragraph("16.1.2 Non-serious Events", h3),
        Paragraph("Detailed list of non-serious adverse events observed in treatment groups.", body),
        PageBreak(),
        # Page 6
        Paragraph("16.2 Laboratory Findings", h2),
        Paragraph("Clinical pathology, urinalysis, and metabolic panels.", body),
        PageBreak(),
        # Page 7
        Paragraph("17. Clinical Efficacy", h1),
        Paragraph("Primary and secondary efficacy endpoints.", body),
    ]
    doc.build(story)
    return pdf_path


def build_test4_same_page_boundary():
    pdf_path = FIXTURES_DIR / "test4_same_page_boundary.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    _, h1, h2, h3, body, _ = get_styles()
    story = [
        Paragraph("16. Safety Information", h1),
        Paragraph("Safety overview text.", body),
        Spacer(1, 6),
        Paragraph("16.1 Adverse Events", h2),
        Paragraph("Adverse events summary.", body),
        Spacer(1, 6),
        Paragraph("16.1.1 Serious Events", h3),
        Paragraph("Severe complications were rare and self-limiting.", body),
        Spacer(1, 6),
        Paragraph("16.1.2 Non-serious Events", h3),
        Paragraph("Non-serious events included nausea in 4% of participants.", body),
        Spacer(1, 15),
        # On the exact same page: 16.2 starts!
        Paragraph("16.2 Laboratory Findings", h2),
        Paragraph("Baseline laboratory values were within normal limits.", body),
        Spacer(1, 10),
        Paragraph("17. Clinical Summary", h1),
        Paragraph("Concluding clinical remarks.", body),
    ]
    doc.build(story)
    return pdf_path


def build_test5_scanned_mock():
    # Produces a PDF with minimal text characters to trigger OCR detection
    pdf_path = FIXTURES_DIR / "test5_scanned_mock.pdf"
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    # Insert a drawn rectangle and tiny placeholder instead of rich font text
    page.draw_rect(fitz.Rect(50, 50, 500, 700), color=(0.5, 0.5, 0.5), fill=(0.95, 0.95, 0.95))
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def build_test6_toc():
    pdf_path = FIXTURES_DIR / "test6_toc.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    _, h1, h2, _, body, toc_style = get_styles()
    story = [
        # Page 1: Table of Contents
        Paragraph("Table of Contents", h1),
        Spacer(1, 10),
        Paragraph("15. Pharmacology ...................................................... 1", toc_style),
        Paragraph("16. Safety Information ................................................ 2", toc_style),
        Paragraph("16.1 Adverse Events ................................................... 2", toc_style),
        Paragraph("16.2 Laboratory Findings .............................................. 3", toc_style),
        Paragraph("17. Clinical Data ..................................................... 4", toc_style),
        PageBreak(),
        # Page 2: Actual Body
        Paragraph("16. Safety Information", h1),
        Paragraph("This is the real body content of Section 16.", body),
        Spacer(1, 10),
        Paragraph("16.1 Adverse Events", h2),
        Paragraph("Real adverse events body text describing observed frequencies.", body),
        PageBreak(),
        # Page 3: 16.2
        Paragraph("16.2 Laboratory Findings", h2),
        Paragraph("Real laboratory findings body text.", body),
        PageBreak(),
        # Page 4: 17
        Paragraph("17. Clinical Data", h1),
        Paragraph("Real clinical data body text.", body),
    ]
    doc.build(story)
    return pdf_path


def build_test7_in_text_citation():
    pdf_path = FIXTURES_DIR / "test7_in_text_citation.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    _, h1, h2, _, body, _ = get_styles()
    story = [
        Paragraph("15. Study Introduction", h1),
        Paragraph(
            "As discussed in Section 16.1, adverse events were monitored closely throughout. "
            "Overall, 16.1% of patients reported mild reactions. See Section 16 for detailed safety criteria.",
            body
        ),
        Spacer(1, 15),
        Paragraph("16. Safety Information", h1),
        Paragraph("Official safety information chapter body text.", body),
        Spacer(1, 10),
        Paragraph("16.1 Adverse Events", h2),
        Paragraph("Official adverse events section body text.", body),
        Spacer(1, 10),
        Paragraph("16.2 Laboratory Findings", h2),
        Paragraph("Official laboratory findings section body text.", body),
    ]
    doc.build(story)
    return pdf_path


def build_test8_tables():
    pdf_path = FIXTURES_DIR / "test8_tables.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    _, h1, h2, _, body, _ = get_styles()

    table1_data = [
        ["Adverse Reaction", "Drug A (N=100)", "Placebo (N=100)"],
        ["Headache", "12 (12%)", "4 (4%)"],
        ["Nausea", "8 (8%)", "2 (2%)"],
        ["Dizziness", "5 (5%)", "1 (1%)"],
    ]
    t1 = Table(table1_data, colWidths=[150, 120, 120])
    t1.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.navy),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
    ]))

    table2_data = [
        ["Laboratory Test", "Baseline Mean", "Week 12 Mean"],
        ["ALT (U/L)", "22.4", "24.1"],
        ["AST (U/L)", "20.1", "21.0"],
        ["Serum Creatinine (mg/dL)", "0.9", "0.9"],
    ]
    t2 = Table(table2_data, colWidths=[150, 120, 120])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))

    story = [
        Paragraph("16. Safety Information", h1),
        Paragraph("Safety information text with clinical event tables below.", body),
        Spacer(1, 10),
        Paragraph("16.1 Adverse Events", h2),
        Paragraph("Table 1 summarizes all treatment-emergent adverse reactions.", body),
        Spacer(1, 6),
        t1,
        Spacer(1, 15),
        Paragraph("16.2 Laboratory Findings", h2),
        Paragraph("Table 2 outlines hepatic and renal laboratory measures.", body),
        Spacer(1, 6),
        t2,
    ]
    doc.build(story)
    return pdf_path


def generate_all():
    print("Generating test fixtures...")
    f1 = build_test1_basic()
    f2 = build_test2_deep_subsections()
    f3 = build_test3_multipage()
    f4 = build_test4_same_page_boundary()
    f5 = build_test5_scanned_mock()
    f6 = build_test6_toc()
    f7 = build_test7_in_text_citation()
    f8 = build_test8_tables()
    print("Successfully generated all 8 test fixtures in:", FIXTURES_DIR)
    return [f1, f2, f3, f4, f5, f6, f7, f8]


if __name__ == "__main__":
    generate_all()
