# Intelligent PDF Section Extractor - Client API Integration Architecture

> **Document Version**: 1.0  
> **Status**: Architectural Blueprint & Implementation Guide  
> **Target Audience**: Development Team & Client Technical Stakeholders  
> **Related Module**: [`pdf_extractor`](file:///Users/satya/Desktop/webcrwler/pdf_extractor)

---

## 1. Executive Summary

### 1.1 The Client's Requirement
The client wants to use our **Intelligent PDF Section Extractor engine** (which deterministically extracts hierarchical sections like **Section 16 → 16.1**, tables, lists, and metadata without LLMs) **from their own website**:
- The client does **not** want their users or staff to navigate to our platform's dashboard.
- The client wants to place a button on **their website** (e.g., *"Extract Section 16.1"*, *"Extract Tables"*, or *"Process Clinical Study Report"*).
- When clicked, their site calls our API, sends the PDF (or a PDF URL / file path), extracts the exact section, and displays the structured content or triggers an instant Excel/JSON download.

---

### 1.2 Is This Possible?
**Yes, 100% possible.** The PDF extractor backend is already built on **FastAPI**, fully modularized, and exposes REST endpoints for file upload, extraction, and downloads. 

The client can integrate it in as little as **one HTTP request**.

---

## 2. High-Level Integration Architecture

```
+-----------------------------------------------------------------------------------+
|                                 CLIENT'S WEBSITE                                  |
|                                                                                   |
|   +---------------------------------------------------------------------------+   |
|   |  Client Webpage (e.g., Document Management / Clinical Trials Portal)       |   |
|   |                                                                           |   |
|   |  [ Choose PDF: clinical_report.pdf ]                                      |   |
|   |  Target Section: [ 16.1 ]                                                 |   |
|   |                                                                           |   |
|   |  +--------------------------------------------------------------------+   |   |
|   |  |  🔘 [ Extract Section & Generate Excel ]                            |   |   |
|   |  +---------------------------------+----------------------------------+   |   |
|   +------------------------------------|--------------------------------------+   |
|                                        |                                          |
|                                        | (Click Event)                            |
|                                        v                                          |
|   +---------------------------------------------------------------------------+   |
|   |  Option A: Client's Backend Server (Node.js, Python, PHP, Ruby, Java)     |   |
|   |  Option B: Direct Browser fetch() via HTTPS                               |   |
|   +------------------------------------+--------------------------------------+   |
+----------------------------------------|------------------------------------------+
                                         |
                                         | HTTPS POST /api/extract
                                         | (Multipart Form or JSON Payload)
                                         v
+-----------------------------------------------------------------------------------+
|                            OUR PDF EXTRACTOR BACKEND                              |
|                                                                                   |
|   +---------------------------------------------------------------------------+   |
|   | Nginx Gateway & Reverse Proxy (SSL/HTTPS, Rate Limiting, File Size Limit)  |   |
|   +------------------------------------+--------------------------------------+   |
|                                        |                                          |
|                                        v                                          |
|   +---------------------------------------------------------------------------+   |
|   | FastAPI Application Engine                                                |   |
|   |   - API Key Authentication (`X-API-Key`)                                  |   |
|   |   - PDF Reader & Validation (fitz / PyMuPDF)                              |   |
|   |   - Typography & Layout Geometry Engine                                   |   |
|   |   - Multi-Signal Heading Classifier & TOC Discriminator                   |   |
|   |   - Strict Sibling Boundary Truncator (stops strictly at 16.2)            |   |
|   |   - Table Association & Export Generator (JSON, XLSX, CSV, TXT)          |   |
|   +------------------------------------+--------------------------------------+   |
|                                        |                                          |
|                                        v                                          |
|   +---------------------------------------------------------------------------+   |
|   | Structured Response Payload:                                              |   |
|   |   - Clean Plain Text & Markdown                                           |   |
|   |   - Structured Table Matrix & Column Headers                              |   |
|   |   - Page-by-Page Bounding Box Block Trace                                 |   |
|   |   - Audit Checklist & Confidence Score (0.0 - 1.0)                        |   |
|   |   - Direct Download URLs for .xlsx, .json, .csv, .txt                     |   |
|   +------------------------------------+--------------------------------------+   |
+----------------------------------------|------------------------------------------+
                                         |
                                         | HTTPS JSON / File Stream Response
                                         v
+-----------------------------------------------------------------------------------+
|  Client Website receives the response:                                            |
|   - Renders extracted text & interactive table directly in their web UI           |
|   - OR automatically triggers immediate browser download of the styled Excel file |
+-----------------------------------------------------------------------------------+
```

---

## 3. Integration Workflows (Choose What Fits the Client)

### Workflow 1: Single-Step Direct Upload & Extract (Recommended for Client Frontend ⭐⭐⭐)
The client makes **one single request**. They send the PDF file and the desired section parameters in a single `multipart/form-data` request, and receive the extracted JSON and download URLs immediately.

* **Client action**: Select PDF → Click Button.
* **Network**: 1 API call (`POST /api/extract-direct`).
* **Response**: Instant JSON with text, tables, and Excel download links.

---

### Workflow 2: URL-Based Extraction (Best for Cloud/S3 Systems ⭐⭐⭐)
If the client already hosts their PDF documents in AWS S3, Google Cloud Storage, or an internal server, their users do **not** need to upload the file.

* **Client sends**:
  ```json
  {
    "pdf_url": "https://client-storage.com/documents/report_2026.pdf",
    "main_section": "16",
    "target_subsection": "16.1"
  }
  ```
* **Our platform**: Streams the PDF from the URL into memory, executes deterministic extraction, and returns the result.

---

### Workflow 3: Two-Step Pipeline (Current Native API)
1. **Upload**: Client calls `POST /api/upload` with the PDF → receives `saved_filename` and `file_path`.
2. **Extract**: Client calls `POST /api/extract` with `{ "file_path": "...", "main_section": "16", "target_subsection": "16.1" }`.

---

## 4. The 2 Integration Approaches

### Approach A: Secure Backend-to-Backend Proxy (Recommended ⭐⭐⭐)

```
Client Browser  --->  Client Server  --->  Our Platform API
Client Browser  <---  Client Server  <---  Our Platform API
```

* **Why recommended**:
  * The client's private API Key is stored on their backend (`.env`) and never visible in browser inspect tools.
  * No browser CORS issues.
  * The client can save the extracted tables directly into their own database.

---

### Approach B: Direct Browser-to-API Call (Quickest Frontend Setup ⭐⭐)

```
Client Browser (JS fetch)  =======================>  Our Platform API
Client Browser (renders data)  <====================  Our Platform API
```

* **Requirements**:
  * Our FastAPI app allows the client's domain in CORS:
    ```python
    allow_origins = ["https://clientportal.com"]
    ```
  * Client includes their API Key or authorized origin header.

---

## 5. API Reference for the Client

### 5.1 Single-Step Direct Extract Endpoint (Proposed Enhancement)
* **Method**: `POST`
* **URL**: `https://api.yourdomain.com/api/extract-direct`
* **Content-Type**: `multipart/form-data`
* **Form Parameters**:
  * `file`: The PDF file binary.
  * `main_section`: (Optional, default: `"16"`)
  * `target_subsection`: (Optional, default: `"16.1"`)
  * `natural_query`: (Optional, e.g. `"Extract section 16.1 with tables"`)

#### Response Payload (`application/json`):
```json
{
  "document": "clinical_report.pdf",
  "requested_section": "16",
  "requested_subsection": "16.1",
  "start_page": 42,
  "end_page": 58,
  "subsections_found": ["16.1", "16.1.1", "16.1.2"],
  "content": "16.1 Key Safety and Clinical Findings\n\nA total of 450 subjects...",
  "structured_content": [
    {
      "type": "heading",
      "page": 42,
      "title": "16.1 Key Safety Findings",
      "level": 2
    },
    {
      "type": "paragraph",
      "page": 42,
      "text": "A total of 450 subjects were enrolled across 12 clinical centers..."
    },
    {
      "type": "table",
      "page": 44,
      "caption": "Table 16.1-1: Summary of Treatment-Emergent Adverse Events",
      "columns": ["Adverse Event", "Cohort A (N=225)", "Cohort B (N=225)", "p-value"],
      "rows": [
        {"Adverse Event": "Headache", "Cohort A (N=225)": "12 (5.3%)", "Cohort B (N=225)": "14 (6.2%)", "p-value": "0.78"},
        {"Adverse Event": "Nausea", "Cohort A (N=225)": "8 (3.5%)", "Cohort B (N=225)": "9 (4.0%)", "p-value": "0.85"}
      ]
    }
  ],
  "validation": {
    "was_main_section_found": true,
    "was_target_subsection_found": true,
    "start_page": 42,
    "end_page": 58,
    "included_sections": ["16.1", "16.1.1", "16.1.2"],
    "excluded_sections": ["16.2"],
    "tables_included_count": 3,
    "total_blocks_extracted": 87,
    "confidence_score": 0.98,
    "status_message": "Perfect extraction: Target subsection found and next sibling strictly excluded."
  },
  "download_urls": {
    "txt": "https://api.yourdomain.com/api/download/a1b2c3d4_clinical_report_16.1.txt",
    "json": "https://api.yourdomain.com/api/download/a1b2c3d4_clinical_report_16.1.json",
    "csv": "https://api.yourdomain.com/api/download/a1b2c3d4_clinical_report_16.1.csv",
    "xlsx": "https://api.yourdomain.com/api/download/a1b2c3d4_clinical_report_16.1.xlsx",
    "html": "https://api.yourdomain.com/api/download/a1b2c3d4_clinical_report_16.1.html"
  },
  "status": "success"
}
```

---

### 5.2 Download Generated Export Files
* **Method**: `GET`
* **URL**: `https://api.yourdomain.com/api/download/{filename}`
* **Returns**: Direct download file stream (`.xlsx`, `.json`, `.csv`, `.txt`, `.html`).

---

## 6. Ready-to-Use Code Snippets for the Client

### 6.1 Client Frontend Button & Modal (HTML + JavaScript)

The client can copy and paste this complete snippet directly onto their website. It includes:
1. File selector.
2. Section inputs.
3. Loading spinner.
4. Summary card with confidence score badge.
5. Extracted text preview.
6. Interactive table rendering.
7. One-click instant **Download Excel (.xlsx)** and **Download JSON** buttons.

```html
<!-- ========================================================================= -->
<!-- CLIENT WEBSITE: PDF SECTION EXTRACTOR BUTTON COMPONENT                     -->
<!-- ========================================================================= -->
<div class="pdf-extractor-widget" style="max-width: 800px; margin: 20px auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
  
  <div style="border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px; background: #ffffff; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
    <h2 style="margin-top: 0; font-size: 1.25rem; color: #1e293b;">📄 Clinical Section Extractor</h2>
    <p style="color: #64748b; font-size: 0.9rem; margin-bottom: 20px;">Extract target subsections and tables deterministically without LLMs.</p>

    <!-- File Input & Controls -->
    <div style="display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px;">
      <input type="file" id="clientPdfInput" accept=".pdf" style="flex: 1; min-width: 240px; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px;" />
      
      <input type="text" id="clientMainSection" value="16" placeholder="Parent Section (e.g. 16)" style="width: 120px; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px;" />
      
      <input type="text" id="clientTargetSubsection" value="16.1" placeholder="Target Subsection (e.g. 16.1)" style="width: 140px; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px;" />
    </div>

    <!-- Action Button -->
    <button id="clientExtractBtn" onclick="runPdfExtraction()" style="background: #2563eb; color: #ffffff; border: none; padding: 10px 20px; border-radius: 8px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 8px;">
      <span id="btnText">⚡ Extract Section 16.1</span>
      <span id="btnSpinner" style="display: none;">⏳ Extracting...</span>
    </button>
  </div>

  <!-- Results Card (Hidden initially) -->
  <div id="extractionResultsCard" style="display: none; margin-top: 20px; border: 1px solid #cbd5e1; border-radius: 12px; padding: 24px; background: #f8fafc;">
    
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h3 style="margin: 0; color: #0f172a;" id="resDocName">Extraction Results</h3>
      <span id="resConfidence" style="background: #dcfce7; color: #166534; padding: 4px 10px; border-radius: 9999px; font-size: 0.85rem; font-weight: 600;">Confidence: 100%</span>
    </div>

    <p style="font-size: 0.9rem; color: #475569;" id="resSummaryDetails"></p>

    <!-- Download Buttons -->
    <div style="display: flex; gap: 10px; margin-bottom: 20px;" id="downloadButtonGroup">
      <a id="downloadXlsxBtn" href="#" target="_blank" style="background: #059669; color: #fff; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-size: 0.85rem; font-weight: 600;">📊 Download Excel (.xlsx)</a>
      <a id="downloadJsonBtn" href="#" target="_blank" style="background: #475569; color: #fff; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-size: 0.85rem; font-weight: 600;">💾 Download JSON</a>
      <a id="downloadTxtBtn" href="#" target="_blank" style="background: #64748b; color: #fff; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-size: 0.85rem; font-weight: 600;">📝 Plain Text</a>
    </div>

    <!-- Extracted Content Preview -->
    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; max-height: 350px; overflow-y: auto;">
      <h4 style="margin-top: 0; color: #334155;">Extracted Content Preview:</h4>
      <pre id="resTextContent" style="white-space: pre-wrap; font-family: monospace; font-size: 0.85rem; color: #1e293b;"></pre>
    </div>
  </div>
</div>

<script>
// Configure your API domain
const PDF_API_BASE = 'https://api.yourdomain.com';

async function runPdfExtraction() {
  const fileInput = document.getElementById('clientPdfInput');
  const mainSec = document.getElementById('clientMainSection').value.trim() || '16';
  const targetSec = document.getElementById('clientTargetSubsection').value.trim() || '16.1';
  
  const extractBtn = document.getElementById('clientExtractBtn');
  const btnText = document.getElementById('btnText');
  const btnSpinner = document.getElementById('btnSpinner');
  const resultsCard = document.getElementById('extractionResultsCard');

  if (!fileInput.files || fileInput.files.length === 0) {
    alert('Please select a PDF file first.');
    return;
  }

  const file = fileInput.files[0];

  try {
    // 1. Show loading state
    extractBtn.disabled = true;
    btnText.style.display = 'none';
    btnSpinner.style.display = 'inline';

    // 2. Prepare multipart form data
    const formData = new FormData();
    formData.append('files', file);

    // Step A: Upload file
    const uploadRes = await fetch(`${PDF_API_BASE}/api/upload`, {
      method: 'POST',
      body: formData
    });

    if (!uploadRes.ok) throw new Error(`Upload failed with status ${uploadRes.status}`);
    const uploadData = await uploadRes.json();
    const uploadedFile = uploadData.files[0];

    // Step B: Request Extraction
    const extractRes = await fetch(`${PDF_API_BASE}/api/extract`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_path: uploadedFile.file_path,
        filename: uploadedFile.original_filename,
        main_section: mainSec,
        target_subsection: targetSec
      })
    });

    if (!extractRes.ok) throw new Error(`Extraction failed with status ${extractRes.status}`);
    const result = await extractRes.json();

    // 3. Render Results
    document.getElementById('resDocName').innerText = `${result.document} — Section ${result.requested_subsection || result.requested_section}`;
    
    const confScore = Math.round((result.validation?.confidence_score || 0) * 100);
    const confBadge = document.getElementById('resConfidence');
    confBadge.innerText = `Confidence: ${confScore}%`;
    confBadge.style.background = confScore >= 80 ? '#dcfce7' : '#fef3c7';
    confBadge.style.color = confScore >= 80 ? '#166534' : '#92400e';

    document.getElementById('resSummaryDetails').innerText = 
      `Pages ${result.start_page} to ${result.end_page} | ${result.validation?.tables_included_count || 0} Tables Included | Subsections Found: ${(result.subsections_found || []).join(', ')}`;

    // Set download links
    if (result.download_urls) {
      document.getElementById('downloadXlsxBtn').href = `${PDF_API_BASE}${result.download_urls.xlsx}`;
      document.getElementById('downloadJsonBtn').href = `${PDF_API_BASE}${result.download_urls.json}`;
      document.getElementById('downloadTxtBtn').href = `${PDF_API_BASE}${result.download_urls.txt}`;
    }

    // Set text preview
    document.getElementById('resTextContent').innerText = result.content || 'No text extracted.';

    // Reveal card
    resultsCard.style.display = 'block';

  } catch (err) {
    console.error('PDF extraction failed:', err);
    alert('Extraction failed: ' + err.message);
  } finally {
    extractBtn.disabled = false;
    btnText.style.display = 'inline';
    btnSpinner.style.display = 'none';
  }
}
</script>
```

---

### 6.2 Client Backend Proxy (Node.js / Express Example)

If the client prefers to call our API from their server (Approach A):

```javascript
// Express.js Route on Client's Server
const express = require('express');
const multer = require('multer');
const FormData = require('form-data');
const axios = require('axios');
const fs = require('fs');

const upload = multer({ dest: 'uploads/' });
const router = express.Router();

const PDF_API_BASE_URL = process.env.PDF_EXTRACTOR_URL || 'https://api.yourdomain.com';
const API_KEY = process.env.PDF_EXTRACTOR_KEY;

router.post('/extract-clinical-section', upload.single('pdf'), async (req, res) => {
  try {
    const file = req.file;
    const { main_section = '16', target_subsection = '16.1' } = req.body;

    if (!file) {
      return res.status(400).json({ error: 'No PDF file uploaded' });
    }

    // 1. Forward file to PDF Extractor upload endpoint
    const form = new FormData();
    form.append('files', fs.createReadStream(file.path), file.originalname);

    const uploadResponse = await axios.post(`${PDF_API_BASE_URL}/api/upload`, form, {
      headers: {
        ...form.getHeaders(),
        'X-API-Key': API_KEY
      }
    });

    const savedFile = uploadResponse.data.files[0];

    // 2. Trigger section extraction
    const extractResponse = await axios.post(`${PDF_API_BASE_URL}/api/extract`, {
      file_path: savedFile.file_path,
      filename: savedFile.original_filename,
      main_section,
      target_subsection
    }, {
      headers: {
        'X-API-Key': API_KEY,
        'Content-Type': 'application/json'
      }
    });

    // 3. Clean up local temp file
    fs.unlinkSync(file.path);

    // 4. Return clean data to client's frontend
    return res.json({
      success: true,
      data: extractResponse.data
    });

  } catch (error) {
    console.error('Proxy extraction error:', error.message);
    return res.status(500).json({
      success: false,
      message: 'Failed to process PDF through extraction engine'
    });
  }
});

module.exports = router;
```

---

## 7. What Needs to Be Implemented on Our Side (Roadmap)

To deliver this to the client smoothly, we will execute the following items:

| # | Feature | File / Component | Purpose |
| :--- | :--- | :--- | :--- |
| **1** | **Direct Upload & Extract Endpoint (`/api/extract-direct`)** | `pdf_extractor/backend/api/extraction.py` | Allows client to upload and extract in a **single HTTP call** instead of two. |
| **2** | **URL Ingestion Endpoint (`/api/extract-url`)** | `pdf_extractor/backend/api/extraction.py` | Allows client to pass an S3 / cloud URL so they don't have to re-upload files. |
| **3** | **Client Domain CORS Whitelist** | `pdf_extractor/backend/main.py` | Whitelists client's specific domain (currently `*` in dev, lock down for prod). |
| **4** | **API Key Authentication (`X-API-Key`)** | `pdf_extractor/backend/api/auth.py` | Secures the extractor against unauthorized public usage. |
| **5** | **File Size & Cleanup Worker** | `pdf_extractor/backend/config.py` | Configures max PDF size (e.g., 100MB) and auto-deletes temporary exports after 24 hours. |

---

## 8. Summary & Next Steps

1. **Is it possible?** **Yes, 100% possible.** The client's users can click a button on their own site, and the entire extraction will execute transparently in the background.
2. **What they receive**:
   - Clean text and markdown.
   - Fully structured tables with column headers and cell rows.
   - Block coordinates for traceability.
   - Ready-to-download formatted **Excel (.xlsx)**, **JSON**, **CSV**, and **HTML** files.
3. **Next Steps**:
   - Review this file with the client.
   - Confirm whether they prefer **Direct File Upload** (Workflow 1) or **Cloud URL** (Workflow 2).
   - Once approved, we will add the single-step `/api/extract-direct` endpoint and secure CORS/API Keys!
