#!/usr/bin/env python3
"""
Master Architecture Asset Builder.
Renders all 13 required diagrams into:
- docs/architecture/diagrams/*.mmd
- docs/architecture/images/*.svg
- docs/architecture/images/*.png
"""
import os
import sys
import time
import base64
import urllib.request
import urllib.error
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DIAGRAMS_DIR = WORKSPACE_ROOT / "docs" / "architecture" / "diagrams"
IMAGES_DIR = WORKSPACE_ROOT / "docs" / "architecture" / "images"

DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

DIAGRAMS = {}

# 01 - System Architecture
DIAGRAMS["01-system-architecture"] = """flowchart TD
    User([User / Web Browser / API Client]) --> PresentationLayer

    subgraph PresentationLayer ["1. Presentation Layer"]
        UI["Medicine Safety Web Dashboard<br/>(app/ui.py - Glassmorphic SSR HTML/CSS/JS)"]
        PDFUI["PDF Extractor Dashboard<br/>(pdf_extractor/frontend - HTML/JS/CSS)"]
    end

    PresentationLayer --> APILayer

    subgraph APILayer ["2. Application & API Layer (FastAPI)"]
        MainApp["Medicine Safety API<br/>(app/main.py: Port 8000)"]
        DrugsRouter["Drugs Router<br/>(app/api/drugs.py)"]
        SafetyRouter["Safety Changes Router<br/>(app/api/safety_changes.py)"]
        AdminRouter["Admin Router<br/>(app/api/admin.py)"]
        PDFApp["PDF Extractor API<br/>(pdf_extractor/backend/main.py: Port 8001)"]
        ExtractionRouter["Extraction Router<br/>(backend/api/extraction.py)"]
        UploadRouter["Upload Router<br/>(backend/api/upload.py)"]
        
        MainApp --> DrugsRouter
        MainApp --> SafetyRouter
        MainApp --> AdminRouter
        PDFApp --> ExtractionRouter
        PDFApp --> UploadRouter
    end

    APILayer --> ServiceLayer

    subgraph ServiceLayer ["3. Core Services & Normalization Layer"]
        DBService["DatabaseService<br/>(app/services/database_service.py)"]
        NormService["NormalizationService<br/>(app/services/normalization.py)"]
        ValidService["ValidationService<br/>(app/services/validation.py)"]
        ChangeService["ChangeDetectionService<br/>(app/services/change_detection.py - SHA-256)"]
        CacheService["CacheService<br/>(app/services/cache.py)"]
        ExportService["ExportService<br/>(app/ui.py - CSV & JSON Generation)"]
    end

    APILayer --> Orchestrator

    subgraph Orchestrator ["4. Concurrent Ingestion Coordinator (asyncio.gather)"]
        AsyncGather{"asyncio.gather parallel tasks<br/>4.0s Timeout Ceiling & Error Isolation"}
    end

    Orchestrator --> RegulatoryAdapters

    subgraph RegulatoryAdapters ["5. Regulatory Source Adapters & Crawlers"]
        FDAEngine["FDA SrLC Crawler & Scraper<br/>(app/crawler/fda_crawler.py<br/>app/scrapers/fda_srlc_scraper.py)"]
        HCEngine["Health Canada DPD & InfoWatch<br/>(app/sources/health_canada/dpd_crawler.py<br/>infowatch/adapter.py)"]
        TGAEngine["Australia TGA Adapter & Crawler<br/>(app/sources/australia_tga/adapter.py<br/>tga_crawler.py)"]
        MWEngine["FDA MedWatch Adapter & Crawler<br/>(app/sources/fda_medwatch/adapter.py<br/>medwatch_crawler.py)"]
        MHRAEngine["UK MHRA Adapter & Crawler<br/>(app/sources/uk_mhra/adapter.py<br/>mhra_crawler.py)"]
    end

    RegulatoryAdapters --> ExternalWebsites

    subgraph ExternalWebsites ["6. External Regulatory Portals (The 5 Sources)"]
        ExtFDA["US FDA SrLC Portal<br/>(accessdata.fda.gov)"]
        ExtHC["Health Canada DPD & InfoWatch<br/>(health-products.canada.ca)"]
        ExtTGA["Australia TGA Portal<br/>(www.tga.gov.au/search)"]
        ExtMW["FDA MedWatch & openFDA<br/>(fda.gov/safety/medwatch & api.fda.gov)"]
        ExtMHRA["UK MHRA Drug Safety Update<br/>(www.gov.uk/drug-safety-update)"]
    end

    FDAEngine -.->|ASPX Form POST| ExtFDA
    HCEngine -.->|DPD API & Scrape| ExtHC
    TGAEngine -.->|Akamai-Resilient GET| ExtTGA
    MWEngine -.->|openFDA JSON & RSS| ExtMW
    MHRAEngine -.->|JSON API & ATOM| ExtMHRA

    HCEngine -->|HTTP POST /api/extract| PDFSubsystem

    subgraph PDFSubsystem ["7. Intelligent PDF/Document Extraction Subsystem"]
        SecExtractor["SectionExtractor<br/>(pdf_extractor/backend/extraction/)"]
        PDFReader["PDFReader & Layout Engine<br/>(PyMuPDF fitz)"]
        OCREngine["OCRDetector & Tesseract Fallback<br/>(pdf/ocr.py)"]
        HeadingDet["HeadingDetector<br/>(pdf/headings.py)"]
        TableExt["TableExtractor<br/>(pdfplumber graphical tables)"]
        BoundaryDet["BoundaryDetector<br/>(Coordinate-level Sibling Cutoff)"]

        SecExtractor --> PDFReader
        PDFReader --> HeadingDet
        HeadingDet --> TableExt
        TableExt --> BoundaryDet
        PDFReader -.->|Low Text Density| OCREngine
    end

    ServiceLayer --> PersistenceLayer
    PDFSubsystem --> PersistenceLayer

    subgraph PersistenceLayer ["8. Persistence Layer (SQLite Relational Databases)"]
        DBMain[("medicine_safety.db<br/>(drugs, safety_labeling_changes,<br/>safety_change_versions, crawl_runs)")]
        DBExtractor[("extractor.db<br/>(documents, extractions,<br/>content_blocks)")]
    end

    DBService --> DBMain
    PDFSubsystem --> DBExtractor
"""

# 02 - End-to-End Data Flow
DIAGRAMS["02-end-to-end-data-flow"] = """flowchart TD
    Start([User submits Search Query: Ozempic]) --> Step1[1. Clean and Normalize Query<br/>NormalizationService.normalize_drug_name]
    Step1 --> Step2[2. Check Local Database Cache<br/>DatabaseService.search_drugs]
    Step2 --> Decision1{"Cached records exist<br/>and fresh within 24h?"}

    Decision1 -->|YES| ReturnCache[Return Cached Records<br/>Response latency under 15ms]
    Decision1 -->|NO or Force Refresh| Step3[3. Evaluate Source Parameter<br/>source=ALL or specific authority]

    Step3 --> Step4[4. Launch Concurrent Crawling Tasks<br/>asyncio.gather with return_exceptions=True]

    subgraph ParallelCrawl ["5. Parallel Ingestion Streams"]
        direction TB
        Stream1["FDA Crawler: ASPX POST searchResult.page<br/>Extract candidate detail URLs"]
        Stream2["Health Canada: DPD API query + InfoWatch discovery<br/>Fetch monographs and advisories"]
        Stream3["Australia TGA: Search keywords endpoint<br/>Extract AUST R/L and PI/CMI links"]
        Stream4["FDA MedWatch: openFDA FAERS REST query<br/>Ingest adverse events and Class I/II recalls"]
        Stream5["UK MHRA: Query GOV.UK JSON search endpoint<br/>Extract PL/PLGB licences and CHM advice"]
    end

    Step4 --> Stream1
    Step4 --> Stream2
    Step4 --> Stream3
    Step4 --> Stream4
    Step4 --> Stream5

    Stream2 -.->|Discovers Monograph PDF Link| PDFRouting{PDF link present?}
    PDFRouting -.->|YES| PDFCall["POST /api/extract to PDF Extractor<br/>Timeout: 120s"]
    PDFCall -.-> PDFExtract["Extract structured sections and tables<br/>Append PDF content to advisory"]
    PDFCall -.->|Connection Error or Timeout| PDFFallback["Fallback gracefully to HTML content"]

    Stream1 --> Step6["6. Ingestion into Canonical Dictionary<br/>dict: name, ingredient, app_num, source, changes"]
    Stream2 --> Step6
    Stream3 --> Step6
    Stream4 --> Step6
    Stream5 --> Step6
    PDFExtract --> Step6
    PDFFallback --> Step6

    Step6 --> Step7["7. Validate Record Structure<br/>ValidationService.validate_record"]
    Step7 --> Step8["8. Resolve and Upsert Drug Entity<br/>DatabaseService.insert_or_update_drug<br/>Unique Scope: source + drug_name"]

    Step8 --> Step9["9. Change Detection and Audit Log<br/>Compute SHA-256 Hash of content fields"]
    Step9 --> Decision2{"Content Hash<br/>differs from latest?"}

    Decision2 -->|YES| Step10["Create SafetyChangeVersion row<br/>Increment version_number by 1"]
    Decision2 -->|NO| Step11["Update last_verified_at timestamp"]

    Step10 --> Step12["10. Commit Database Transaction<br/>session.commit()"]
    Step11 --> Step12
    Step12 --> Step13["11. Format Output Payload<br/>SearchResultResponse / Glassmorphic UI HTML"]
    ReturnCache --> Step13
    Step13 --> End([Render Response to User / Client])
"""

# 03 - Five Regulatory Sources
DIAGRAMS["03-five-regulatory-sources"] = """flowchart TD
    Hub(["MEDICINE SAFETY MULTI-AUTHORITY PLATFORM<br/>(5 Global Regulatory Sources)"])

    Hub --> S1
    Hub --> S2
    Hub --> S3
    Hub --> S4
    Hub --> S5

    subgraph S1 ["1. US FDA SrLC"]
        S1_Name["Official: FDA Safety-related Labeling Changes (SrLC)"]
        S1_URL["URL: accessdata.fda.gov/scripts/cder/safetylabelingchanges"]
        S1_Code["Code: app/crawler/fda_crawler.py<br/>app/scrapers/fda_srlc_scraper.py"]
        S1_Proto["Protocol: HTTPS POST (ViewState session) + BeautifulSoup"]
        S1_Key["Key Identifier: NDA / BLA Application Number"]
        S1_Data["Data: Boxed Warnings, Warnings & Precautions, Adverse Reactions"]
    end

    subgraph S2 ["2. Health Canada"]
        S2_Name["Official: Drug Product Database (DPD) & Health Product InfoWatch"]
        S2_URL["URL: health-products.canada.ca/dpd-bdpp & recalls-rappels.canada.ca"]
        S2_Code["Code: app/sources/health_canada/dpd_crawler.py<br/>infowatch/adapter.py"]
        S2_Proto["Protocol: DPD REST API + InfoWatch Scraper + PDF Extractor"]
        S2_Key["Key Identifier: 8-digit Drug Identification Number (DIN)"]
        S2_Data["Data: Product Monographs, Marketed Status, Recall Advisories"]
    end

    subgraph S3 ["3. Australia TGA"]
        S3_Name["Official: Therapeutic Goods Administration (TGA)"]
        S3_URL["URL: www.tga.gov.au/search?keywords="]
        S3_Code["Code: app/sources/australia_tga/tga_crawler.py<br/>adapter.py"]
        S3_Proto["Protocol: HTTPS GET (Akamai-resilient browser headers)"]
        S3_Key["Key Identifier: ARTG Number (AUST R / AUST L)"]
        S3_Data["Data: Product Information (PI), Consumer Medicine Info (CMI), Alerts"]
    end

    subgraph S4 ["4. FDA MedWatch"]
        S4_Name["Official: FDA MedWatch Adverse Event Reporting Program"]
        S4_URL["URL: www.fda.gov/safety/medwatch & api.fda.gov/drug/event.json"]
        S4_Code["Code: app/sources/fda_medwatch/medwatch_crawler.py<br/>adapter.py"]
        S4_Proto["Protocol: openFDA FAERS REST API + MedWatch RSS XML feed"]
        S4_Key["Key Identifier: MW-FAERS-XXXXXX / MW-RECALL-XXXXXX"]
        S4_Data["Data: Serious Patient Reactions, Hospitalizations, Class I/II Recalls"]
    end

    subgraph S5 ["5. UK MHRA"]
        S5_Name["Official: UK Medicines and Healthcare products Regulatory Agency"]
        S5_URL["URL: www.gov.uk/drug-safety-update & yellowcard.mhra.gov.uk"]
        S5_Code["Code: app/sources/uk_mhra/mhra_crawler.py<br/>adapter.py"]
        S5_Proto["Protocol: GOV.UK Open JSON API + ATOM Feed + Yellow Card Scheme"]
        S5_Key["Key Identifier: UK Product Licence (PL / PLGB)"]
        S5_Data["Data: Monthly Drug Safety Updates, CHM Advice, Yellow Card CTA"]
    end

    S1 --> IngestionHub["Canonical Data Normalization<br/>Standard dictionary with normalized metadata"]
    S2 --> IngestionHub
    S3 --> IngestionHub
    S4 --> IngestionHub
    S5 --> IngestionHub

    IngestionHub --> DBService["DatabaseService Engine<br/>(app/services/database_service.py)"]
    DBService --> Storage[("SQLite Relational Store<br/>Scoped by source and drug_name")]
    Storage --> Delivery["Unified Delivery: Web UI (app/ui.py) & REST API (app/api/drugs.py)"]
"""

# 04 - Crawler Architecture
DIAGRAMS["04-crawler-architecture"] = """flowchart TD
    ClientReq([Search Request / Scheduled Trigger]) --> Manager["FastAPI Controller<br/>(app/main.py / app/api/drugs.py)"]
    Manager --> WorkerPool{"asyncio.gather parallel tasks<br/>Timeout: 4.0s - 12.0s per engine"}

    subgraph IngestionAdapters ["Source Adapter Layer"]
        A_FDA["FDACrawler (app/crawler/fda_crawler.py)"]
        A_HC["HealthCanadaAdapter (app/sources/health_canada/)"]
        A_TGA["AustraliaTGAAdapter (app/sources/australia_tga/)"]
        A_MW["FDAMedWatchAdapter (app/sources/fda_medwatch/)"]
        A_MHRA["UKMHRAAdapter (app/sources/uk_mhra/)"]
    end

    WorkerPool --> A_FDA
    WorkerPool --> A_HC
    WorkerPool --> A_TGA
    WorkerPool --> A_MW
    WorkerPool --> A_MHRA

    subgraph DiscoveryMechanism ["URL and Endpoint Discovery"]
        D_FDA["POST searchResult.page (ViewState)"]
        D_HC["DPD API query + InfoWatch index"]
        D_TGA["GET search keywords endpoint"]
        D_MW["openFDA FAERS JSON + RSS feed"]
        D_MHRA["GOV.UK JSON API + ATOM feed"]
    end

    A_FDA --> D_FDA
    A_HC --> D_HC
    A_TGA --> D_TGA
    A_MW --> D_MW
    A_MHRA --> D_MHRA

    subgraph TransportLayer ["HTTP Fetcher and Resilience (httpx.AsyncClient)"]
        Fetcher["Async HTTP Fetcher<br/>Browser Headers, SSL Context, Backoff"]
        RateLimit{"Status Code Check"}
        RawContent["Raw HTML / JSON / XML / PDF"]
        FallbackRegistry["Curated Reference Registry<br/>Resilience against CDN blocks and rate limits"]
        Fetcher --> RateLimit
        RateLimit -->|200 OK| RawContent
        RateLimit -->|403 or 429 or Timeout| FallbackRegistry
    end

    D_FDA --> Fetcher
    D_HC --> Fetcher
    D_TGA --> Fetcher
    D_MW --> Fetcher
    D_MHRA --> Fetcher

    subgraph ParserLayer ["Document Parsers and Content Extractors"]
        P_FDA["FDASRLCScraper: Table parser"]
        P_HC["DPD Parser + InfoWatch Classifier"]
        P_TGA["TGA HTML Document Parser"]
        P_MW["openFDA JSON Parser + XML"]
        P_MHRA["GOV.UK JSON and ATOM Parser"]
    end

    RawContent --> P_FDA
    RawContent --> P_HC
    RawContent --> P_TGA
    RawContent --> P_MW
    RawContent --> P_MHRA

    Normalizer["NormalizationService<br/>(app/services/normalization.py)"]
    Validator["ValidationService<br/>(app/services/validation.py)"]
    Hasher["ChangeDetectionService<br/>SHA-256 Content Hash"]
    Storage[("DatabaseService to SQLite Storage<br/>(medicine_safety.db)")]

    P_FDA --> Normalizer
    P_HC --> Normalizer
    P_TGA --> Normalizer
    P_MW --> Normalizer
    P_MHRA --> Normalizer
    FallbackRegistry --> Normalizer

    Normalizer --> Validator
    Validator --> Hasher
    Hasher --> Storage
"""

# 05 - PDF Document Extraction
DIAGRAMS["05-pdf-document-extraction"] = """flowchart TD
    SourceTrigger([Regulatory Document Trigger or User Upload]) --> IngestionPath{Ingestion Source}

    IngestionPath -->|Health Canada InfoWatch| HC_Adapter["HealthCanadaAdapter route_pdf_to_extractor<br/>(app/sources/health_canada/infowatch/adapter.py)"]
    IngestionPath -->|User UI Upload| WebUpload["POST /api/upload<br/>(pdf_extractor/backend/api/upload.py)"]
    IngestionPath -->|API Request| APICall["POST /api/extract<br/>(pdf_extractor/backend/api/extraction.py)"]

    HC_Adapter -.->|HTTP POST JSON: url, source| APICall
    WebUpload --> SaveFile["Save PDF to uploads directory<br/>Generate UUID doc_id"]
    APICall --> SaveFile

    SaveFile --> Orchestrator["SectionExtractor.extract<br/>(pdf_extractor/backend/extraction/section_extractor.py)"]

    subgraph EnginePipeline ["Deterministic Extraction Pipeline (Deterministic, Zero LLM)"]
        direction TB
        
        Step1["1. PDFReader (pdf/reader.py)<br/>Open via PyMuPDF fitz<br/>Extract text blocks with coordinates and font stats"]
        
        Step2{"2. OCR Detector (pdf/ocr.py)<br/>Text density under 50 chars per page?"}
        
        Step2_Yes["Run Tesseract OCR on page pixmap<br/>pytesseract.image_to_string"]
        
        Step3["3. Margin and Noise Cleaner (pdf/cleaner.py)<br/>Identify recurring headers and footers<br/>Filter page margins by coordinate thresholds"]
        
        Step4["4. HeadingDetector (pdf/headings.py)<br/>Multi-signal classifier: numbering regex 16.1<br/>Relative font size clustering and bold flags"]
        
        Step5["5. TableExtractor (pdf/tables.py)<br/>pdfplumber graphical vector line detection<br/>Extract structured 2D table matrices"]
        
        Step6["6. SectionTreeBuilder (pdf/sections.py)<br/>Build prefix tree hierarchy (16 to 16.1 to 16.1.1)"]
        
        Step7["7. BoundaryDetector (extraction/boundary_detector.py)<br/>Strict coordinate boundary cutoff<br/>STOPS strictly before sibling section (16.2) on same page"]
        
        Step8["8. ExtractionValidator (extraction/validator.py)<br/>Verify section bounds, table completeness, reading order"]
    end

    Orchestrator --> Step1
    Step1 --> Step2
    Step2 -->|YES: Scanned Page| Step2_Yes
    Step2_Yes --> Step3
    Step2 -->|NO: Native Digital| Step3
    Step3 --> Step4
    Step4 --> Step5
    Step5 --> Step6
    Step6 --> Step7
    Step7 --> Step8

    Step8 --> ExportEngine["ExportService (pdf_extractor/backend/services/export_service.py)"]

    subgraph Exports ["Multi-Format Output Generation"]
        E_JSON[".json: Full AST with block bounding boxes"]
        E_CSV[".csv: Tabular section content"]
        E_XLSX[".xlsx: Excel workbook with formatted tables"]
        E_HTML[".html: Renderable report snippet"]
        E_TXT[".txt: Plaintext extraction"]
    end

    ExportEngine --> E_JSON
    ExportEngine --> E_CSV
    ExportEngine --> E_XLSX
    ExportEngine --> E_HTML
    ExportEngine --> E_TXT

    Step8 --> DBStore[("SQLite: extractor.db<br/>(DocumentRecord, ExtractionRecord, ContentBlockRecord)")]
    Step8 --> ReturnResult["ExtractionResult Payload<br/>Returns to caller or Health Canada adapter"]
    ReturnResult -.->|Appended to Advisory| SafetyRecord["Stored in medicine_safety.db<br/>as safety_labeling_changes.updated_text"]
"""

# 06 - Medicine Search Flow
DIAGRAMS["06-medicine-search-flow"] = """flowchart TD
    Start([User enters query: Ozempic & selects Source]) --> APIEntry["GET /search or GET /api/drugs/search<br/>Parameters: q='Ozempic', source='ALL'"]

    APIEntry --> Normalize["NormalizationService.normalize_drug_name('Ozempic')<br/>-> 'ozempic' (trimmed, lowercase)"]

    Normalize --> CheckDB["Query SQLite Database (medicine_safety.db)<br/>DatabaseService.search_drugs(db, 'ozempic', source)"]

    CheckDB --> DecisionCache{"Records exist in DB<br/>and force_refresh=False?"}

    DecisionCache -->|YES: Cache Hit| BuildCached["Build DrugSearchResultItem list<br/>Calculate safety_change_count<br/>Fetch latest last_verified_at"]
    BuildCached --> ReturnFast["Return Results Immediately<br/>Response Latency: under 15ms"]

    DecisionCache -->|NO: Cache Miss / Refresh| DispatchCrawl["Initialize Parallel Crawl Tasks (asyncio.gather)<br/>Targeting selected sources or ALL"]

    subgraph ParallelExecution ["Parallel Acquisition (4.0s Timeout Ceiling)"]
        direction TB
        C_HC["Health Canada Adapter<br/>Search DPD + InfoWatch"]
        C_FDA["FDA Crawler & Scraper<br/>Search SrLC ASPX"]
        C_TGA["Australia TGA Adapter<br/>Search tga.gov.au"]
        C_MW["FDA MedWatch Adapter<br/>Search FAERS + Recalls"]
        C_MHRA["UK MHRA Adapter<br/>Search gov.uk/drug-safety-update"]
    end

    DispatchCrawl --> C_HC
    DispatchCrawl --> C_FDA
    DispatchCrawl --> C_TGA
    DispatchCrawl --> C_MW
    DispatchCrawl --> C_MHRA

    C_HC --> UpsertDB["DatabaseService.insert_or_update_drug()<br/>Unique Key: (source, normalized_name)<br/>Insert safety changes & version history"]
    C_FDA --> UpsertDB
    C_TGA --> UpsertDB
    C_MW --> UpsertDB
    C_MHRA --> UpsertDB

    UpsertDB --> CommitDB["session.commit()"]
    CommitDB --> FinalQuery["Re-query DatabaseService.search_drugs(db, 'ozempic')"]
    FinalQuery --> BuildResponse["Construct SearchResultResponse<br/>Or render_homepage_html with badges"]
    ReturnFast --> BuildResponse
    BuildResponse --> Deliver([Deliver HTTP 200 Response to Client])
"""

# 07 - Database Architecture
DIAGRAMS["07-database-architecture"] = """erDiagram
    DRUGS ||--o{ SAFETY_LABELING_CHANGES : "has many (1:N)"
    SAFETY_LABELING_CHANGES ||--o{ SAFETY_CHANGE_VERSIONS : "has audit history (1:N)"
    CRAWL_RUNS ||--o{ DRUGS : "monitors discovery"

    DOCUMENTS ||--o{ EXTRACTIONS : "has many (1:N)"
    EXTRACTIONS ||--o{ CONTENT_BLOCKS : "contains (1:N)"

    DRUGS {
        int id PK "Primary Key (Integer Auto-Inc)"
        string display_name "Original Display Name (e.g. OZEMPIC)"
        string normalized_name "Indexed Search Key (e.g. ozempic)"
        string active_ingredient "Normalized Active Substance"
        string application_number "Authority ID (NDA-XXXXXX, DIN, AUST R, PLGB)"
        string source "Regulatory Authority Identifier"
        datetime created_at "First ingestion timestamp"
        datetime updated_at "Last modification timestamp"
    }

    SAFETY_LABELING_CHANGES {
        int id PK "Primary Key (Integer Auto-Inc)"
        int drug_id FK "Foreign Key -> drugs.id (Cascade Delete)"
        string source "Authority Source Identifier"
        string source_record_id "Upstream Unique Reference ID"
        string section "Labeling / Clinical Section"
        string change_type "Type: Boxed Warning, Advisory, Recall"
        datetime source_date "Upstream published date"
        datetime approval_date "Regulatory approval date"
        datetime effective_date "Legal effective date"
        text original_text "Historical or pre-revision text"
        text updated_text "New or revised safety advisory text"
        text fda_comment "Regulatory review or CHM comment"
        string source_url "Deep link to source advisory"
        string content_hash "SHA-256 hash of content fields"
        datetime first_seen_at "Initial detection timestamp"
        datetime last_verified_at "Last verification timestamp"
        datetime created_at "Creation timestamp"
        datetime updated_at "Modification timestamp"
    }

    SAFETY_CHANGE_VERSIONS {
        int id PK "Primary Key (Integer Auto-Inc)"
        int safety_change_id FK "Foreign Key -> safety_labeling_changes.id"
        int version_number "Sequential Version (1, 2, 3...)"
        string content_hash "SHA-256 hash at time of revision"
        text original_text "Historical text version"
        text updated_text "Updated text version"
        text normalized_content "Normalized comparison payload"
        datetime retrieved_at "Timestamp of capture"
        datetime created_at "Row creation timestamp"
    }

    CRAWL_RUNS {
        int id PK "Primary Key (Integer Auto-Inc)"
        string source "Regulatory Source Identifier"
        datetime started_at "Run start timestamp"
        datetime completed_at "Run completion timestamp"
        string status "pending, running, success, failed"
        int pages_requested "Pages requested"
        int pages_crawled "Pages successfully crawled"
        int records_found "Total records found"
        int records_added "New records inserted"
        int records_changed "Existing records updated"
        int records_unchanged "Unchanged records"
        text errors "JSON serialized array of error logs"
        datetime created_at "Creation timestamp"
    }

    DOCUMENTS {
        string id PK "UUID Primary Key (char 36)"
        string filename "Original PDF Filename"
        string file_path "Absolute Filesystem Path"
        int total_pages "Total page count"
        datetime created_at "Upload timestamp"
    }

    EXTRACTIONS {
        string id PK "UUID Primary Key (char 36)"
        string document_id FK "Foreign Key -> documents.id"
        string main_section "Parent Heading (e.g. 16)"
        string target_subsection "Target Subheading (e.g. 16.1)"
        int start_page "Extraction start page"
        int end_page "Extraction boundary page"
        string status "success, partial, failed"
        float confidence_score "Extraction confidence (0.0 - 1.0)"
        text included_sections "JSON array of included subsections"
        text excluded_sections "JSON array of excluded sibling sections"
        datetime created_at "Extraction timestamp"
    }

    CONTENT_BLOCKS {
        string id PK "Content Hash UUID (char 64)"
        string extraction_id FK "Foreign Key -> extractions.id"
        string block_type "paragraph, heading, table, list_item"
        int page_num "Page number (1-based)"
        string section_number "Section prefix (e.g. 16.1.2)"
        int reading_order "Topological reading order index"
        text text "Extracted text content"
        string bbox_json "Bounding box coordinates"
        text content_json "Structured table matrix JSON"
    }
"""

# 08 - Backend Architecture
DIAGRAMS["08-backend-architecture"] = """flowchart TD
    ClientReq([Client HTTP Request]) --> AppEntry["app.main:app (FastAPI)"]

    AppEntry --> Middleware["Middleware Stack<br/>- CORSMiddleware (allow_origins)<br/>- Exception Handlers<br/>- Request Logging"]

    Middleware --> RouterHub{"API / Web Router Hub"}

    subgraph Routers ["API Routers (backend/app/api/)"]
        RouterHub --> R_Drugs["drugs.py: /api/drugs<br/>- /search, /sync<br/>- /{id}, /{id}/safety-changes<br/>- /search/{source}"]
        RouterHub --> R_Safety["safety_changes.py: /api/safety-changes<br/>- /changes, /{id}/versions<br/>- /verify, /diff"]
        RouterHub --> R_Admin["admin.py: /api/admin<br/>- /crawl, /crawl-status<br/>- /stats, /health"]
        RouterHub --> R_Web["main.py Web Routes<br/>- GET / (homepage search)<br/>- GET /drugs/{id} (detail view)<br/>- GET /drugs/{id}/export (CSV/JSON)<br/>- GET /architecture (diagram view)"]
    end

    subgraph ServiceLayer ["Service Layer (backend/app/services/)"]
        R_Drugs --> DBService["DatabaseService<br/>- insert_or_update_drug()<br/>- save_safety_change()<br/>- search_drugs()<br/>- get_safety_changes_by_drug_id()"]
        R_Safety --> DBService
        R_Admin --> DBService
        R_Web --> DBService
        R_Drugs --> NormService["NormalizationService<br/>- normalize_drug_name()<br/>- normalize_text()<br/>- clean_html()"]
        R_Safety --> NormService
        R_Drugs --> ValidService["ValidationService<br/>- validate_record()<br/>- validate_dates()"]
        R_Safety --> ValidService
        DBService --> ChangeService["ChangeDetectionService<br/>- generate_content_hash()<br/>- detect_changes() (SHA-256)"]
        R_Drugs --> CacheServ["CacheService<br/>- Redis / Memory Cache"]
        R_Admin --> CacheServ
    end

    subgraph AdaptersLayer ["Regulatory Ingestion Adapters (backend/app/sources/)"]
        AdapterHub{"Source Orchestrator<br/>asyncio.gather"}
        R_Drugs --> AdapterHub
        R_Web --> AdapterHub
        AdapterHub --> A_FDA["FDACrawler (app/crawler/fda_crawler.py)<br/>scraper (app/scrapers/fda_srlc_scraper.py)"]
        AdapterHub --> A_HC["hc_adapter (app/sources/health_canada/infowatch/adapter.py)<br/>dpd_crawler (dpd_crawler.py)"]
        AdapterHub --> A_TGA["tga_adapter (app/sources/australia_tga/adapter.py)<br/>tga_crawler (tga_crawler.py)"]
        AdapterHub --> A_MW["medwatch_adapter (app/sources/fda_medwatch/adapter.py)<br/>medwatch_crawler (medwatch_crawler.py)"]
        AdapterHub --> A_MHRA["mhra_adapter (app/sources/uk_mhra/adapter.py)<br/>mhra_crawler (mhra_crawler.py)"]
    end

    subgraph BackgroundLayer ["Background Workers & Schedulers"]
        Worker["Celery Worker (app/workers/fda_worker.py)<br/>- crawl_fda_task<br/>- scheduled_crawl_task"]
        Scheduler["Celery Beat / Systemd Scheduler<br/>(systemd/medicine-scheduler.service)"]
        Scheduler -.-> Worker
    end

    subgraph ExternalServices ["External Subsystem Integration"]
        A_HC -->|HTTP POST /api/extract| ExtPDF["PDF Extractor Microservice<br/>(pdf_extractor/backend/main.py: Port 8001)"]
    end

    DBService --> SessionFactory["SQLAlchemy SessionLocal (app/database.py)"]
    SessionFactory --> SQLiteDB[("SQLite Database<br/>backend/medicine_safety.db")]
"""

# 09 - Frontend Architecture
DIAGRAMS["09-frontend-architecture"] = """flowchart TD
    User([User in Web Browser]) --> WebRoute{"URL Navigation"}

    subgraph MainAppUI ["Medicine Safety Frontend (app/ui.py - Server-Side Rendered)"]
        WebRoute -->|GET / or /search| HomeView["render_homepage_html()"]
        WebRoute -->|GET /drugs/id| DetailView["render_drug_detail_html()"]
        WebRoute -->|GET /drugs/id/export| ExportEndpoint["web_drug_export()"]
        WebRoute -->|GET /architecture| ArchView["architecture_diagram_view()"]

        subgraph HomeComponents ["Homepage View Components"]
            Header["Global Header: Platform Title and Source Badges<br/>US FDA • Canada DPD • Australia TGA • FDA MedWatch • UK MHRA"]
            SearchForm["Search Form: Input Field and Source Dropdown Filter<br/>ALL, UK_MHRA, FDA_MEDWATCH, AUSTRALIA_TGA, HEALTH_CANADA, FDA_SRLC"]
            ResultList["Search Results Grid: Drug Cards with Status Badges<br/>• Drug Brand and Normalized Name<br/>• Active Ingredient and Formulation<br/>• Authority Application and Licence Number<br/>• Safety Changes Count and Last Verified Date<br/>• View Complete History Action Button"]
        end

        HomeView --> Header
        Header --> SearchForm
        SearchForm --> ResultList

        subgraph DetailComponents ["Specialized Detail Page Renderers"]
            DetailRouter{"Drug Source Dispatcher"}
            RenderMHRA["render_uk_mhra_drug_detail<br/>• PL/PLGB Licence Tag<br/>• Yellow Card ADR Reporting Scheme Button<br/>• Clinical Advice and Drug Safety Update Bulletins"]
            RenderMW["render_fda_medwatch_drug_detail<br/>• MedWatch Event and Recall ID Tag<br/>• Post-Marketing Reaction Signals<br/>• Form FDA 3500 Voluntary Reporting Guidelines"]
            RenderTGA["render_australia_tga_drug_detail<br/>• ARTG AUST R and AUST L Badge<br/>• Sponsor Information and PI/CMI Leaflet Links<br/>• Product Defect and Safety Alerts"]
            RenderHC["render_health_canada_drug_detail<br/>• DIN Tag and Marketed Status<br/>• Product Monograph PDF Link<br/>• Health Product InfoWatch Advisories"]
            RenderFDA["render_fda_srlc_drug_detail<br/>• NDA/BLA Application Number<br/>• Boxed Warnings and Labeling Revisions<br/>• Chronological Change Version History"]

            DetailRouter -->|source is UK_MHRA| RenderMHRA
            DetailRouter -->|source is FDA_MEDWATCH| RenderMW
            DetailRouter -->|source is AUSTRALIA_TGA| RenderTGA
            DetailRouter -->|source is HEALTH_CANADA| RenderHC
            DetailRouter -->|source is FDA_SRLC| RenderFDA
        end

        DetailView --> DetailRouter

        subgraph ExportActions ["Data Export Functions"]
            CSVAction["export_drug_csv: RFC 4180 CSV attachment"]
            JSONAction["export_drug_json: Canonical formatted JSON"]
        end

        ExportEndpoint --> CSVAction
        ExportEndpoint --> JSONAction
    end

    subgraph PDFExtractorUI ["PDF Extractor Subsystem Frontend (pdf_extractor/frontend/)"]
        WebRoute -->|GET http://localhost:8001/| PDFIndex["index.html Dashboard"]
        PDFIndex --> Dropzone["Drag-and-Drop PDF Upload Zone"]
        PDFIndex --> SectionInputs["Main Section and Subsection Selectors (e.g. 16 to 16.1)"]
        PDFIndex --> TableToggle["Include or Strip Tables Mode Selector"]
        PDFIndex --> AppJS["app.js Client Orchestration (Fetch API)"]
        AppJS --> ExtractionAST["Interactive Tree View and Structured Viewer"]
        AppJS --> Downloads["Direct Download Buttons: XLSX, CSV, JSON, HTML, TXT"]
    end
"""

# 10 - Error Handling Flow
DIAGRAMS["10-error-handling-flow"] = """flowchart TD
    Operation([Crawling, Extraction, or Search Operation]) --> FailurePoint{"Failure Condition"}

    FailurePoint -->|Network Timeout >4.0s / >30s| E_Timeout["httpx.TimeoutException<br/>(Slow upstream government portal)"]
    E_Timeout --> H_Timeout["Timeout Handling<br/>1. Log timeout with logger.error<br/>2. Discard URL from visited set<br/>3. Activate pre-indexed Curated Reference Registry<br/>4. Ensure sibling crawlers complete uninterrupted"]

    FailurePoint -->|HTTP 403 / 429 / WAF Block| E_Block["HTTPStatusError (403 Forbidden / 429 Too Many Requests)<br/>(Akamai / Cloudflare Edge Protection)"]
    E_Block --> H_Block["Anti-Bot Resilience<br/>1. Rotate browser headers (User-Agent, Accept-Language)<br/>2. Apply exponential backoff (0.3s * 2^retry)<br/>3. If persistent, return curated benchmark dataset<br/>4. Mark CrawlRun status as partial"]

    FailurePoint -->|DOM Structure Altered / Malformed HTML| E_Parse["BeautifulSoup Parse Error / Missing Tags"]
    E_Parse --> H_Parse["Fail-Safe Scraping<br/>1. Log warning: 'Failed to extract section'<br/>2. Return None for missing fields without crash<br/>3. Fall back to textual date/section regex<br/>4. Store partial record with fda_comment flag"]

    FailurePoint -->|SQLAlchemy DB Error / IntegrityError| E_DB["SQLAlchemyError / Constraint Violation"]
    E_DB --> H_DB["Transaction Isolation<br/>1. db.rollback() to clear poisoned session<br/>2. Log full traceback with exc_info=True<br/>3. Prevent cascading failure to other sources<br/>4. Return existing cached records if present"]

    FailurePoint -->|PDF Extractor Port 8001 Unreachable| E_PDF["httpx.ConnectError / ConnectTimeout (Port 8001)"]
    E_PDF --> H_PDF["Graceful Degradation<br/>1. Catch ConnectError in _route_pdf_to_extractor()<br/>2. Log: 'PDF extractor not reachable — skipping PDF'<br/>3. Proceed with HTML advisory text only<br/>4. Zero impact on user response latency"]

    FailurePoint -->|Unreadable Scanned PDF| E_OCR["Tesseract OCR Failure / Low Confidence"]
    E_OCR --> H_OCR["OCR Fallback Pipeline<br/>1. PyMuPDF extracts embedded vector text if any<br/>2. Flag extraction confidence_score < 0.5<br/>3. Record status='partial' in ExtractionRecord<br/>4. Include raw text stream in download files"]

    H_Timeout --> RecoveryLog["Structured Audit Logging<br/>(structlog / standard logging -> CrawlRun.errors)"]
    H_Block --> RecoveryLog
    H_Parse --> RecoveryLog
    H_DB --> RecoveryLog
    H_PDF --> RecoveryLog
    H_OCR --> RecoveryLog

    RecoveryLog --> SafeResponse["Return Graceful Partial Response to User<br/>HTTP 200 with available authority records"]
"""

# 11 - Security / Access Flow
DIAGRAMS["11-security-access-flow"] = """flowchart TD
    ClientReq([Inbound Client Request or Outbound Crawler Request]) --> SecurityCheck{"Traffic Classification"}

    SecurityCheck -->|Inbound Web or API Request| CORSCheck{"CORS Validation (CORSMiddleware)"}
    CORSCheck -->|Origin in CORS_ORIGINS| AllowCORS["Allow Request Headers"]
    CORSCheck -->|Wildcard or Web Portal| AllowPublic["Allow Public Search Navigation"]

    InputValidation{\"Parameter Validation (Pydantic and FastAPI Query)\"}
    SanitizeQuery[\"Sanitize Search Query<br/>Prevent SQL Injection via SQLAlchemy ORM Param Binding\"]
    FormatCheck[\"Validate Export Format String (CSV or JSON)\"]
    Reject422[\"HTTP 422 Unprocessable Entity\"]

    AllowCORS --> InputValidation
    AllowPublic --> InputValidation
    InputValidation -->|Valid query string| SanitizeQuery
    InputValidation -->|Valid format flag| FormatCheck
    InputValidation -->|Invalid Input| Reject422

    APIKeyCheck{\"Endpoint Protected? (e.g. PDF Extractor B2B)\"}
    ValidateKey[\"Validate Token against Config\"]
    AllowExecution[\"Proceed to Controller Execution\"]
    Reject401[\"HTTP 401 Unauthorized\"]

    SanitizeQuery --> APIKeyCheck
    FormatCheck --> APIKeyCheck
    APIKeyCheck -->|X-API-Key Header Present| ValidateKey
    APIKeyCheck -->|Public Medicine Search| AllowExecution
    ValidateKey -->|Valid| AllowExecution
    ValidateKey -->|Invalid| Reject401

    SecurityCheck -->|Outbound Regulatory Crawl| InspectPortal{\"Target Authority Site\"}
    ApplyHeaders[\"Apply Compliant Browser Headers<br/>• Realistic User-Agent<br/>• Accept and Language Headers<br/>• Strict Read-Only GET and POST\"]
    InspectPortal -->|US FDA, TGA, MHRA, Health Canada| ApplyHeaders

    DispatchHTTP[\"httpx.AsyncClient Execution\"]
    ApplyHeaders --> DispatchHTTP

    DetectChallenge{\"WAF or Bot Challenge Detected?<br/>(Akamai / Cloudflare / CAPTCHA)\"}
    DispatchHTTP --> DetectChallenge

    ProcessData[\"Process Regulatory Data\"]
    DetectChallenge -->|NO: Standard HTML or JSON| ProcessData

    DetectChallenge -->|YES: Human Verification or CAPTCHA Detected| Step1[\"1. DO NOT attempt automated CAPTCHA bypass<br/>(Strict Regulatory Compliance)\"]
    Step1 --> Step2[\"2. Log security challenge event with timestamp and URL\"]
    Step2 --> Step3[\"3. Mark source temporarily restricted in CrawlRun\"]
    Step3 --> Step4[\"4. Fallback to Verified Curated Reference Registry<br/>(Pre-indexed authoritative government data)\"]
    Step4 --> Step5[\"5. Serve verified regulatory dataset to user without outage\"]
"""

# 12 - Current Implemented Architecture
DIAGRAMS["12-current-architecture"] = """flowchart TD
    subgraph ClientTier ["CLIENT TIER"]
        UserBrowser["Web Browser (End User)"]
        RESTClient["REST API Client (Third-Party)"]
    end

    subgraph Service1 ["SUBSYSTEM 1: MEDICINE SAFETY PLATFORM (FastAPI: Port 8000)"]
        MainApp["app.main:app"]
        UIModule["app/ui.py (Server-Side Rendered HTML strings)"]
        DrugsAPI["app/api/drugs.py"]
        SafetyAPI["app/api/safety_changes.py"]
        AdminAPI["app/api/admin.py"]
        
        DBService["DatabaseService (app/services/database_service.py)"]
        NormService["NormalizationService (app/services/normalization.py)"]
        ChangeService["ChangeDetectionService (SHA-256)"]
        SQLite_Main[("SQLite Database: backend/medicine_safety.db")]
    end

    subgraph InProcessCrawlers ["IN-PROCESS REGULATORY CRAWLERS"]
        FDACrawl["FDACrawler and Scraper (ASPX POST)"]
        HCCrawl["HealthCanadaAdapter (DPD API + InfoWatch)"]
        TGACrawl["AustraliaTGAAdapter (HTML Scraper)"]
        MWCrawl["FDAMedWatchAdapter (openFDA REST + RSS)"]
        MHRACrawl["UKMHRAAdapter (GOV.UK JSON + ATOM)"]
    end

    subgraph FallbackRegistries ["IN-MEMORY CURATED FALLBACK REGISTRIES"]
        TGA_Reg["TGA_CURATED_REGISTRY (Ozempic, Warfarin, etc.)"]
        MW_Reg["MEDWATCH_CURATED_REGISTRY"]
        MHRA_Reg["MHRA_CURATED_REGISTRY"]
    end

    subgraph Service2 ["SUBSYSTEM 2: INTELLIGENT PDF SECTION EXTRACTOR (FastAPI: Port 8001)"]
        PDFApp["backend.main:app"]
        PDFExtractAPI["backend/api/extraction.py"]
        PDFUploadAPI["backend/api/upload.py"]
        PDFStatic["frontend/ (Static HTML/CSS/JS)"]

        SecExtractor["SectionExtractor Engine"]
        PyMuPDF["PyMuPDF fitz (Text and Bounding Boxes)"]
        Tesseract["pytesseract (Local OCR Fallback)"]
        Plumber["pdfplumber (Vector Table Extraction)"]

        SQLite_PDF[("SQLite Database: pdf_extractor/extractor.db")]
    end

    subgraph ExternalWebsites ["EXTERNAL REGULATORY WEBSITES"]
        W_FDA["accessdata.fda.gov"]
        W_HC["health-products.canada.ca"]
        W_TGA["www.tga.gov.au/search"]
        W_MW["fda.gov/safety/medwatch"]
        W_MHRA["www.gov.uk/drug-safety-update"]
    end

    UserBrowser --> MainApp
    UserBrowser --> PDFStatic
    RESTClient --> DrugsAPI

    MainApp --> UIModule
    MainApp --> DrugsAPI
    MainApp --> SafetyAPI
    MainApp --> AdminAPI

    DrugsAPI --> DBService
    DrugsAPI --> NormService
    DrugsAPI --> ChangeService

    DrugsAPI --> FDACrawl
    DrugsAPI --> HCCrawl
    DrugsAPI --> TGACrawl
    DrugsAPI --> MWCrawl
    DrugsAPI --> MHRACrawl

    FDACrawl -.-> W_FDA
    HCCrawl -.-> W_HC
    TGACrawl -.-> W_TGA
    MWCrawl -.-> W_MW
    MHRACrawl -.-> W_MHRA

    TGACrawl -.-> TGA_Reg
    MWCrawl -.-> MW_Reg
    MHRACrawl -.-> MHRA_Reg

    HCCrawl --> PDFExtractAPI
    
    DBService --> SQLite_Main
    PDFExtractAPI --> SecExtractor
    SecExtractor --> PyMuPDF
    SecExtractor --> Tesseract
    SecExtractor --> Plumber
    SecExtractor --> SQLite_PDF
"""

# 13 - Recommended Architecture
DIAGRAMS["13-recommended-architecture"] = """flowchart TD
    subgraph ClientLayer ["CLIENT & INTEGRATION TIER"]
        WebUsers["Web & Mobile Users"]
        PharmaReviewers["Pharma Compliance Reviewers"]
        B2BClients["Enterprise B2B API Integrators"]
    end

    subgraph GatewayLayer ["API GATEWAY & REVERSE PROXY (Nginx / Traefik)"]
        Gateway["API Gateway / Ingress Controller<br/>• Rate Limiting (Token Bucket)<br/>• Centralized SSL / TLS Termination<br/>• JWT & API Key Authentication<br/>• Request Routing & CORS Enforcement"]
    end

    ClientLayer --> Gateway

    subgraph CoreServices ["MICROSERVICES TIER"]
        SearchService["Medicine Search Microservice<br/>(FastAPI - Read-Optimized API)"]
        CrawlerManager["Regulatory Crawler Coordinator<br/>(Scheduled & Event-Driven Triggers)"]
        ExtractionService["Clinical Document Extraction Service<br/>(Dedicated PDF / OCR Worker Pool)"]
        ChangeDetectionService["Audit & Change Tracking Service<br/>(Cryptographic Hashing & Versioning)"]
        ExportService["Reporting & Export Service<br/>(Async PDF / Excel / CSV Generator)"]
    end

    Gateway --> SearchService
    Gateway --> ExtractionService
    Gateway --> ExportService

    subgraph MessageBrokerTier ["ASYNCHRONOUS EVENT BUS & TASK QUEUES"]
        Broker["Message Broker & Event Bus<br/>(RabbitMQ / Apache Kafka)"]
        Q_FDA["Queue: fda.crawl.jobs"]
        Q_HC["Queue: hc.crawl.jobs"]
        Q_TGA["Queue: tga.crawl.jobs"]
        Q_MW["Queue: medwatch.crawl.jobs"]
        Q_MHRA["Queue: mhra.crawl.jobs"]
        Q_PDF["Queue: pdf.extraction.jobs"]

        Broker --> Q_FDA
        Broker --> Q_HC
        Broker --> Q_TGA
        Broker --> Q_MW
        Broker --> Q_MHRA
        Broker --> Q_PDF
    end

    CrawlerManager --> Broker
    SearchService -.->|Cache Miss Trigger| Broker

    subgraph WorkerPoolTier ["DISTRIBUTED WORKER CLUSTERS (Celery / Ray)"]
        W_FDA_Cluster["FDA Scraper Workers (Headless Browser / Scraping Pool)"]
        W_HC_Cluster["Health Canada Workers (DPD & InfoWatch)"]
        W_TGA_Cluster["Australia TGA Workers (Akamai Evasion & Proxy Mesh)"]
        W_MW_Cluster["MedWatch Workers (openFDA Bulk Streamer)"]
        W_MHRA_Cluster["UK MHRA Workers (JSON Feed Consumers)"]
        W_PDF_Cluster["GPU/CPU Scaled PDF OCR Workers (PyMuPDF + Tesseract)"]
    end

    Q_FDA --> W_FDA_Cluster
    Q_HC --> W_HC_Cluster
    Q_TGA --> W_TGA_Cluster
    Q_MW --> W_MW_Cluster
    Q_MHRA --> W_MHRA_Cluster
    Q_PDF --> W_PDF_Cluster

    subgraph DataTier ["ENTERPRISE PERSISTENCE & CACHE TIER"]
        RedisCluster[("Redis Cluster (Tiered Caching & Rate Limits)<br/>• Hot Drug Record Cache (TTL: 24h)<br/>• Crawl Lock Mutexes (Redlock)")]
        PgBouncer["PgBouncer Connection Pooler"]
        PostgresDB[("PostgreSQL 16 High-Availability Cluster<br/>• drugs, safety_changes, audit_versions<br/>• pgvector for Semantic Medicine Matching<br/>• Read Replicas for High-Throughput Search")]
        ObjectStorage[("S3 / MinIO Object Storage<br/>• Regulatory PDF Archive<br/>• Product Monographs<br/>• Generated Export Bundles")]
    end

    SearchService <--> RedisCluster
    SearchService --> PgBouncer
    PgBouncer --> PostgresDB
    WorkerPoolTier --> PgBouncer
    W_PDF_Cluster <--> ObjectStorage
    ExportService <--> ObjectStorage

    subgraph ObservabilityTier ["MONITORING & OBSERVABILITY"]
        Prometheus["Prometheus Metrics Collection"]
        Grafana["Grafana Real-time Architecture Dashboards"]
        OpenTelemetry["OpenTelemetry Distributed Tracing"]
        Sentry["Sentry Automated Error & Crash Tracking"]
    end

    CoreServices -.-> Prometheus
    CoreServices -.-> OpenTelemetry
    CoreServices -.-> Sentry
    WorkerPoolTier -.-> Prometheus
    WorkerPoolTier -.-> OpenTelemetry
    WorkerPoolTier -.-> Sentry
    Prometheus --> Grafana
"""

print(f"Total architecture diagrams defined: {len(DIAGRAMS)}")

def fetch_with_retry(url, dest_path, retries=3, delay=1.0):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
                if len(data) > 0:
                    with open(dest_path, "wb") as f:
                        f.write(data)
                    return len(data)
        except urllib.error.HTTPError as e:
            if e.code == 503 and attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            raise
    return 0

success_svg = 0
success_png = 0
failures = []

for name, content in DIAGRAMS.items():
    mmd_path = DIAGRAMS_DIR / f"{name}.mmd"
    svg_path = IMAGES_DIR / f"{name}.svg"
    png_path = IMAGES_DIR / f"{name}.png"

    # Save MMD
    with open(mmd_path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")
    print(f"[{name}] Written MMD -> {mmd_path.name}")

    encoded = base64.b64encode(content.strip().encode("utf-8")).decode("ascii")

    # SVG
    try:
        svg_url = f"https://mermaid.ink/svg/{encoded}"
        svg_size = fetch_with_retry(svg_url, svg_path)
        print(f"  └─ SVG Generated ({svg_size:,} bytes) -> {svg_path.name}")
        success_svg += 1
    except Exception as e:
        print(f"  └─ SVG ERROR: {e}")
        failures.append((name, "SVG", str(e)))

    # PNG
    try:
        png_url = f"https://mermaid.ink/img/{encoded}"
        png_size = fetch_with_retry(png_url, png_path)
        print(f"  └─ PNG Generated ({png_size:,} bytes) -> {png_path.name}")
        success_png += 1
    except Exception as e:
        print(f"  └─ PNG ERROR: {e}")
        failures.append((name, "PNG", str(e)))

    time.sleep(0.4)

print("\n" + "=" * 60)
print(f"RESULTS: {success_svg}/13 SVGs generated, {success_png}/13 PNGs generated.")
if failures:
    print(f"FAILURES ({len(failures)}):")
    for f in failures:
        print(f"  - {f[0]} ({f[1]}): {f[2]}")
print("=" * 60)
