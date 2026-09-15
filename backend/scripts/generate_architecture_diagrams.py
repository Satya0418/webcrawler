#!/usr/bin/env python3
"""
Architecture Diagram Generator for Medicine Safety & Section Extraction Platform.
Generates 13 professional Mermaid source files (.mmd) and renders both SVG and PNG
diagram assets into docs/architecture/diagrams/ and docs/architecture/images/.
"""
import os
import sys
import base64
import time
import urllib.request
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DIAGRAMS_DIR = WORKSPACE_ROOT / "docs" / "architecture" / "diagrams"
IMAGES_DIR = WORKSPACE_ROOT / "docs" / "architecture" / "images"

DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

DIAGRAMS = {}

# ==============================================================================
# DIAGRAM 01: SYSTEM ARCHITECTURE
# ==============================================================================
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
        
        MainApp --> DrugsRouter & SafetyRouter & AdminRouter
        PDFApp --> ExtractionRouter & UploadRouter
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
        AsyncGather{"asyncio.gather(*tasks)<br/>4.0s Timeout Ceiling & Error Isolation"}
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
        ExtFDA["🇺🇸 US FDA SrLC Portal<br/>(accessdata.fda.gov)"]
        ExtHC["🍁 Health Canada DPD & InfoWatch<br/>(health-products.canada.ca)"]
        ExtTGA["🇦🇺 Australia TGA Portal<br/>(www.tga.gov.au/search)"]
        ExtMW["🚨 FDA MedWatch & openFDA<br/>(fda.gov/safety/medwatch & api.fda.gov)"]
        ExtMHRA["🇬🇧 UK MHRA Drug Safety Update<br/>(www.gov.uk/drug-safety-update)"]
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

        SecExtractor --> PDFReader --> HeadingDet --> TableExt --> BoundaryDet
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

# ==============================================================================
# DIAGRAM 02: END-TO-END DATA FLOW
# ==============================================================================
DIAGRAMS["02-end-to-end-data-flow"] = """flowchart TD
    Start([User submits Search Query: 'Ozempic']) --> Step1[1. Clean & Normalize Query<br/>NormalizationService.normalize_drug_name]
    Step1 --> Step2[2. Check Local Database Cache<br/>DatabaseService.search_drugs]
    Step2 --> Decision1{Cached records exist<br/>and fresh <24h?}

    Decision1 -->|YES| ReturnCache[Return Cached Records<br/>Response latency <15ms]
    Decision1 -->|NO or Force Refresh| Step3[3. Evaluate Source Parameter<br/>source=ALL or specific authority]

    Step3 --> Step4[4. Launch Concurrent Crawling Tasks<br/>asyncio.gather with return_exceptions=True]

    subgraph ParallelCrawl ["5. Parallel Ingestion Streams"]
        direction TB
        Stream1["FDA Crawler: ASPX POST searchResult.page<br/>Extract candidate detail URLs"]
        Stream2["Health Canada: DPD API query + InfoWatch discovery<br/>Fetch monographs & advisories"]
        Stream3["Australia TGA: Search keywords endpoint<br/>Extract AUST R/L & PI/CMI links"]
        Stream4["FDA MedWatch: openFDA FAERS REST query<br/>Ingest adverse events & Class I/II recalls"]
        Stream5["UK MHRA: Query GOV.UK JSON search endpoint<br/>Extract PL/PLGB licences & CHM advice"]
    end

    Step4 --> Stream1 & Stream2 & Stream3 & Stream4 & Stream5

    Stream2 -.->|Discovers Monograph PDF Link| PDFRouting{PDF link present?}
    PDFRouting -.->|YES| PDFCall[POST /api/extract to PDF Extractor<br/>Timeout: 120s]
    PDFCall -.-> PDFExtract[Extract structured sections & tables<br/>Append [PDF content] to advisory]
    PDFCall -.->|Connection Error / Timeout| PDFFallback[Fallback gracefully to HTML content]

    Stream1 & Stream2 & Stream3 & Stream4 & Stream5 --> Step6[6. Ingestion into Canonical Dictionary<br/>dict: name, ingredient, app_num, source, changes]
    PDFExtract --> Step6
    PDFFallback --> Step6

    Step6 --> Step7[7. Validate Record Structure<br/>ValidationService.validate_record]
    Step7 --> Step8[8. Resolve & Upsert Drug Entity<br/>DatabaseService.insert_or_update_drug<br/>Unique Scope: source + drug_name]

    Step8 --> Step9[9. Change Detection & Audit Log<br/>Compute SHA-256 Hash of content fields]
    Step9 --> Decision2{Content Hash<br/>differs from latest?}

    Decision2 -->|YES| Step10[Create SafetyChangeVersion row<br/>Increment version_number by 1]
    Decision2 -->|NO| Step11[Update last_verified_at timestamp]

    Step10 & Step11 --> Step12[10. Commit Database Transaction<br/>session.commit]
    Step12 --> Step13[11. Format Output Payload<br/>SearchResultResponse / Glassmorphic UI HTML]
    ReturnCache --> Step13
    Step13 --> End([Render Response to User / Client])
"""

# ==============================================================================
# DIAGRAM 03: FIVE REGULATORY SOURCES
# ==============================================================================
DIAGRAMS["03-five-regulatory-sources"] = """flowchart TD
    Hub(["MEDICINE SAFETY MULTI-AUTHORITY PLATFORM<br/>(5 Global Regulatory Sources)"])

    Hub --> S1
    Hub --> S2
    Hub --> S3
    Hub --> S4
    Hub --> S5

    subgraph S1 ["🇺🇸 1. US FDA SrLC"]
        S1_Name["Official: FDA Safety-related Labeling Changes (SrLC)"]
        S1_URL["URL: accessdata.fda.gov/scripts/cder/safetylabelingchanges"]
        S1_Code["Code: app/crawler/fda_crawler.py<br/>app/scrapers/fda_srlc_scraper.py"]
        S1_Proto["Protocol: HTTPS POST (ViewState session) + BeautifulSoup"]
        S1_Key["Key Identifier: NDA / BLA Application Number"]
        S1_Data["Data: Boxed Warnings, Warnings & Precautions, Adverse Reactions"]
    end

    subgraph S2 ["🍁 2. Health Canada"]
        S2_Name["Official: Drug Product Database (DPD) & Health Product InfoWatch"]
        S2_URL["URL: health-products.canada.ca/dpd-bdpp & recalls-rappels.canada.ca"]
        S2_Code["Code: app/sources/health_canada/dpd_crawler.py<br/>infowatch/adapter.py"]
        S2_Proto["Protocol: DPD REST API + InfoWatch Scraper + PDF Extractor"]
        S2_Key["Key Identifier: 8-digit Drug Identification Number (DIN)"]
        S2_Data["Data: Product Monographs, Marketed Status, Recall Advisories"]
    end

    subgraph S3 ["🇦🇺 3. Australia TGA"]
        S3_Name["Official: Therapeutic Goods Administration (TGA)"]
        S3_URL["URL: www.tga.gov.au/search?keywords="]
        S3_Code["Code: app/sources/australia_tga/tga_crawler.py<br/>adapter.py"]
        S3_Proto["Protocol: HTTPS GET (Akamai-resilient browser headers)"]
        S3_Key["Key Identifier: ARTG Number (AUST R / AUST L)"]
        S3_Data["Data: Product Information (PI), Consumer Medicine Info (CMI), Alerts"]
    end

    subgraph S4 ["🚨 4. FDA MedWatch"]
        S4_Name["Official: FDA MedWatch Adverse Event Reporting Program"]
        S4_URL["URL: www.fda.gov/safety/medwatch & api.fda.gov/drug/event.json"]
        S4_Code["Code: app/sources/fda_medwatch/medwatch_crawler.py<br/>adapter.py"]
        S4_Proto["Protocol: openFDA FAERS REST API + MedWatch RSS XML feed"]
        S4_Key["Key Identifier: MW-FAERS-XXXXXX / MW-RECALL-XXXXXX"]
        S4_Data["Data: Serious Patient Reactions, Hospitalizations, Class I/II Recalls"]
    end

    subgraph S5 ["🇬🇧 5. UK MHRA"]
        S5_Name["Official: UK Medicines and Healthcare products Regulatory Agency"]
        S5_URL["URL: www.gov.uk/drug-safety-update & yellowcard.mhra.gov.uk"]
        S5_Code["Code: app/sources/uk_mhra/mhra_crawler.py<br/>adapter.py"]
        S5_Proto["Protocol: GOV.UK Open JSON API + ATOM Feed + Yellow Card Scheme"]
        S5_Key["Key Identifier: UK Product Licence (PL / PLGB)"]
        S5_Data["Data: Monthly Drug Safety Updates, CHM Advice, Yellow Card CTA"]
    end

    S1 & S2 & S3 & S4 & S5 --> IngestionHub["Canonical Data Normalization<br/>(dict with standardized medicine & safety context)"]
    IngestionHub --> DBService["DatabaseService Engine<br/>(app/services/database_service.py)"]
    DBService --> Storage[("SQLite Relational Store<br/>Scoped by (source, drug_name)")]
    Storage --> Delivery["Unified Delivery: Web UI (app/ui.py) & REST API (app/api/drugs.py)"]
"""

# ==============================================================================
# DIAGRAM 04: CRAWLER ARCHITECTURE
# ==============================================================================
DIAGRAMS["04-crawler-architecture"] = """flowchart TD
    ClientReq([Search Request / Scheduled Trigger]) --> Manager["FastAPI Controller<br/>(app/main.py / app/api/drugs.py)"]

    Manager --> WorkerPool{"asyncio.gather(*tasks)<br/>Timeout: 4.0s - 12.0s per engine"}

    subgraph IngestionAdapters ["Source Adapter Layer"]
        WorkerPool --> A_FDA["FDACrawler (app/crawler/fda_crawler.py)"]
        WorkerPool --> A_HC["HealthCanadaAdapter (app/sources/health_canada/)"]
        WorkerPool --> A_TGA["AustraliaTGAAdapter (app/sources/australia_tga/)"]
        WorkerPool --> A_MW["FDAMedWatchAdapter (app/sources/fda_medwatch/)"]
        WorkerPool --> A_MHRA["UKMHRAAdapter (app/sources/uk_mhra/)"]
    end

    subgraph DiscoveryMechanism ["URL & Endpoint Discovery"]
        A_FDA --> D_FDA["POST index.cfm?event=searchResult.page<br/>ViewState + Cookie Tracking"]
        A_HC --> D_HC["Query /api/drug/dinnumber<br/>Discover InfoWatch monthly index HTML"]
        A_TGA --> D_TGA["GET /search?keywords={query}<br/>Parse document search cards"]
        A_MW --> D_MW["Query api.fda.gov/drug/event.json<br/>Parse /medwatch/rss.xml"]
        A_MHRA --> D_MHRA["Query /drug-safety-update.json?keywords={q}<br/>Poll /drug-safety-update.atom"]
    end

    subgraph TransportLayer ["HTTP Fetcher & Resilience (httpx.AsyncClient)"]
        D_FDA & D_HC & D_TGA & D_MW & D_MHRA --> Fetcher["Async HTTP Fetcher<br/>Browser Headers, SSL Context, Exponential Backoff"]
        Fetcher --> RateLimit{"Status Code Check"}
        RateLimit -->|200 OK| RawContent["Raw HTML / JSON / XML / PDF"]
        RateLimit -->|403 / 429 / Timeout| FallbackRegistry["Curated Reference Registry<br/>(Resilience against CDN blocks / rate limits)"]
    end

    subgraph ParserLayer ["Document Parsers & Content Extractors"]
        RawContent --> P_FDA["FDASRLCScraper: BeautifulSoup table parser<br/>Regex Section Classification"]
        RawContent --> P_HC["DPD Parser + InfoWatch Classifier<br/>(ArticleType: Recall, Letter, Review)"]
        RawContent --> P_TGA["TGA HTML Document Parser<br/>Extract Sponsor, AUST R, PI/CMI"]
        RawContent --> P_MW["openFDA JSON Parser + ElementTree XML<br/>Aggregate serious patient outcomes"]
        RawContent --> P_MHRA["GOV.UK JSON & ATOM Parser<br/>Extract title, date, summary, PLGB"]
    end

    FallbackRegistry --> Normalizer
    P_FDA & P_HC & P_TGA & P_MW & P_MHRA --> Normalizer["NormalizationService<br/>(app/services/normalization.py)"]
    Normalizer --> Validator["ValidationService<br/>(app/services/validation.py)"]
    Validator --> Hasher["ChangeDetectionService<br/>(SHA-256 Content Hash)"]
    Hasher --> Storage[("DatabaseService -> SQLite Storage<br/>(medicine_safety.db)")]
"""

# ==============================================================================
# DIAGRAM 05: PDF DOCUMENT EXTRACTION FLOW
# ==============================================================================
DIAGRAMS["05-pdf-document-extraction"] = """flowchart TD
    SourceTrigger([Regulatory Document Trigger / User Upload]) --> IngestionPath{Ingestion Source}

    IngestionPath -->|Health Canada InfoWatch| HC_Adapter["HealthCanadaAdapter._route_pdf_to_extractor()<br/>(app/sources/health_canada/infowatch/adapter.py)"]
    IngestionPath -->|User UI Upload| WebUpload["POST /api/upload<br/>(pdf_extractor/backend/api/upload.py)"]
    IngestionPath -->|API Request| APICall["POST /api/extract<br/>(pdf_extractor/backend/api/extraction.py)"]

    HC_Adapter -.->|HTTP POST JSON: url, source| APICall
    WebUpload --> SaveFile["Save PDF to uploads/ directory<br/>Generate UUID doc_id"]
    APICall --> SaveFile

    SaveFile --> Orchestrator["SectionExtractor.extract()<br/>(pdf_extractor/backend/extraction/section_extractor.py)"]

    subgraph EnginePipeline ["Deterministic Extraction Pipeline (100% Deterministic, Zero LLM)"]
        direction TB
        
        Step1["1. PDFReader (pdf/reader.py)<br/>Open via PyMuPDF fitz<br/>Extract text blocks with (x0, y0, x1, y1) & font stats"]
        
        Step2{"2. OCR Detector (pdf/ocr.py)<br/>Text density < 50 chars/page?"}
        
        Step2_Yes["Run Tesseract OCR on page pixmap<br/>(pytesseract.image_to_string)"]
        
        Step3["3. Margin & Noise Cleaner (pdf/cleaner.py)<br/>Identify recurring headers & footers<br/>Filter page margins by coordinate thresholds"]
        
        Step4["4. HeadingDetector (pdf/headings.py)<br/>Multi-signal classifier: numbering regex (16.1)<br/>Relative font size clustering & bold flags"]
        
        Step5["5. TableExtractor (pdf/tables.py)<br/>pdfplumber graphical vector line detection<br/>Extract structured 2D table matrices"]
        
        Step6["6. SectionTreeBuilder (pdf/sections.py)<br/>Build prefix tree hierarchy (e.g. 16 -> 16.1 -> 16.1.1)"]
        
        Step7["7. BoundaryDetector (extraction/boundary_detector.py)<br/>Strict coordinate boundary cutoff<br/>STOPS strictly before sibling section (16.2) on same page"]
        
        Step8["8. ExtractionValidator (extraction/validator.py)<br/>Verify section bounds, table completeness, reading order"]
    end

    Orchestrator --> Step1
    Step1 --> Step2
    Step2 -->|YES: Scanned Page| Step2_Yes --> Step3
    Step2 -->|NO: Native Digital| Step3
    Step3 --> Step4 --> Step5 --> Step6 --> Step7 --> Step8

    Step8 --> ExportEngine["ExportService (pdf_extractor/backend/services/export_service.py)"]

    subgraph Exports ["Multi-Format Output Generation"]
        E_JSON[".json: Full AST with block bounding boxes"]
        E_CSV[".csv: Tabular section content"]
        E_XLSX[".xlsx: Excel workbook with formatted tables"]
        E_HTML[".html: Renderable report snippet"]
        E_TXT[".txt: Plaintext extraction"]
    end

    ExportEngine --> E_JSON & E_CSV & E_XLSX & E_HTML & E_TXT

    Step8 --> DBStore[("SQLite: extractor.db<br/>(DocumentRecord, ExtractionRecord, ContentBlockRecord)")]
    Step8 --> ReturnResult["ExtractionResult Payload<br/>Returns to caller / Health Canada adapter"]
    ReturnResult -.->|Appended to Advisory| SafetyRecord["Stored in medicine_safety.db<br/>as safety_labeling_changes.updated_text"]
"""

# ==============================================================================
# DIAGRAM 06: MEDICINE SEARCH FLOW
# ==============================================================================
DIAGRAMS["06-medicine-search-flow"] = """flowchart TD
    Start([User enters query: 'Ozempic' & selects Source]) --> APIEntry["GET /search or GET /api/drugs/search<br/>Parameters: q='Ozempic', source='ALL'"]

    APIEntry --> Normalize["NormalizationService.normalize_drug_name('Ozempic')<br/>-> 'ozempic' (trimmed, lowercase)"]

    Normalize --> CheckDB["Query SQLite Database (medicine_safety.db)<br/>DatabaseService.search_drugs(db, 'ozempic', source)"]

    CheckDB --> DecisionCache{Records exist in DB<br/>and force_refresh=False?}

    DecisionCache -->|YES: Cache Hit| BuildCached["Build DrugSearchResultItem list<br/>Calculate safety_change_count<br/>Fetch latest last_verified_at"]
    BuildCached --> ReturnFast["Return Results Immediately<br/>Response Latency: <15ms"]

    DecisionCache -->|NO: Cache Miss / Refresh| DispatchCrawl["Initialize Parallel Crawl Tasks (asyncio.gather)<br/>Targeting selected sources or ALL"]

    subgraph ParallelExecution ["Parallel Acquisition (4.0s Timeout Ceiling)"]
        direction TB
        C_HC["Health Canada Adapter<br/>Search DPD + InfoWatch"]
        C_FDA["FDA Crawler & Scraper<br/>Search SrLC ASPX"]
        C_TGA["Australia TGA Adapter<br/>Search tga.gov.au"]
        C_MW["FDA MedWatch Adapter<br/>Search FAERS + Recalls"]
        C_MHRA["UK MHRA Adapter<br/>Search gov.uk/drug-safety-update"]
    end

    DispatchCrawl --> C_HC & C_FDA & C_TGA & C_MW & C_MHRA

    subgraph ErrorHandling ["Per-Source Fault Isolation"]
        C_HC -.->|Error| Log1["Log HC Error & rollback(db)"]
        C_FDA -.->|Error| Log2["Log FDA Error & rollback(db)"]
        C_TGA -.->|Error| Log3["Log TGA Error & rollback(db)"]
        C_MW -.->|Error| Log4["Log MedWatch Error & rollback(db)"]
        C_MHRA -.->|Error| Log5["Log MHRA Error & rollback(db)"]
    end

    C_HC & C_FDA & C_TGA & C_MW & C_MHRA --> UpsertDB["DatabaseService.insert_or_update_drug()<br/>Unique Key: (source, normalized_name)<br/>Insert safety changes & version history"]

    UpsertDB --> CommitDB["session.commit()"]
    CommitDB --> FinalQuery["Re-query DatabaseService.search_drugs(db, 'ozempic')"]
    FinalQuery --> BuildResponse["Construct SearchResultResponse<br/>Or render_homepage_html with badges"]
    ReturnFast --> BuildResponse
    BuildResponse --> Deliver([Deliver HTTP 200 Response to Client])
"""

# ==============================================================================
# DIAGRAM 07: DATABASE ARCHITECTURE
# ==============================================================================
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
        string bbox_json "Bounding box [x0, y0, x1, y1]"
        text content_json "Structured table matrix JSON"
    }
"""

# ==============================================================================
# DIAGRAM 08: BACKEND ARCHITECTURE
# ==============================================================================
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
        R_Drugs & R_Safety & R_Admin & R_Web --> DBService["DatabaseService<br/>- insert_or_update_drug()<br/>- save_safety_change()<br/>- search_drugs()<br/>- get_safety_changes_by_drug_id()"]
        R_Drugs & R_Safety --> NormService["NormalizationService<br/>- normalize_drug_name()<br/>- normalize_text()<br/>- clean_html()"]
        R_Drugs & R_Safety --> ValidService["ValidationService<br/>- validate_record()<br/>- validate_dates()"]
        DBService --> ChangeService["ChangeDetectionService<br/>- generate_content_hash()<br/>- detect_changes() (SHA-256)"]
        R_Drugs & R_Admin --> CacheServ["CacheService<br/>- Redis / Memory Cache"]
    end

    subgraph AdaptersLayer ["Regulatory Ingestion Adapters (backend/app/sources/)"]
        R_Drugs & R_Web --> AdapterHub{"Source Orchestrator<br/>asyncio.gather"}
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

# ==============================================================================
# DIAGRAM 09: FRONTEND ARCHITECTURE
# ==============================================================================
DIAGRAMS["09-frontend-architecture"] = """flowchart TD
    User([User in Web Browser]) --> WebRoute{"URL Navigation"}

    subgraph MainAppUI ["Medicine Safety Frontend (app/ui.py - Server-Side Rendered)"]
        WebRoute -->|GET / or /search| HomeView["render_homepage_html()"]
        WebRoute -->|GET /drugs/{drug_id}| DetailView["render_drug_detail_html()"]
        WebRoute -->|GET /drugs/{drug_id}/export| ExportEndpoint["web_drug_export()"]
        WebRoute -->|GET /architecture| ArchView["architecture_diagram_view()"]

        subgraph HomeComponents ["Homepage View Components"]
            Header["Global Header: Platform Title & Source Badges<br/>🇺🇸 FDA • 🍁 Canada • 🇦🇺 TGA • 🚨 MedWatch • 🇬🇧 MHRA"]
            SearchForm["Search Form: Input Field + Source Dropdown Filter<br/>(ALL, UK_MHRA, FDA_MEDWATCH, AUSTRALIA_TGA, HEALTH_CANADA, FDA_SRLC)"]
            ResultList["Search Results Grid: Drug Cards with Status Badges<br/>- Drug Brand & Normalized Name<br/>- Active Ingredient & Formulation<br/>- Authority Application / Licence Number<br/>- Safety Changes Count & Last Verified Date<br/>- 'View Complete History' Action Button"]
        end

        HomeView --> Header --> SearchForm --> ResultList

        subgraph DetailComponents ["Specialized Detail Page Renderers"]
            DetailRouter{"Drug Source Dispatcher"}
            DetailRouter -->|source == 'UK_MHRA'| RenderMHRA["_render_uk_mhra_drug_detail()<br/>- PL/PLGB Licence Tag<br/>- Yellow Card ADR Reporting Scheme Button<br/>- Clinical Advice & Drug Safety Update Bulletins"]
            DetailRouter -->|source == 'FDA_MEDWATCH'| RenderMW["_render_fda_medwatch_drug_detail()<br/>- MedWatch Event / Recall ID Tag<br/>- Post-Marketing Reaction Signals<br/>- Form FDA 3500 Voluntary Reporting Guidelines"]
            DetailRouter -->|source == 'AUSTRALIA_TGA'| RenderTGA["_render_australia_tga_drug_detail()<br/>- ARTG AUST R / AUST L Badge<br/>- Sponsor Information & PI/CMI Leaflet Links<br/>- Product Defect & Safety Alerts"]
            DetailRouter -->|source == 'HEALTH_CANADA'| RenderHC["_render_health_canada_drug_detail()<br/>- DIN Tag & Marketed Status<br/>- Product Monograph PDF Link<br/>- Health Product InfoWatch Advisories"]
            DetailRouter -->|source == 'FDA_SRLC'| RenderFDA["_render_fda_srlc_drug_detail()<br/>- NDA/BLA Application Number<br/>- Boxed Warnings & Labeling Revisions<br/>- Chronological Change Version History"]
        end

        DetailView --> DetailRouter

        subgraph ExportActions ["Data Export Functions"]
            CSVAction["export_drug_csv(): RFC 4180 CSV attachment"]
            JSONAction["export_drug_json(): Canonical formatted JSON"]
        end

        ExportEndpoint --> CSVAction & JSONAction
    end

    subgraph PDFExtractorUI ["PDF Extractor Subsystem Frontend (pdf_extractor/frontend/)"]
        WebRoute -->|GET http://localhost:8001/| PDFIndex["index.html Dashboard"]
        PDFIndex --> Dropzone["Drag-and-Drop PDF Upload Zone"]
        PDFIndex --> SectionInputs["Main Section & Subsection Selectors (e.g. 16 -> 16.1)"]
        PDFIndex --> TableToggle["Include/Strip Tables Mode Selector"]
        PDFIndex --> AppJS["app.js Client Orchestration (Fetch API)"]
        AppJS --> ExtractionAST["Interactive Tree View & Structured HTML/JSON Viewer"]
        AppJS --> Downloads["Direct Download Buttons: XLSX, CSV, JSON, HTML, TXT"]
    end
"""

# ==============================================================================
# DIAGRAM 10: ERROR HANDLING FLOW
# ==============================================================================
DIAGRAMS["10-error-handling-flow"] = """flowchart TD
    Operation([Crawling, Extraction, or Search Operation]) --> FailurePoint{"Failure Condition"}

    %% Failure 1: Network Timeout
    FailurePoint -->|Network Timeout >4.0s / >30s| E_Timeout["httpx.TimeoutException<br/>(Slow upstream government portal)"]
    E_Timeout --> H_Timeout["Timeout Handling<br/>1. Log timeout with logger.error<br/>2. Discard URL from visited set<br/>3. Activate pre-indexed Curated Reference Registry<br/>4. Ensure sibling crawlers complete uninterrupted"]

    %% Failure 2: HTTP 403 / 429 Bot Detection
    FailurePoint -->|HTTP 403 / 429 / WAF Block| E_Block["HTTPStatusError (403 Forbidden / 429 Too Many Requests)<br/>(Akamai / Cloudflare Edge Protection)"]
    E_Block --> H_Block["Anti-Bot Resilience<br/>1. Rotate browser headers (User-Agent, Accept-Language)<br/>2. Apply exponential backoff (0.3s * 2^retry)<br/>3. If persistent, return curated benchmark dataset<br/>4. Mark CrawlRun status as partial"]

    %% Failure 3: HTML Structure / Scraping Error
    FailurePoint -->|DOM Structure Altered / Malformed HTML| E_Parse["BeautifulSoup Parse Error / Missing Tags"]
    E_Parse --> H_Parse["Fail-Safe Scraping<br/>1. Log warning: 'Failed to extract section'<br/>2. Return None for missing fields without crash<br/>3. Fall back to textual date/section regex<br/>4. Store partial record with fda_comment flag"]

    %% Failure 4: Database Transaction Failure
    FailurePoint -->|SQLAlchemy DB Error / IntegrityError| E_DB["SQLAlchemyError / Constraint Violation"]
    E_DB --> H_DB["Transaction Isolation<br/>1. db.rollback() to clear poisoned session<br/>2. Log full traceback with exc_info=True<br/>3. Prevent cascading failure to other sources<br/>4. Return existing cached records if present"]

    %% Failure 5: PDF Extractor Unreachable
    FailurePoint -->|PDF Extractor Port 8001 Unreachable| E_PDF["httpx.ConnectError / ConnectTimeout (Port 8001)"]
    E_PDF --> H_PDF["Graceful Degradation<br/>1. Catch ConnectError in _route_pdf_to_extractor()<br/>2. Log: 'PDF extractor not reachable — skipping PDF'<br/>3. Proceed with HTML advisory text only<br/>4. Zero impact on user response latency"]

    %% Failure 6: Scanned PDF / OCR Failure
    FailurePoint -->|Unreadable Scanned PDF| E_OCR["Tesseract OCR Failure / Low Confidence"]
    E_OCR --> H_OCR["OCR Fallback Pipeline<br/>1. PyMuPDF extracts embedded vector text if any<br/>2. Flag extraction confidence_score < 0.5<br/>3. Record status='partial' in ExtractionRecord<br/>4. Include raw text stream in download files"]

    H_Timeout & H_Block & H_Parse & H_DB & H_PDF & H_OCR --> RecoveryLog["Structured Audit Logging<br/>(structlog / standard logging -> CrawlRun.errors)"]
    RecoveryLog --> SafeResponse["Return Graceful Partial Response to User<br/>HTTP 200 with available authority records"]
"""

# ==============================================================================
# DIAGRAM 11: SECURITY / ACCESS FLOW
# ==============================================================================
DIAGRAMS["11-security-access-flow"] = """flowchart TD
    ClientReq([Inbound Client Request / Outbound Crawler Request]) --> SecurityCheck{"Traffic Classification"}

    %% Inbound Security
    SecurityCheck -->|Inbound Web / API Request| InboundGuard["Inbound API Security Layer"]
    
    InboundGuard --> CORSCheck{"CORS Validation<br/>(CORSMiddleware)"}
    CORSCheck -->|Origin in CORS_ORIGINS| AllowCORS["Allow Request Headers"]
    CORSCheck -->|Wildcard / Web Portal| AllowPublic["Allow Public Search Navigation"]

    AllowCORS & AllowPublic --> InputValidation{"Parameter Validation<br/>(Pydantic & FastAPI Query)"}
    InputValidation -->|q.strip(), min_length=1| SanitizeQuery["Sanitize Search Query<br/>Prevent SQL Injection via SQLAlchemy ORM Param Binding"]
    InputValidation -->|regex='^(csv|json)$'| FormatCheck["Validate Export Format String"]
    InputValidation -->|Invalid Input| Reject422["HTTP 422 Unprocessable Entity"]

    SanitizeQuery & FormatCheck --> APIKeyCheck{"Endpoint Protected?<br/>(e.g. PDF Extractor B2B)"}
    APIKeyCheck -->|X-API-Key Header Present| ValidateKey["Validate Token against Config"]
    APIKeyCheck -->|Public Medicine Search| AllowExecution["Proceed to Controller Execution"]
    ValidateKey -->|Valid| AllowExecution
    ValidateKey -->|Invalid| Reject401["HTTP 401 Unauthorized"]

    %% Outbound Crawler Security & Anti-Bot
    SecurityCheck -->|Outbound Regulatory Crawl| OutboundGuard["Outbound Crawler Security & Compliance"]

    OutboundGuard --> InspectPortal{"Target Authority Site"}
    
    InspectPortal -->|US FDA / Australia TGA / UK MHRA| ApplyHeaders["Apply Compliant Browser Headers<br/>- Realistic User-Agent<br/>- Accept, Accept-Language, Sec-Fetch-*<br/>- Strict Read-Only GET/POST"]

    ApplyHeaders --> DispatchHTTP["httpx.AsyncClient Execution"]
    DispatchHTTP --> DetectChallenge{"WAF / Bot Challenge Detected?<br/>(Akamai / Cloudflare / CAPTCHA)"}

    DetectChallenge -->|NO: Standard HTML/JSON| ProcessData["Process Regulatory Data"]
    
    DetectChallenge -->|YES: Human Verification / CAPTCHA Detected| StrictCompliance["HUMAN VERIFICATION HANDLING PROTOCOL<br/>(Strict Regulatory Compliance)"]

    StrictCompliance --> Step1["1. DO NOT attempt automated CAPTCHA bypass<br/>(Respect government Terms of Service)"]
    Step1 --> Step2["2. Log security challenge event with timestamp & URL"]
    Step2 --> Step3["3. Mark source temporarily restricted in CrawlRun"]
    Step3 --> Step4["4. Fallback to Verified Curated Reference Registry<br/>(Pre-indexed authoritative government data)"]
    Step4 --> Step5["5. Serve verified regulatory dataset to user without outage"]
"""

# ==============================================================================
# DIAGRAM 12: CURRENT IMPLEMENTED ARCHITECTURE
# ==============================================================================
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

        subgraph InProcessCrawlers ["In-Process On-Demand Crawlers (Executed directly inside API request)"]
            FDACrawl["FDACrawler & Scraper (ASPX POST)"]
            HCCrawl["HealthCanadaAdapter (DPD API + InfoWatch)"]
            TGACrawl["AustraliaTGAAdapter (HTML Scraper)"]
            MWCrawl["FDAMedWatchAdapter (openFDA REST + RSS)"]
            MHRACrawl["UKMHRAAdapter (GOV.UK JSON + ATOM)"]
        end

        subgraph FallbackRegistries ["In-Memory Curated Fallback Registries"]
            TGA_Reg["TGA_CURATED_REGISTRY (Ozempic, Warfarin, etc.)"]
            MW_Reg["MEDWATCH_CURATED_REGISTRY"]
            MHRA_Reg["MHRA_CURATED_REGISTRY"]
        end

        SQLite_Main[("SQLite Database<br/>backend/medicine_safety.db<br/>(Local file locking)")]
    end

    subgraph Service2 ["SUBSYSTEM 2: INTELLIGENT PDF SECTION EXTRACTOR (FastAPI: Port 8001)"]
        PDFApp["backend.main:app"]
        PDFExtractAPI["backend/api/extraction.py"]
        PDFUploadAPI["backend/api/upload.py"]
        PDFStatic["frontend/ (Static HTML/CSS/JS)"]

        SecExtractor["SectionExtractor Engine"]
        PyMuPDF["PyMuPDF fitz (Text & Bounding Boxes)"]
        Tesseract["pytesseract (Local OCR Fallback)"]
        Plumber["pdfplumber (Vector Table Extraction)"]

        SQLite_PDF[("SQLite Database<br/>pdf_extractor/extractor.db<br/>(Independent schema)")]
    end

    subgraph ExternalWebsites ["EXTERNAL REGULATORY WEBSITES"]
        W_FDA["accessdata.fda.gov"]
        W_HC["health-products.canada.ca"]
        W_TGA["www.tga.gov.au/search"]
        W_MW["fda.gov/safety/medwatch"]
        W_MHRA["www.gov.uk/drug-safety-update"]
    end

    UserBrowser -->|HTTP GET /search| MainApp
    UserBrowser -->|HTTP GET /| PDFStatic
    RESTClient -->|HTTP GET /api/drugs| DrugsAPI

    MainApp --> UIModule & DrugsAPI & SafetyAPI & AdminAPI
    DrugsAPI & MainApp --> DBService & NormService & ChangeService
    DrugsAPI & MainApp -->|asyncio.gather on search| InProcessCrawlers

    FDACrawl -.->|HTTP POST| W_FDA
    HCCrawl -.->|HTTP GET| W_HC
    TGACrawl -.->|HTTP GET| W_TGA
    MWCrawl -.->|HTTP GET| W_MW
    MHRACrawl -.->|HTTP GET| W_MHRA

    TGACrawl -.->|On Network Error| TGA_Reg
    MWCrawl -.->|On Network Error| MW_Reg
    MHRACrawl -.->|On Network Error| MHRA_Reg

    HCCrawl -->|HTTP POST /api/extract (Port 8001)| PDFExtractAPI
    
    DBService --> SQLite_Main
    PDFExtractAPI --> SecExtractor --> PyMuPDF & Tesseract & Plumber --> SQLite_PDF
"""

# ==============================================================================
# DIAGRAM 13: RECOMMENDED ENTERPRISE ARCHITECTURE
# ==============================================================================
DIAGRAMS["13-recommended-architecture"] = """flowchart TD
    subgraph ClientLayer ["CLIENT & INTEGRATION TIER"]
        WebUsers["Web & Mobile Users"]
        PharmaReviewers["Pharma Compliance Reviewers"]
        B2BClients["Enterprise B2B API Integrators"]
    end

    subgraph GatewayLayer ["API GATEWAY & REVERSE PROXY (Nginx / Traefik)"]
        Gateway["API Gateway / Ingress Controller<br/>- Rate Limiting (Token Bucket)<br/>- Centralized SSL / TLS Termination<br/>- JWT & API Key Authentication<br/>- Request Routing & CORS Enforcement"]
    end

    ClientLayer --> Gateway

    subgraph CoreServices ["MICROSERVICES TIER"]
        SearchService["Medicine Search Microservice<br/>(FastAPI - Read-Optimized API)"]
        CrawlerManager["Regulatory Crawler Coordinator<br/>(Scheduled & Event-Driven Triggers)"]
        ExtractionService["Clinical Document Extraction Service<br/>(Dedicated PDF / OCR Worker Pool)"]
        ChangeDetectionService["Audit & Change Tracking Service<br/>(Cryptographic Hashing & Versioning)"]
        ExportService["Reporting & Export Service<br/>(Async PDF / Excel / CSV Generator)"]
    end

    Gateway --> SearchService & ExtractionService & ExportService

    subgraph MessageBrokerTier ["ASYNCHRONOUS EVENT BUS & TASK QUEUES"]
        Broker["Message Broker & Event Bus<br/>(RabbitMQ / Apache Kafka)"]
        Q_FDA["Queue: fda.crawl.jobs"]
        Q_HC["Queue: hc.crawl.jobs"]
        Q_TGA["Queue: tga.crawl.jobs"]
        Q_MW["Queue: medwatch.crawl.jobs"]
        Q_MHRA["Queue: mhra.crawl.jobs"]
        Q_PDF["Queue: pdf.extraction.jobs"]

        Broker --> Q_FDA & Q_HC & Q_TGA & Q_MW & Q_MHRA & Q_PDF
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
        RedisCluster[("Redis Cluster (Tiered Caching & Rate Limits)<br/>- Hot Drug Record Cache (TTL: 24h)<br/>- Crawl Lock Mutexes (Redlock)")]
        PgBouncer["PgBouncer Connection Pooler"]
        PostgresDB[("PostgreSQL 16 High-Availability Cluster<br/>- drugs, safety_changes, audit_versions<br/>- pgvector for Semantic Medicine Matching<br/>- Read Replicas for High-Throughput Search")]
        ObjectStorage[("S3 / MinIO Object Storage<br/>- Regulatory PDF Archive<br/>- Product Monographs<br/>- Generated Export Bundles")]
    end

    SearchService <--> RedisCluster
    SearchService --> PgBouncer --> PostgresDB
    WorkerPoolTier --> PgBouncer
    W_PDF_Cluster <--> ObjectStorage
    ExportService <--> ObjectStorage

    subgraph ObservabilityTier ["MONITORING & OBSERVABILITY"]
        Prometheus["Prometheus Metrics Collection"]
        Grafana["Grafana Real-time Architecture Dashboards"]
        OpenTelemetry["OpenTelemetry Distributed Tracing"]
        Sentry["Sentry Automated Error & Crash Tracking"]
    end

    CoreServices & WorkerPoolTier -.-> Prometheus & OpenTelemetry & Sentry
    Prometheus --> Grafana
"""

print(f"Total diagrams defined: {len(DIAGRAMS)}")

# ==============================================================================
# WRITING MMD FILES AND RENDERING SVG & PNG
# ==============================================================================
success_count = 0
fail_count = 0

for name, mmd_content in DIAGRAMS.items():
    mmd_path = DIAGRAMS_DIR / f"{name}.mmd"
    svg_path = IMAGES_DIR / f"{name}.svg"
    png_path = IMAGES_DIR / f"{name}.png"

    # Write MMD file
    with open(mmd_path, "w", encoding="utf-8") as f:
        f.write(mmd_content.strip() + "\n")
    print(f"[{name}] Written MMD -> {mmd_path.name}")

    # Base64 encode for rendering
    encoded = base64.b64encode(mmd_content.strip().encode("utf-8")).decode("ascii")

    # Fetch SVG
    try:
        svg_url = f"https://mermaid.ink/svg/{encoded}"
        req_svg = urllib.request.Request(svg_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req_svg, timeout=15) as resp:
            svg_bytes = resp.read()
            with open(svg_path, "wb") as f:
                f.write(svg_bytes)
        print(f"  └─ Generated SVG ({len(svg_bytes):,} bytes) -> {svg_path.name}")
    except Exception as exc:
        print(f"  └─ ERROR generating SVG for {name}: {exc}")
        fail_count += 1

    # Fetch PNG
    try:
        png_url = f"https://mermaid.ink/img/{encoded}"
        req_png = urllib.request.Request(png_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req_png, timeout=15) as resp:
            png_bytes = resp.read()
            with open(png_path, "wb") as f:
                f.write(png_bytes)
        print(f"  └─ Generated PNG ({len(png_bytes):,} bytes) -> {png_path.name}")
        success_count += 1
    except Exception as exc:
        print(f"  └─ ERROR generating PNG for {name}: {exc}")
        fail_count += 1

    time.sleep(0.5)  # Be polite to the renderer

print("\n" + "=" * 60)
print(f"Summary: {success_count} diagrams rendered successfully, {fail_count} failures.")
print("=" * 60)
