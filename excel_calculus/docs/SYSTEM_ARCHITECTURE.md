# Pharmacovigilance Line-Listing Calculus & Safety Concern Platform: System Architecture

## 1. Executive Summary & Design Philosophy
The **Excel Calculus &bull; PV Safety Concern Platform** replaces the manual, error-prone spreadsheet manipulations (Power Query, split columns, custom formulas, VLOOKUP, manual cross-sheet copying) performed by safety reviewers during Periodic Benefit-Risk Evaluation Report (PBRER) preparation, specifically for **Section 16.3 (Summary of Safety Concerns)** and **Section 9 (Worldwide Non-Marketed & Marketed Safety Data)**.

### Core Architectural Axioms
1. **Ingest Once &rarr; Search Many Times**: Large workbooks (10,000+ cases) are ingested, cleaned, exploded, and indexed into relational tables once. Subsequent safety concern searches execute in milliseconds against indexed relational and text tables rather than repeatedly reading massive `.xlsx` files from disk.
2. **Deterministic Medical Reference Matching**: Core pharmacovigilance safety searches are deterministic queries against official MedDRA SMQ terminology (64,410 terms) and configured PT lists. No non-deterministic LLM black box is used for medical matching.
3. **Multi-Event Explosion with 100% Traceability**: A single line listing row may contain multiple adverse events bundled inside the `Event Verbatim` column. The calculus engine explodes these into $N$ distinct `CaseEvent` entities while preserving raw formatting, brackets, position index, and exact source lineage (`raw_source_file`, `raw_source_sheet`, `raw_source_row`).
4. **Distinct Case Count vs Event Match Count**: Clear separation between event matches (e.g. 21 medication error events) and distinct candidate cases (14 distinct cases), preventing over-counting in safety reports.
5. **Human-in-the-Loop Clinical Assessment**: An event match establishes a *candidate* case. The platform provides a full Case Review modal with patient history, products, exploded events, and narrative, allowing reviewers to record formal regulatory relevance assessments (`RELEVANT`, `NOT_RELEVANT`, `NEEDS_REVIEW`) and secondary clinical assessments.

---

## 2. System Architecture Diagram

```
+-----------------------------------------------------------------------------------------+
|                                    PRESENTATION LAYER                                   |
|   React + TypeScript + Vite Enterprise PV Dashboard (Responsive, Glassmorphic, Modern)  |
|                                                                                         |
|   +-----------------------+  +---------------------------+  +-------------------------+ |
|   | Evaluation Workspace  |  | PBRER Section 16.3 Report |  |  Data Pipeline Status   | |
|   | - Product Selector    |  | - Regulatory Narrative    |  |  - Ingestion Metrics    | |
|   | - Safety Concern Drop |  | - Case Counts & Metrics   |  |  - Indexed Cases        | |
|   | - Search Criteria Bar |  | - PT Distribution Table   |  |  - Exploded Event Count | |
|   | - Candidate Table     |  | - Export & Copy Action    |  |  - Source File Tracker  | |
|   +-----------------------+  +---------------------------+  +-------------------------+ |
|                                           |                                             |
|                               +-----------v-----------+                                 |
|                               |   Case Detail Modal   |                                 |
|                               | - Complete Overview   |                                 |
|                               | - Patient Demographics|                                 |
|                               | - Suspect Products    |                                 |
|                               | - Exploded Events     |                                 |
|                               | - Narrative & Lineage |                                 |
|                               | - Relevance Assessment|                                 |
|                               +-----------------------+                                 |
+-------------------------------------------|---------------------------------------------+
                                            | REST API (HTTP / JSON)
+-------------------------------------------v---------------------------------------------+
|                                   APPLICATION API LAYER                                 |
|                              FastAPI (Uvicorn / Python 3.9+)                            |
|                                                                                         |
|  - /api/ingestion/status      : Storage and file ingestion telemetry                    |
|  - /api/concerns              : Configured safety concerns by product                   |
|  - /api/search/{concern_id}   : Deterministic search execution & summary                |
|  - /api/cases/{case_number}   : Deep complete case inspection with exploded events      |
|  - /api/assessment            : Clinical relevance & secondary assessment updates       |
|  - /api/reports/pbrer/{id}    : PBRER Section 16.3 report generation                    |
+-------------------------------------------|---------------------------------------------+
                                            |
+-------------------------------------------v---------------------------------------------+
|                                     DOMAIN SERVICES                                     |
|                                                                                         |
|  +------------------------+  +------------------------+  +---------------------------+  |
|  |   Ingestion Engine     |  |   SearchEngineService  |  |   ReportService           |  |
|  | - OpenPyXL Streaming   |  | - BROAD_SMQ Matching   |  | - Table 16.3 Aggregator   |  |
|  | - Hex Sanitization     |  | - NARROW_SMQ Matching  |  | - PT Distribution Counter |  |
|  | - Event Verbatim Split |  | - SOC Filter           |  | - Clinical Narrative Text |  |
|  | - Product Normalization|  | - MULTIPLE_PTS Match   |  | - Line-Listing Exporter   |  |
|  | - Source Lineage Store |  | - NARRATIVE Text Scan  |  +---------------------------+  |
|  +------------------------+  | - Secondary Concomitant|                                 |
|                              +------------------------+                                 |
+-------------------------------------------|---------------------------------------------+
                                            | SQLAlchemy ORM
+-------------------------------------------v---------------------------------------------+
|                                    PERSISTENCE LAYER                                    |
|                             SQLite (Relational Database)                                |
|                                                                                         |
|  - case_records       : Case master (case_number, patient, seriousness, outcome, lineage) |
|  - case_events        : Exploded adverse events (normalized_term, PT, raw_verbatim, pos)|
|  - case_products      : Suspect and concomitant medications                             |
|  - safety_concerns    : Regulatory search specifications & concern definitions          |
|  - smq_terms          : MedDRA SMQ Version 29.0 reference hierarchy (64,410 terms)     |
|  - search_matches     : Deterministic event-level match audit records                   |
|  - relevance_assess   : Reviewer clinical relevance, exclusion reasons, notes           |
|  - audit_logs         : Comprehensive chronological reviewer audit trail                |
+-----------------------------------------------------------------------------------------+
```

---

## 3. The Multi-Event Normalization & Explosion Calculus

In pharmacovigilance interval line listings, adverse events are often packed together inside a single cell:
```
[PAIN IN EXTREMITY]
Y / Y / Y
[GAIT DISTURBANCE]
Y / Y / Y
[BONE PAIN]
Y / Y / Y
```

### Transformation Pipeline
1. **Raw String Sanitization**: Remove Excel hex-encoded XML artifacts (`_x0015_`, `_x0016_`, `_x000D_`) and carriage returns (`\r\n` &rarr; `\n`).
2. **Bracket Parsing**: Identify bracketed event terms `\[([^\]]+)\]`.
3. **Delimiter Fallback**: If bracketed terms are absent, fall back to line breaks (`\n`) and commas (reproducing the Power Query *Split Column by Delimiter* transformation observed in the Nilima recording).
4. **Noise & Marker Filtering**: Strip `Y / Y / Y` assessment markers, trailing punctuation, and non-printable characters.
5. **Whitespace Normalization**: Trim leading/trailing whitespace and collapse internal duplicate spaces.
6. **Relational Explosion**:
   - Create one `CaseEvent` row per extracted event.
   - Record `position` (1, 2, 3...) to preserve chronological/reporting order.
   - Store both `raw_verbatim` (unmodified original) and `normalized_term` (uppercase cleaned).
   - Retain full source lineage (`raw_source_file`, `raw_source_sheet`, `raw_source_row`).

---

## 4. MedDRA SMQ Reference Architecture

The MedDRA SMQ 29.0 reference spreadsheet (`SMQ_spreadsheet_29_0_English.xlsx`) contains hierarchical groupings:
- **Level 1 SMQ**: Identified by column positioning (Column B, 5-level indent).
- **Sub-SMQs (Level 2+)**: Nested hierarchical definitions.
- **Child Preferred Terms (PTs)**: Specific adverse reaction terms with assigned Scope (`Broad` or `Narrow`).
- **Hierarchy Resolution**:
  The `SMQLoader` traverses the 64,410 rows, maintains parent-child SMQ context stacks, and indexes:
  - `smq_name`: Standardized SMQ Name (e.g. `Drug related hepatic disorders - comprehensive search (SMQ)`)
  - `term_name`: Preferred Term / LLT / HLT
  - `term_code`: MedDRA Code
  - `scope`: `Broad` or `Narrow`
  - `term_type`: `PT`, `LLT`, `HLT`

---

## 5. Safety Concern Search Engine

The `SearchEngineService` implements 9 search methods configured as declarative JSON data:

| Search Method | Logic | Example Concern |
| :--- | :--- | :--- |
| `BROAD_SMQ` | Matches events against all Broad & Narrow terms in the configured SMQ | Hepatotoxicity, Medication error |
| `NARROW_SMQ` | Matches events strictly against Narrow scope terms in the SMQ | Rhabdomyolysis / Myopathy |
| `SOC` | Matches events where the Primary SOC equals the configured organ class | Cardiac Disorders |
| `SINGLE_PT` | Exact match against a single designated Preferred Term | Allergic alveolitis (`Alveolitis`) |
| `MULTIPLE_PTS` | Exact match against an enumerated set of Preferred Terms | Cataract, Accidental exposure, Off-label use |
| `NARRATIVE` | Keyword & regex substring search within Case Narrative and Comments | Safety and efficacy in long-term use |
| `SECONDARY_CONCOMITANT` | PT match combined with inspection of concomitant medication list | Drug-drug interaction with CYP2D6 inhibitors |
| `STRUCTURED_FIELD` | Search across structured patient fields (e.g. death cause, age group) | Fatal Outcomes, Pediatric Off-Label |
| `COMBINED` | Boolean combinations of SMQ and narrative terms | Complex risk evaluations |

### Match Explanation (Why Matched)
Every result record includes:
- `matched_field`: The exact case or event field (e.g. `Event Preferred Term`, `Case Narrative`)
- `matched_term`: The medical term that triggered the match
- `reference_source`: The exact SMQ name, SOC, or PT rule
- `evidence`: The verbatim passage or text snippet containing the match

---

## 6. Review Workflow & Assessment States

A candidate match is never assumed to be a final confirmed case:
```
RAW LINE LISTING 
  ──> INGESTION & EVENT EXPLOSION 
    ──> DETERMINISTIC SEARCH 
      ──> CANDIDATE MATCHES (Pending Review)
        ──> CASE DETAIL REVIEW (Clinical Inspection)
          ──> RELEVANCE ASSESSMENT:
                [ RELEVANT ]       --> Included in PBRER Section 16.3 Table & Counts
                [ NOT_RELEVANT ]   --> Excluded with Mandatory Clinical Justification
                [ NEEDS_REVIEW ]   --> Flagged for Physician Second Opinion
```

---

## 7. Performance & Scalability
- **Streaming Ingestion**: `openpyxl` with `read_only=True` avoids loading massive DOM trees into memory.
- **Indexed Relational Storage**: `case_number`, `product_name`, and `normalized_term` have B-Tree indices in SQLite/PostgreSQL.
- **Sub-Second Queries**: Running a Broad SMQ search across 1,000+ events and 64,410 reference terms executes in ~40ms.
- **Asynchronous Architecture**: Production deployments can bind `Celery` + `Redis` for background ingestion tasks without altering the domain services.
