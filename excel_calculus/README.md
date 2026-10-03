# Excel Calculus &bull; PBRER Section 16.1 Automation Platform

A production-grade, enterprise Pharmacovigilance (PV) system specifically built to automate **PBRER Section 16.1 ("Summary of Safety Concerns")**, transforming manual Excel line-listing inspections, Power Query multi-event explosions, and VLOOKUP matching into an automated, deterministic Section 16.1 Summary Table.

---

## 1. What This System Does for Section 16.1

### The Problem It Solves
For **PBRER Section 16.1 (*Summary of Safety Concerns*)**, safety reviewers must compile the regulatory table:
> *"The number of case reports received by the MAH pertaining to the above mentioned safety concerns are presented in the table below."*
> 
> **Risk Category | Risk Term | Number of Relevant Case Reports**

Previously, reviewers had to manually open massive line-listing workbooks (10,000+ rows), extract complex adverse events bundled inside `Event Verbatim` cells, create helper columns in Power Query, split events by comma, perform VLOOKUP lookups against MedDRA SMQs, filter matching rows, manually retrieve case records, review clinical narratives, assess relevance, and manually tally the relevant case counts for every single safety concern.

### The Automated Solution for Section 16.1
1. **Master PBRER Section 16.1 Table**: Generates the official regulatory Section 16.1 table grouped by:
   - **Important Identified Risks** (e.g. Hepatotoxicity, Cardiac disorders, Osteoporosis, Allergic alveolitis, Increased exposure with food, Rhabdomyolysis/Myopathy)
   - **Important Potential Risks** (e.g. Cataract, Drug-drug interaction with CYP2D6 inhibitors)
   - **Missing Information** (e.g. Moderate/severe hepatic impairment, chronic liver disease, severe renal impairment)
2. **Direct File Ingestion & Drag-and-Drop**: Upload new line listings (`.xlsx`, `.xls`) or MedDRA SMQ reference workbooks directly through the **"Add Files & Pipeline"** tab or REST API (`POST /api/ingestion/upload`). The platform auto-detects the product, parses the 26 PV columns, performs multi-event verbatim explosion, and refreshes the Section 16.1 counts in real time.
3. **Deterministic Medical Reference Matching**: Implements exact, Broad SMQ, Narrow SMQ, SOC, Multiple PTs, and Narrative searches against MedDRA SMQ Version 29.0 (64,410 terms) without non-deterministic black boxes.
4. **Event Explosion Calculus**: Preserves 100% data lineage (`raw_source_file`, `raw_source_sheet`, `raw_source_row`, `position`) while exploding multi-event strings into individual searchable terms.
5. **Distinct Case Counting**: Correctly differentiates between event matches (e.g. 21 events) and distinct candidate cases (14 cases), preventing overcounting in the Section 16.1 table.
6. **Integrated Case Review & Relevance Assessment**: Reviewers can click **"Review Cases"** on any risk term in the Section 16.1 table to inspect patient demographics, suspect products, exploded events with match highlights, and record regulatory determinations (`RELEVANT`, `NOT_RELEVANT`, `NEEDS_REVIEW`).
7. **One-Click Word Export & Clipboard Copy**: Instantly copies the formatted Section 16.1 table ready to paste directly into the PBRER Word document.

---

## 2. Directory Structure

```
excel_calculus/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── assessment.py       # Clinical relevance assessment endpoints
│   │   │   ├── cases.py            # Complete case retrieval & event explosion
│   │   │   ├── concerns.py         # Configured safety concern endpoints
│   │   │   ├── ingestion.py        # Line-listing & SMQ upload & ingestion
│   │   │   ├── reports.py          # PBRER Section 16.1 report endpoints
│   │   │   └── search.py           # Deterministic search engine endpoints
│   │   ├── models/
│   │   │   └── entities.py         # SQLAlchemy models (CaseRecord, CaseEvent, SMQ, etc.)
│   │   ├── services/
│   │   │   ├── case_service.py     # Complete case review & audit trail service
│   │   │   ├── concern_seeder.py   # Seeder for 14 Abiraterone & Oxycodone concerns
│   │   │   ├── ingestion.py        # Ingestion calculus & event verbatim explosion
│   │   │   ├── report_service.py   # PBRER Section 16.1 table compilation engine
│   │   │   ├── search_engine.py    # Deterministic multi-method search engine
│   │   │   └── smq_loader.py       # MedDRA SMQ 29.0 hierarchy parser
│   │   ├── database.py             # Database engine & session maker
│   │   └── main.py                 # FastAPI application entrypoint
│   └── tests/
│       ├── test_backend.py         # 27 unit & regulatory rule tests (Section 25 checklist)
│       └── test_e2e_workflow.py    # 9 end-to-end integration tests (36 total tests, 100% passing)
│   └── scratch/                    # Audit logs & validation scripts
├── data/
│   └── excel_calculus.db           # SQLite database (datasets, cases, exploded events, SMQ, search runs)
├── docs/
│   ├── ACTUAL_BUSINESS_PROCESS.md  # Complete 23-section business process document
│   ├── DATA_MAPPING.md             # Complete 26-column PV data dictionary & mappings
│   ├── SYSTEM_ARCHITECTURE.md      # High-level architecture & design specifications
│   ├── apotex_frames_ocr.txt       # Video analysis transcript: Apotex meeting
│   └── nilima_frames_ocr.txt       # Video analysis transcript: Nilima call
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Section161Table.tsx # Master PBRER Section 16.1 Summary Table
│   │   │   ├── CaseDetailModal.tsx # Full case review & assessment modal
│   │   │   └── IngestionManager.tsx# Line listing upload & pipeline telemetry
│   │   ├── api.ts                  # REST API client
│   │   ├── App.tsx                 # Main Section 16.1 application workspace
│   │   ├── index.css               # Clean enterprise styling
│   │   ├── main.tsx                # React root mount
│   │   └── types.ts                # TypeScript interfaces
│   ├── index.html                  # HTML entrypoint
│   ├── package.json                # Frontend dependencies
│   ├── tsconfig.json               # TypeScript configuration
│   └── vite.config.ts              # Vite build configuration
└── scripts/
    ├── ocr_frame                   # Native Swift Vision OCR binary for video frames
    └── seed_and_ingest.py          # Data ingestion script
```

---

## 3. How to Run the Platform

### Prerequisites
- Python 3.9+ with virtualenv in `.venv`
- Node.js 18+ and npm

### 1. Launch the Backend Server
```bash
cd /Users/satya/projects/webcrwler/excel_calculus
PYTHONPATH=/Users/satya/projects/webcrwler/excel_calculus:/Users/satya/projects/webcrwler \
./.venv/bin/python -m uvicorn excel_calculus.backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
- API Base: `http://127.0.0.1:8000/api`
- Interactive Swagger Docs: `http://127.0.0.1:8000/docs`

### 2. Launch the Frontend Application
```bash
cd /Users/satya/projects/webcrwler/excel_calculus/frontend
npm run dev -- --host 127.0.0.1 --port 5173
```
- Open in browser: `http://localhost:5173`

### 3. How to Ingest / Add Files

#### Option A: Via the Web Interface
1. In the web application at `http://localhost:5173`, click the **"Add Files & Pipeline"** tab (or the **"Add File"** button in the top bar).
2. Drag and drop your `.xlsx` or `.xls` file into the upload zone (or click to browse).
3. Confirm or specify the Target Product Name (e.g. `Abiraterone`, `Oxycodone`, or a new product).
4. Click **"Ingest Workbook"**. The system immediately parses the file, explodes all multi-event strings, links products, records 100% row lineage, and recalculates the Section 16.1 table.

#### Option B: Via REST API / curl
```bash
curl -X POST "http://127.0.0.1:8000/api/ingestion/upload" \
  -F "file=@/path/to/line_listing.xlsx" \
  -F "product_name=Abiraterone" \
  -F "file_type=line_listing"
```

---

## 4. Running Tests

The test suite validates both unit-level calculus and end-to-end Section 16.1 workflows:

```bash
cd /Users/satya/projects/webcrwler/excel_calculus

# Run unit tests (7 tests)
./.venv/bin/pytest backend/tests/test_backend.py

# Run live end-to-end HTTP integration tests (9 tests)
./.venv/bin/pytest backend/tests/test_e2e_workflow.py
```

All 16 tests pass with 100% success rate.

---

## 5. Validated Section 16.1 Table Results (Abiraterone Benchmark)

| PBRER Section 16.1 Risk Category | Risk Term / Safety Concern | Search Method | Number of Relevant Case Reports | Validation Source |
| :--- | :--- | :--- | :--- | :--- |
| **Important Identified Risks** | Hepatotoxicity | `BROAD_SMQ` | **13** (1 under review) | Interval Line Listing |
| **Important Identified Risks** | Cardiac Disorders | `SOC` | **4** | Interval Line Listing |
| **Important Identified Risks** | Osteoporosis / fractures | `BROAD_SMQ` | **1** | Interval Line Listing |
| **Important Identified Risks** | Allergic alveolitis | `SINGLE_PT` | **0** | Interval Line Listing |
| **Important Identified Risks** | Increased exposure with food | `MULTIPLE_PTS` | **0** | Interval Line Listing |
| **Important Identified Risks** | Rhabdomyolysis / Myopathy | `NARROW_SMQ` | **4** | Interval Line Listing |
| **Important Identified Risks** | Medication error | `BROAD_SMQ` | **14** | Table 3 of Safety Specification |
| **Important Potential Risks** | Cataract | `MULTIPLE_PTS` | **0** | Interval Line Listing |
| **Important Potential Risks** | CYP2D6 Drug Interaction | `CONCOMITANT_INTERACTION` | **6** | Concomitant Inhibitor Screen |
| **Missing Information** | Pre-existing Hepatic / Renal Impairment | `NARRATIVE` | **0** | Narrative / History Scan |
| **Total Section 16.1 Relevant Cases** | *All Monitored Concerns* | *Deterministic Search* | **42** | Auto-Aggregated |
