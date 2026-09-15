# Architecture Documentation & Diagram Catalog

This directory contains the official software architecture documentation, system design specifications, and diagram visual assets for the **Medicine Regulatory Safety Intelligence & Intelligent Document Processing Platform**.

---

## 1. Documentation Structure

```
docs/architecture/
├── ARCHITECTURE.md          # Primary Architecture Specification (19 Sections)
├── README.md                # This directory index & asset catalog
├── SYSTEM_ARCHITECTURE.svg  # High-resolution standalone vector diagram (1600x980)
├── diagrams/                # Editable Mermaid source files (.mmd)
│   ├── 01-system-architecture.mmd
│   ├── 02-end-to-end-data-flow.mmd
│   ├── 03-five-regulatory-sources.mmd
│   ├── 04-crawler-architecture.mmd
│   ├── 05-pdf-document-extraction.mmd
│   ├── 06-medicine-search-flow.mmd
│   ├── 07-database-architecture.mmd
│   ├── 08-backend-architecture.mmd
│   ├── 09-frontend-architecture.mmd
│   ├── 10-error-handling-flow.mmd
│   ├── 11-security-access-flow.mmd
│   ├── 12-current-architecture.mmd
│   └── 13-recommended-architecture.mmd
└── images/                  # Rendered High-Resolution Assets (PNG + SVG)
    ├── 01-system-architecture.png & .svg
    ├── 02-end-to-end-data-flow.png & .svg
    ├── 03-five-regulatory-sources.png & .svg
    ├── 04-crawler-architecture.png & .svg
    ├── 05-pdf-document-extraction.png & .svg
    ├── 06-medicine-search-flow.png & .svg
    ├── 07-database-architecture.png & .svg
    ├── 08-backend-architecture.png & .svg
    ├── 09-frontend-architecture.png & .svg
    ├── 10-error-handling-flow.png & .svg
    ├── 11-security-access-flow.png & .svg
    ├── 12-current-architecture.png & .svg
    └── 13-recommended-architecture.png & .svg
```

---

## 2. Complete Diagram Catalog

| # | Diagram Title | Editable Source (.mmd) | Vector Image (.svg) | Presentation Image (.png) |
|---|---|---|---|---|
| **01** | **System Architecture** | [01-system-architecture.mmd](diagrams/01-system-architecture.mmd) | [01-system-architecture.svg](images/01-system-architecture.svg) | [01-system-architecture.png](images/01-system-architecture.png) |
| **02** | **End-to-End Data Flow** | [02-end-to-end-data-flow.mmd](diagrams/02-end-to-end-data-flow.mmd) | [02-end-to-end-data-flow.svg](images/02-end-to-end-data-flow.svg) | [02-end-to-end-data-flow.png](images/02-end-to-end-data-flow.png) |
| **03** | **Five Regulatory Sources** | [03-five-regulatory-sources.mmd](diagrams/03-five-regulatory-sources.mmd) | [03-five-regulatory-sources.svg](images/03-five-regulatory-sources.svg) | [03-five-regulatory-sources.png](images/03-five-regulatory-sources.png) |
| **04** | **Crawler Architecture** | [04-crawler-architecture.mmd](diagrams/04-crawler-architecture.mmd) | [04-crawler-architecture.svg](images/04-crawler-architecture.svg) | [04-crawler-architecture.png](images/04-crawler-architecture.png) |
| **05** | **PDF / Document Extraction** | [05-pdf-document-extraction.mmd](diagrams/05-pdf-document-extraction.mmd) | [05-pdf-document-extraction.svg](images/05-pdf-document-extraction.svg) | [05-pdf-document-extraction.png](images/05-pdf-document-extraction.png) |
| **06** | **Medicine Search Flow** | [06-medicine-search-flow.mmd](diagrams/06-medicine-search-flow.mmd) | [06-medicine-search-flow.svg](images/06-medicine-search-flow.svg) | [06-medicine-search-flow.png](images/06-medicine-search-flow.png) |
| **07** | **Database Architecture (ERD)** | [07-database-architecture.mmd](diagrams/07-database-architecture.mmd) | [07-database-architecture.svg](images/07-database-architecture.svg) | [07-database-architecture.png](images/07-database-architecture.png) |
| **08** | **Backend Architecture** | [08-backend-architecture.mmd](diagrams/08-backend-architecture.mmd) | [08-backend-architecture.svg](images/08-backend-architecture.svg) | [08-backend-architecture.png](images/08-backend-architecture.png) |
| **09** | **Frontend Architecture** | [09-frontend-architecture.mmd](diagrams/09-frontend-architecture.mmd) | [09-frontend-architecture.svg](images/09-frontend-architecture.svg) | [09-frontend-architecture.png](images/09-frontend-architecture.png) |
| **10** | **Error Handling Flow** | [10-error-handling-flow.mmd](diagrams/10-error-handling-flow.mmd) | [10-error-handling-flow.svg](images/10-error-handling-flow.svg) | [10-error-handling-flow.png](images/10-error-handling-flow.png) |
| **11** | **Security & Access Flow** | [11-security-access-flow.mmd](diagrams/11-security-access-flow.mmd) | [11-security-access-flow.svg](images/11-security-access-flow.svg) | [11-security-access-flow.png](images/11-security-access-flow.png) |
| **12** | **Current Implemented Architecture** | [12-current-architecture.mmd](diagrams/12-current-architecture.mmd) | [12-current-architecture.svg](images/12-current-architecture.svg) | [12-current-architecture.png](images/12-current-architecture.png) |
| **13** | **Recommended Enterprise Architecture** | [13-recommended-architecture.mmd](diagrams/13-recommended-architecture.mmd) | [13-recommended-architecture.svg](images/13-recommended-architecture.svg) | [13-recommended-architecture.png](images/13-recommended-architecture.png) |

---

## 3. How to View and Edit the Diagrams

### 3.1 Viewing Images
- **PNG Files**: Optimized for Microsoft PowerPoint, Google Slides, pitch decks, executive summaries, and standard image viewers. Located in `docs/architecture/images/*.png`.
- **SVG Files**: Infinite vector scaling without pixelation, ideal for retina displays, printing, and embedding in markdown previewers or web applications. Located in `docs/architecture/images/*.svg`.
- **In-App Live Visualizer**: Start the backend (`python backend/app/main.py`) and navigate to `http://localhost:8000/architecture` to interact with the full-screen visualizer.

### 3.2 Editing Diagrams
Each diagram is stored as a clean, version-controlled Mermaid source file (`.mmd`) in `docs/architecture/diagrams/`. You can edit them using:
1. **Mermaid Live Editor**: Copy and paste any `.mmd` contents into [mermaid.live](https://mermaid.live).
2. **VS Code / IDE Preview**: Use the "Markdown Preview Mermaid Support" extension in your editor.
3. **GitHub Native Rendering**: Wrap the contents in a ` ```mermaid ` code block directly inside any GitHub Markdown document.

---

## 4. How to Regenerate Diagram Assets

If you modify any `.mmd` file in `docs/architecture/diagrams/`, you can regenerate all corresponding SVG and PNG assets using the provided builder script:

```bash
# Run from repository root
python3 backend/scripts/build_all_assets.py
```

The script automatically compresses the diagram source and fetches crisp, production-grade vector SVG and raster PNG files, placing them into `docs/architecture/images/`.
