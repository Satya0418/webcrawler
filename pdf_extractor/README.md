# Intelligent PDF Section Extraction System

A production-quality, **deterministic** document processing engine and web application that extracts hierarchical sections and target subsections (e.g., **Section 16 → Section 16.1**) with complete recursive subtrees (`16.1.1`, `16.1.2`, etc.) while strictly stopping at the next sibling boundary (e.g., **Section 16.2**) at the block level.

---

## 1. Key Features

- **100% Deterministic — Zero LLM Dependency**: No LLM is required or used in the extraction pipeline. Headings, hierarchy, and boundaries are computed via typography analysis, geometric layout parsing, and hierarchical tree navigation.
- **Sub-Page & Block-Level Boundary Precision**: When Section `16.1.2` and Section `16.2` share the exact same physical page, extraction truncates at the boundary block before `16.2`.
- **Multi-Signal Heading Detection**: Discriminated using 6 independent signals:
  1. Canonical numbering patterns (`16`, `16.1`, `16.1.1`).
  2. Font size & font weight relative to document body font statistics.
  3. Vertical margin spacing & standalone block positioning.
  4. Table of Contents (TOC) dot leader and trailing page number discrimination.
  5. In-text citation suppression (e.g., *"See Section 16.1 for details"*, *"16.1% of patients"*).
  6. PDF bookmark / outline cross-referencing.
- **Content Preservation**: Preserves headers, paragraphs, bulleted lists, numbered lists, numbers, percentages, dates, and embedded tables.
- **Table Detection & Linkage**: Associates tables with their parent section; extracts tables into structured JSON, Markdown, and Excel sheets while excluding tables from subsequent sections.
- **Page-Level Traceability**: Every extracted block retains its original page number, bounding box coordinates `(x0, y0, x1, y1)`, block type, and assigned section.
- **Validation & Confidence Scoring**: Automatically audits results before returning them: verifies main section existence, target subsection presence, boundary exclusion, and computes a confidence score ($0.0 - 1.0$).
- **Dual Ingestion Modes**:
  - **Mode A (Folder Path)**: Enter any folder path (e.g., `/path/to/reports/`), scan for all `.pdf` files, multi-select, and batch process.
  - **Mode B (PDF Upload)**: Drag & drop single or multiple PDF documents directly through the web UI.
- **Multi-Format Exports**: One-click downloads for **TXT**, **JSON**, **CSV**, and styled **Excel (.xlsx)**.
- **State-of-the-Art Web UI**: Dark/Light mode dashboard with interactive section hierarchy tree visualizer, block trace inspector modal, and batch summary dashboard.

---

## 2. Project Folder Structure

```
pdf_extractor/
│
├── backend/
│   ├── main.py                     # FastAPI application entrypoint & static mounting
│   ├── config.py                   # App configuration & storage paths
│   │
│   ├── api/
│   │   ├── upload.py               # File upload endpoints
│   │   ├── files.py                # Folder browsing, sample loading & downloads
│   │   └── extraction.py           # Single & batch extraction endpoints
│   │
│   ├── pdf/
│   │   ├── reader.py               # PDF loading, validation & encryption check
│   │   ├── parser.py               # Typography stats, block extraction & reading order
│   │   ├── ocr.py                  # Scanned PDF auto-detection & OCR fallback
│   │   ├── headings.py             # Multi-signal heading detection & TOC/citation filter
│   │   ├── sections.py             # Hierarchical section tree & block association
│   │   ├── tables.py               # Table extraction & bounding box merge
│   │   └── cleaner.py              # Repeated header & footer frequency/position cleaner
│   │
│   ├── extraction/
│   │   ├── section_extractor.py    # Main deterministic extraction engine
│   │   ├── boundary_detector.py    # Subtree extraction & stop condition logic
│   │   └── validator.py            # Automated validation & confidence scoring
│   │
│   ├── models/
│   │   └── schemas.py              # Pydantic models for blocks, requests & results
│   │
│   └── services/
│       └── export_service.py       # Exporters for TXT, JSON, CSV, and Excel (.xlsx)
│
├── frontend/
│   ├── index.html                  # Interactive dashboard interface
│   ├── styles.css                  # Responsive design system (dark/light theme)
│   └── app.js                      # UI state management, API calls & tree rendering
│
├── tests/
│   ├── generate_test_fixtures.py   # Synthesizes all 8 test PDFs using reportlab
│   ├── test_headings.py            # Tests heading detection & TOC/citation filters
│   ├── test_sections.py            # Tests hierarchy tree construction & parent linking
│   ├── test_extraction.py          # End-to-end extraction tests across all scenarios
│   ├── test_tables.py              # Tests table inclusion & exclusion
│   ├── test_ocr.py                 # Tests scanned PDF detection & OCR interface
│   └── test_api.py                 # Tests FastAPI endpoints & file downloads
│
├── sample_reports/                 # 8 Pre-generated PDF test documents
├── uploads/                        # User-uploaded PDF storage
├── outputs/                        # Generated TXT, JSON, CSV, XLSX exports
├── requirements.txt                # Python package dependencies
├── run.sh                          # One-command launch script
├── README.md                       # Complete documentation
└── .env.example                    # Environment configuration template
```

---

## 3. Installation & Setup

### Prerequisites
- Python 3.9+ installed
- *(Optional)* Tesseract OCR (`brew install tesseract` on macOS or `apt install tesseract-ocr` on Linux) if optical character recognition is required for purely scanned images.

### Quick Start (Automated)
Run the provided startup script:
```bash
cd pdf_extractor
chmod +x run.sh
./run.sh
```

### Manual Setup
```bash
# 1. Navigate to the project directory
cd pdf_extractor

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Generate the 8 programmatic test fixture PDFs
python tests/generate_test_fixtures.py

# 5. Launch the FastAPI server
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Once launched:
- **Web Application Dashboard**: Open [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive Swagger API Documentation**: Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 4. Explanation of the Section Detection & Extraction Algorithm

### A. Document Layout & Typography Parsing
1. PyMuPDF (`fitz`) parses each page into blocks, lines, and text spans.
2. The engine computes the **document-wide body font size** (the statistical mode of font sizes weighted by character length).
3. Blocks within the top 8% or bottom 8% margins that repeat identical text across $\ge 2$ pages or match page number patterns are tagged as `HEADER` or `FOOTER` and suppressed from body content.

### B. Multi-Signal Heading Detection
A text line is classified as a section heading if and only if it passes multi-signal filtering:
1. **Numbering Pattern**: Matches `^(?:Section\s+)?(\d+(?:\.\d+)*)(?:[\.\:\s\-]+)(.*)$`.
2. **Canonical Numbering**: Strips trailing dots (e.g., `"16."` $\to$ `"16"`, `"16.1."` $\to$ `"16.1"`).
3. **Typography Prominence**: Font size $\ge$ body font size, or bold font flag / bold font family.
4. **TOC Discrimination**: Rejects dot leaders (`.... 20`) or lines ending with trailing page numbers.
5. **In-text Citation Rejection**: Rejects sentences starting with phrases like *"See Section 16.1"*, *"According to Section 16"*, sentences exceeding 150 characters, or decimal percentages like *"16.1%"*.
6. **Block Splitting**: If a block starts with a heading on line 0 followed by paragraph text, it is cleanly partitioned into a `Heading` block and a `Paragraph` block.

### C. Hierarchical Tree Assembly
1. Headings are linked hierarchically using prefix parent derivation:
   $$\text{Parent of } \text{"16.1.2"} = \text{"16.1"}, \quad \text{Parent of } \text{"16.1"} = \text{"16"}$$
2. Subsequent body blocks (paragraphs, lists, tables) are automatically assigned to the active section until a new heading is encountered.

### D. Boundary Detection & Subtree Extraction
Given target request `main_section="16"`, `target_subsection="16.1"`:
1. **Start Boundary**: The heading block of Section 16.
2. **Subtree Collection**:
   - Introductory content of Section 16 before 16.1 starts.
   - Section 16.1 heading and direct content.
   - All recursive descendants whose section number starts with `16.1.` (`16.1.1`, `16.1.2`, etc.).
3. **Stop Boundary**:
   - The first block belonging to the next sibling of 16.1 (e.g., `16.2`).
   - If no sibling exists under 16, the next root section (e.g., `17`).
4. **Sub-Page Precision**: Extraction operates on ordered blocks `(page_num, y0, x0)`. If `16.1.2` and `16.2` appear on the exact same page, extraction stops precisely at the block before `16.2`.

---

## 5. REST API Documentation

### 1. `POST /api/extract`
Extracts a section from a single document.
**Request Body**:
```json
{
  "file_path": "/Users/satya/Desktop/webcrwler/pdf_extractor/sample_reports/test1_basic.pdf",
  "filename": "test1_basic.pdf",
  "main_section": "16",
  "target_subsection": "16.1"
}
```
**Response**:
```json
{
  "document": "test1_basic.pdf",
  "requested_section": "16",
  "requested_subsection": "16.1",
  "start_page": 1,
  "end_page": 1,
  "subsections_found": ["16.1"],
  "content": "[Page 1] 16. Safety Information\n...",
  "status": "success",
  "validation": {
    "was_main_section_found": true,
    "was_target_subsection_found": true,
    "included_sections": ["16", "16.1"],
    "excluded_sections": ["16.2"],
    "tables_included_count": 0,
    "total_blocks_extracted": 4,
    "confidence_score": 1.0,
    "status_message": "Extraction completed with high confidence."
  },
  "download_urls": {
    "txt": "/api/download/a1b2c3d4_test1_basic.txt",
    "json": "/api/download/a1b2c3d4_test1_basic.json",
    "csv": "/api/download/a1b2c3d4_test1_basic.csv",
    "excel": "/api/download/a1b2c3d4_test1_basic.xlsx"
  }
}
```

### 2. `POST /api/extract/batch`
Batch extracts sections from a list of files or an entire folder path.
**Request Body**:
```json
{
  "folder_path": "/Users/satya/Desktop/webcrwler/pdf_extractor/sample_reports",
  "main_section": "16",
  "target_subsection": "16.1"
}
```

### 3. `POST /api/files/browse`
Validates and lists all `.pdf` documents in a local directory.
**Request Body**:
```json
{
  "folder_path": "/path/to/pdf/folder"
}
```

### 4. `POST /api/upload`
Multipart form upload of one or more `.pdf` files.

### 5. `GET /api/download/{filename}`
Streams the requested TXT, JSON, CSV, or Excel file download.

---

## 6. Automated Test Suite

Run the full automated test suite with pytest:
```bash
.venv/bin/python -m pytest tests/ -v
```

### Test Coverage Summary:
| Test File | Test Case | Validated Behavior |
|---|---|---|
| `test_extraction.py` | `test_extraction_basic` | Extracts 16 + 16.1; strictly excludes 16.2 and 17. |
| `test_extraction.py` | `test_extraction_deep_subsections` | Extracts 16 + 16.1 + 16.1.1 + 16.1.2; excludes 16.2. |
| `test_extraction.py` | `test_extraction_multipage` | Correctly spans pages 2 to 5; excludes page 6 (16.2) and page 7 (17). |
| `test_extraction.py` | `test_extraction_same_page_boundary` | Truncates at block boundary on the same page before 16.2. |
| `test_extraction.py` | `test_extraction_toc_handling` | Ignores TOC entries on page 1; extracts actual body on page 2. |
| `test_extraction.py` | `test_extraction_in_text_citation` | Rejects *"See Section 16.1"* and *"16.1%"* in section 15 body text. |
| `test_tables.py` | `test_table_extraction_and_exclusion` | Includes Table 1 from 16.1; strictly excludes Table 2 from 16.2. |
| `test_ocr.py` | `test_scanned_pdf_detection` | Automatically flags image-only PDFs and routes to OCR pipeline. |
| `test_api.py` | `test_browse_folder_mode_a` | Validates directory reading, PDF discovery, and metadata extraction. |
| `test_api.py` | `test_extract_batch_endpoint` | Verifies non-blocking batch execution and summary file creation. |

---

## 7. Sample Input & Output

### Input Query:
- **Document**: `sample_reports/test8_tables.pdf`
- **Main Section**: `16`
- **Target Subsection**: `16.1`

### Extracted Output (TXT format):
```text
============================================================
DOCUMENT: test8_tables.pdf
REQUESTED SECTION: 16 -> 16.1
PAGE RANGE: 1 - 1
STATUS: SUCCESS
============================================================

VALIDATION SUMMARY:
  - Main Section Found: True
  - Target Subsection Found: True
  - Included Sections: 16, 16.1
  - Excluded Sections: 16.2
  - Tables Included: 1
  - Confidence Score: 100%
------------------------------------------------------------

EXTRACTED CONTENT:

[Page 1] 16. Safety Information

Safety information text with clinical event tables below.

[Page 1] 16.1 Adverse Events

Table 1 summarizes all treatment-emergent adverse reactions.

[Page 1 Table]
| Adverse Reaction | Drug A (N=100) | Placebo (N=100) |
| --- | --- | --- |
| Headache | 12 (12%) | 4 (4%) |
| Nausea | 8 (8%) | 2 (2%) |
| Dizziness | 5 (5%) | 1 (1%) |
============================================================
```

Notice that **Section 16.2 Laboratory Findings** and its associated table (ALT / AST) are completely excluded.

---

## 8. Known Limitations & Extensibility

1. **Unnumbered Headings**: Documents using purely semantic headings without numerical prefixes (e.g., *"CLINICAL PROTOCOL"* without `"16."`) can be supported by adding custom regex dictionary patterns to `HeadingDetector.HEADING_REGEX`.
2. **Roman Numerals & Letters**: Sections formatted as `"Section XVI"` or `"Appendix B.1"` can be parsed by extending `canonicalize_section_number` to resolve Roman numerals or alphabetic tiers.
3. **Rotated / Vertical Text**: Multi-column landscape tables with 90-degree rotated headers should be normalized via PyMuPDF's page orientation rotation before table detection.
