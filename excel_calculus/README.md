# Excel Calculus &bull; PBRER Section 16.1 Automation Platform

A production-grade, enterprise Pharmacovigilance (PV) system built to automate **PBRER Section 16.1 ("Summary of Safety Concerns")** and generate formal, submission-ready regulatory PDF reports matching the official Apotex/Nilima pharmacovigilance documentation standards.

---

## 1. Business Workflow — Source of Truth

The platform automates the repetitive, manual Excel work of safety reviewers while strictly preserving human clinical judgement:

```
MEDDRA SMQ MASTER EXCEL (Source A)   +   PRODUCT LINE LISTING EXCEL (Source B)
                          ↓
                    Select Product
                          ↓
               Select Reporting Period
                          ↓
                Select Safety Concern
                          ↓
            Select Applicable Search Method
                          ↓
             Load Exact Reference Criteria
                          ↓
            Read Case Number + Event Verbatim
                          ↓
                   Clean Verbatim
                          ↓
              Remove Excel/XML Artifacts
                          ↓
       Explode Multiple Events into Separate Records
                          ↓
                Normalize Event Values
                          ↓
         Exact Lookup against Reference Terminology
                          ↓
                Candidate Event Matches
                          ↓
            Group by DISTINCT Case Number
                          ↓
            Open Complete Case Review Modal
                          ↓
               Review Clinical Narrative
                          ↓
            Secondary Assessment (e.g. CYP2D6)
                          ↓
       RELEVANT / NOT_RELEVANT / NEEDS_REVIEW
                          ↓
         COUNT DISTINCT RELEVANT CASE NUMBERS
                          ↓
       Section 16.1 PBRER Safety Concern Table
                          ↓
             Generate Submission-Ready PDF
```

---

## 2. Core Architectural Principles & Fixes

### A. Case Identity & Dataset Isolation
- `CaseRecord` uses an internal auto-increment integer `id` as its primary key, with a composite unique constraint `(dataset_id, case_number)`.
- The same case number can exist across different reporting periods or products without primary key collisions.
- Child tables (`CaseEvent`, `CaseProduct`, `SearchMatch`, `RelevanceAssessment`, `AuditLog`) link to the internal `case_id`.

### B. Non-Destructive Search Run History
- Re-executing a safety concern search does **not** wipe out historical `SearchMatch` records.
- Each execution creates a new `SearchRun` record and deactivates prior runs (`is_active = False`) while preserving all historical match linkages for regulatory audits.

### C. Re-Ingestion Reconciliation
- Re-uploading an existing line listing reconciles cases using file hashes and dataset identity rather than blind deletion/re-insertion.
- Clinical review assessments (`RelevanceAssessment`) and reviewer notes are preserved across re-ingestions.

### D. Complete Product Information
- Extracts suspect and concomitant products from source columns:
  - `brand_name`, `active_substance`, `role` (Suspect vs Concomitant)
  - `daily_dose` (Column 8), `form` (Column 9), `duration` (Column 10), `indication_pt` (Column 20)

### E. Event Onset & Positional Mapping
- Parses `Event Onset` (Column 11).
- Single-event rows have `CONFIRMED` onset association.
- Multi-event cells where onsets are listed sequentially are mapped by positional order and flagged with:
  `[UNCERTAIN — REQUIRES VERIFICATION: Multi-event onset mapped sequentially by position]`.
  The system never invents associations.

### F. Deterministic Medical Term Matching
- Core regulatory lookup is strictly deterministic:
  $$\text{Normalized Event} \longrightarrow \text{Exact Uppercase Lookup} \longrightarrow \text{MedDRA PT / PT Code / SMQ Scope}$$
- No non-deterministic LLMs or fuzzy string matches are used for the authoritative regulatory lookup.

### G. Candidate vs. Relevant Regulatory Logic
- Candidate matches $\neq$ Relevant cases.
- Final regulatory count for Section 16.1:
  $$\text{Relevant Case Count} = \text{COUNT}(\text{DISTINCT } \text{case\_number}) \quad \text{WHERE assessment.status} = \text{'RELEVANT'}$$
- Candidate cases, excluded cases (`NOT_RELEVANT`), and cases pending review (`NEEDS_REVIEW`) are never counted in the official regulatory total.

### H. Official Table vs. Reviewer View & Total Row Rule
- Per **Requirement 18**, the official Section 16.1 regulatory table does **NOT** display a Total row across concerns, because individual cases can pertain to multiple safety concerns and summing across concerns leads to misleading double-counting.
- Internal analytical metrics are provided in the Reviewer View and KPI summary cards.
- Section 9 "Medication error" is excluded from the Section 16.1 table (which strictly contains 13 official concerns across Important Identified Risks, Important Potential Risks, and Missing Information).

---

## 3. Real PBRER PDF Generation Service

The system includes a dedicated backend PDF Report service (`excel_calculus.backend.app.services.pdf_service.PDFReportService`) utilizing `ReportLab`:
- **Page Size**: A4 portrait with standard 0.75-inch margins.
- **Typography**: Formal Times-Roman serif typography matching regulatory submissions.
- **Page Header**: Repeating header across all pages:
  `Apotex Inc.` | `{Product Name}`
  `Periodic Benefit-Risk Evaluation Report / Periodic Safety Update Report`
- **Page Footer**: Repeating footer with rule line:
  `CONFIDENTIAL` | `Page X of Y` (two-pass `NumberedCanvas`).
- **Table Visuals**: Strict 2-column table (`Risk Term` 72% | `Number of Relevant Case Reports` 28%), thin black borders, clean padding, bold category header rows, and vertically aligned numeric counts.
- **Pagination**: Repeated table headers across page breaks (`repeatRows=1`).
- **Substantiated Data**: Followed by Section 16.2 and Section 16.3 headings with non-fabricated data summaries.

### PDF Endpoints
- **Download PDF**: `GET /api/reports/section-16-1/pdf?product={product}`
  Returns `Content-Disposition: attachment; filename="{product}_Section_16.1_PBRER_Report.pdf"`
- **Inline Preview**: `GET /api/reports/section-16-1/pdf?product={product}&preview=true`
  Returns `Content-Disposition: inline` for modal viewing.

---

## 4. Database Migrations

To upgrade existing SQLite databases without data loss or corruption, run the migration script:

```bash
cd excel_calculus
./.venv/bin/python scripts/migrate_database.py
```

The script:
1. Automatically creates a timestamped backup: `excel_calculus.db.backup_YYYYMMDD_HHMMSS`.
2. Upgrades `case_records` to an auto-increment integer PK `id` with composite uniqueness on `(dataset_id, case_number)`.
3. Adds `case_id` foreign keys to child tables (`case_events`, `case_products`, `search_matches`, `relevance_assessments`, `audit_logs`).
4. Adds `onset_mapping_status`, `is_active`, and `dataset_id` columns.
5. Backfills existing data relationships.

---

## 5. Directory Structure

```
excel_calculus/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── assessment.py       # Clinical relevance assessment endpoints
│   │   │   ├── cases.py            # Case retrieval & event explosion
│   │   │   ├── concerns.py         # Configured safety concern endpoints
│   │   │   ├── ingestion.py        # Line-listing & SMQ upload & ingestion
│   │   │   ├── reports.py          # PBRER Section 16.1 & PDF report endpoints
│   │   │   └── search.py           # Deterministic search engine endpoints
│   │   ├── models/
│   │   │   └── entities.py         # SQLAlchemy models (CaseRecord, CaseEvent, SMQ, etc.)
│   │   ├── services/
│   │   │   ├── case_service.py     # Complete case review & audit trail service
│   │   │   ├── concern_seeder.py   # Seeder for 14 safety concerns
│   │   │   ├── ingestion.py        # Ingestion calculus & event verbatim explosion
│   │   │   ├── pdf_service.py      # ReportLab A4 PBRER PDF renderer
│   │   │   ├── report_service.py   # PBRER Section 16.1 table compilation engine
│   │   │   ├── search_engine.py    # Deterministic multi-method search engine
│   │   │   └── smq_loader.py       # MedDRA SMQ 29.0 hierarchy parser
│   │   ├── database.py             # Database engine & session maker
│   │   └── main.py                 # FastAPI application entrypoint
│   └── tests/
│       ├── test_backend.py         # 31 unit & calculus tests
│       └── test_e2e_workflow.py    # 11 end-to-end integration tests (42 total tests)
├── data/
│   ├── excel_calculus.db           # SQLite database
│   ├── Abiraterone_...xlsx         # Abiraterone benchmark interval line listing
│   └── Oxycodone_...xlsx           # Oxycodone benchmark line listing
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Section161Table.tsx # PBRER Section 16.1 table with PDF preview/download
│   │   │   ├── CaseDetailModal.tsx # Full case review & assessment modal
│   │   │   └── IngestionManager.tsx# Line listing upload & pipeline telemetry
│   │   ├── api.ts                  # REST API client
│   │   ├── App.tsx                 # Main Section 16.1 application workspace
│   │   └── types.ts                # TypeScript interfaces
│   └── vite.config.ts              # Vite build configuration
└── scripts/
    ├── migrate_database.py         # Safe SQLite migration script
    └── seed_and_ingest.py          # Data ingestion script
```

---

## 6. How to Run the Platform

### 1. Launch Backend Server
```bash
cd excel_calculus
PYTHONPATH=. ./.venv/bin/python -m uvicorn excel_calculus.backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
- API Base: `http://127.0.0.1:8000/api`
- Interactive Swagger: `http://127.0.0.1:8000/docs`
- Direct PDF Download: `http://127.0.0.1:8000/api/reports/section-16-1/pdf?product=Abiraterone`

### 2. Launch Frontend Application
```bash
cd excel_calculus/frontend
npm run dev -- --host 127.0.0.1 --port 5173
```
- Web Application: `http://localhost:5173`

---

## 7. Running Portable Automated Tests

The test suite contains zero hard-coded machine paths and dynamically resolves files using relative paths and environment variable overrides:

```bash
cd excel_calculus
./.venv/bin/pytest backend/tests/test_backend.py backend/tests/test_e2e_workflow.py -v
```

### Exact Test Execution Output
```
============================== 42 passed in 1.12s ==============================
```
- **31 Unit & Calculus Tests (`test_backend.py`)**:
  - SMQ 29.0 master loading (48,809 terms)
  - Broad (334 PTs) vs. Narrow (269 PTs) scope resolution
  - Event verbatim cleaning, XML artifact removal, Y/Y/Y stripping
  - Exact uppercase lookup matching
  - Distinct case grouping
  - Reviewer assessment state transitions (`CANDIDATE` $\to$ `RELEVANT`)
  - Source lineage tracking
  - Re-ingestion without case duplication
  - Real PDF generation and text validation using `pypdf`
  - Non-destructive search run history
  - Dataset isolation composite identity
  - Event onset mapping and product fields population
- **11 End-to-End Integration Tests (`test_e2e_workflow.py`)**:
  - Data pipeline status
  - Concern search execution
  - Complete case review modal payload
  - Relevance assessment update
  - Section 16.1 summary table generation
  - Cross-product Oxycodone validation
  - File upload ingestion API
  - PDF report download API (`200 OK`, `application/pdf`, `%PDF-1.4`)
  - PDF report preview API (`inline` disposition)

---

## 8. Abiraterone Benchmark & Validation Results

Evaluated against the official interval line listing (`119 case rows`, `225 exploded events`):

| PBRER Section 16.1 Risk Category | Risk Term / Safety Concern | Search Method | Candidate Cases | Confirmed Relevant Cases |
| :--- | :--- | :--- | :---: | :---: |
| **Important Identified Risks** | Hepatotoxicity | `BROAD_SMQ` | 14 | **1** *(Case 2025AP034387)* |
| **Important Identified Risks** | Cardiac disorders | `SOC` | 0 | **0** |
| **Important Identified Risks** | Osteoporosis including osteoporosis-related fractures | `BROAD_SMQ` | 1 | **0** |
| **Important Identified Risks** | Allergic alveolitis | `SINGLE_PT` | 0 | **0** |
| **Important Identified Risks** | Increased exposure with food | `MULTIPLE_PTS` | 0 | **0** |
| **Important Identified Risks** | Rhabdomyolysis/Myopathy | `NARROW_SMQ` | 4 | **0** |
| **Important Potential Risks** | Cataract | `MULTIPLE_PTS` | 0 | **0** |
| **Important Potential Risks** | Drug drug interaction with CYP2D6 inhibitors | `CONCOMITANT_INTERACTION` | 6 | **0** |
| **Important Potential Risks** | Overdose due to medication error | `MULTIPLE_PTS` | 1 | **0** |
| **Missing Information** | Use in patients with moderate/severe hepatic impairment... | `MULTIPLE_PTS` | 0 | **0** |
| **Missing Information** | Use in patients with severe renal impairment | `MULTIPLE_PTS` | 2 | **0** |
| **Missing Information** | Use in patients with heart disease as specified in SmPC | `MULTIPLE_PTS` | 0 | **0** |
| **Missing Information** | Use in patients with baseline hepatitis or abnormalities... | `MULTIPLE_PTS` | 0 | **0** |

*Note: In accordance with regulatory requirements, Candidate cases are only counted as Relevant once a clinical reviewer conducts a narrative review and assigns `status = 'RELEVANT'`.*

---

## 9. Limitations & Verification Notes

The following items are marked as requiring verification where source data does not provide unambiguous evidence:
1. `[UNCERTAIN — REQUIRES VERIFICATION: Multi-event onset mapped sequentially by position]`: In cells containing multiple onset dates and multiple event verbatims, dates are mapped in positional order.
2. `[UNCERTAIN — REQUIRES VERIFICATION: CYP2D6 Target List Versioning]`: Concomitant CYP2D6 interactions are screened against a curated, configurable substrate/inhibitor dictionary. Final interaction relevance requires clinical review.
3. `[UNCERTAIN — REQUIRES VERIFICATION: Section 16.2 / 16.3 Narrative Content]`: Section 16.2 signal evaluations and 16.3 clinical discussions are derived strictly from confirmed database records. Regulatory narrative prose is never fabricated.
