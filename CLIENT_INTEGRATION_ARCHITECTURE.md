# Client API Integration & Remote Button Architecture

> **Document Version**: 1.0  
> **Status**: Architectural Proposal / Implementation Blueprint (Review Phase)  
> **Target Audience**: Development Team & Client Technical Stakeholders  

---

## 1. Executive Summary

### 1.1 The Requirement
The client wants to use our platform's capabilities (FDA drug safety crawling, adverse reactions extraction, and/or PDF section extraction) **without requiring their users or staff to ever visit our platform's web dashboard**. 

Instead:
1. The client adds a button (e.g., *"Check FDA Safety Changes"*, *"Fetch Adverse Reactions"*, or *"Extract Safety Section"*) directly onto **their own website / web application**.
2. When their user clicks that button, the client's website triggers a background API call to **our platform**.
3. Our platform crawls the FDA / processes the database / extracts the PDF in real-time or from local storage.
4. Our platform returns clean, structured data (JSON or file export) back to the client's website.
5. The client's website displays the results directly in their own custom UI (e.g., in a modal, a table, or a download prompt).

---

### 1.2 Is This Possible?
**Yes, 100% possible.** In fact, this is the industry-standard **"Headless API" / B2B Microservice** pattern. 

Our platform already runs on **FastAPI**, which is purpose-built for high-performance REST APIs. The platform's internal crawler, database, and extraction algorithms are already decoupled from the UI and accessible via JSON endpoints.

---

## 2. High-Level Architecture Diagram

```
+-------------------------------------------------------------------+
|                        CLIENT'S ECOSYSTEM                         |
|                                                                   |
|   +--------------------------+                                    |
|   |   Client's Webpage       |                                    |
|   |                          |                                    |
|   |   [ Drug Details Page ]  |                                    |
|   |                          |                                    |
|   |   +------------------+   |                                    |
|   |   | [🔘 Fetch FDA   |   |                                    |
|   |   |   Safety Changes]|   |                                    |
|   |   +--------+---------+   |                                    |
|   +------------|-------------+                                    |
|                |                                                  |
|                | (User Clicks Button)                             |
|                v                                                  |
|   +--------------------------+                                    |
|   |  Option A: Client Server |                                    |
|   |  (Backend Proxy / Node/  |                                    |
|   |   Python / PHP / Ruby)   |                                    |
+----------------|--------------------------------------------------+
                 |
                 | HTTPS Request (with API Key & Drug Name)
                 | POST / GET https://api.yourdomain.com/api/...
                 v
+-------------------------------------------------------------------+
|                         OUR PLATFORM                              |
|                                                                   |
|   +-----------------------------------------------------------+   |
|   | Nginx Reverse Proxy (SSL, Rate Limiting, CORS)            |   |
|   +-----------------------------+-----------------------------+   |
|                                 |                                 |
|                                 v                                 |
|   +-----------------------------------------------------------+   |
|   | FastAPI Backend Engine                                    |   |
|   |  - API Key Authentication & Access Control                |   |
|   |  - Request Validator                                      |   |
|   +--------------+-----------------------------+--------------+   |
|                  |                             |                  |
|                  v                             v                  |
|   +---------------------------+ +-----------------------------+   |
|   | Local SQLite/Postgres DB  | | FDA SrLC Crawler & Scraper  |   |
|   | (Instant cached lookup)   | | (Live fetch & sync if new)  |   |
|   +---------------------------+ +-----------------------------+   |
|                  |                             |                  |
|                  +--------------+--------------+                  |
|                                 |                                 |
|                                 v                                 |
|   +-----------------------------------------------------------+   |
|   | Clean Structured JSON Response or CSV/PDF Export          |   |
+---------------------------------|---------------------------------+
                                  |
                                  | HTTPS JSON Response
                                  v
+-------------------------------------------------------------------+
|   Client's Website receives JSON and renders it inside their UI:  |
|   - Latest Safety Alerts & Boxed Warnings                         |
|   - Date of Last Supplement Change                                |
|   - Formatted Adverse Reactions summary                           |
|   - Or triggers instant CSV / PDF report download                 |
+-------------------------------------------------------------------+
```

---

## 3. The 3 Approaches for Integration

Depending on the client's tech stack and development team, there are three proven approaches to implement this:

---

### Approach A: Secure Backend-to-Backend Proxy (Recommended ⭐⭐⭐)

In this approach, the client's frontend does **not** talk directly to our API. Instead, their frontend talks to their own server, which then securely forwards the request to our API.

```
Client Browser  --->  Client's Backend  --->  Our Platform API
Client Browser  <---  Client's Backend  <---  Our Platform API
```

#### Why It's Best:
1. **API Key Security**: The client's private API Key is stored securely on their server (`.env`) and is **never exposed** in the user's browser DevTools.
2. **Zero CORS Issues**: Since server-to-server calls don't run in a browser, there are no browser Cross-Origin Resource Sharing (CORS) restrictions.
3. **Data Transformation**: The client can re-format, filter, or combine our data with their own internal database before sending it to their user.
4. **Caching**: The client can cache responses on their server to minimize API calls and make button responses instantaneous.

---

### Approach B: Direct Browser-to-API Call (Lightweight / Quick Setup ⭐⭐)

In this approach, the client adds a JavaScript `fetch()` call directly inside the button click handler on their webpage.

```
Client Browser (fetch API)  =========================>  Our Platform API
Client Browser (renders data)  <======================  Our Platform API
```

#### What We Must Provide on Our Side:
1. **CORS Whitelist**: We configure our FastAPI server to explicitly permit the client's domain:
   ```python
   allow_origins = ["https://clientsite.com", "https://app.clientsite.com"]
   ```
2. **Public Scoped API Key / Domain Verification**: An API key or Origin header check to prevent unauthorized third parties from using the API.
3. **Rate Limiting**: Protect our crawler and server against spam clicks using Nginx / FastAPI rate limiters.

---

### Approach C: Embeddable Drop-In Widget / Web Component (Zero Coding for Client ⭐)

If the client's technical team does not want to write any custom UI or styling for the popup, we can provide a 1-line script tag:

```html
<!-- Client simply pastes this into their HTML -->
<script src="https://api.yourdomain.com/widget.js" 
        data-api-key="CLIENT_PUBLIC_KEY" 
        data-drug="Keytruda"
        data-button-text="View FDA Safety Changes">
</script>
```

When clicked, the script automatically opens a clean, white-labeled modal on top of their site displaying the safety changes, warnings, and export buttons.

---

## 4. How the API Endpoints Will Work for the Client

Our platform already has the core endpoints ready. Here are the primary APIs the client will call:

### 4.1 Search & Discover Drug Changes
* **Method**: `GET`
* **URL**: `https://api.yourdomain.com/api/drugs/search?q={drug_name}`
* **Description**: Checks local database. If not present or outdated, triggers the FDA crawler in the background, updates data, and returns drug information with the latest supplement dates.
* **Sample Response**:
```json
{
  "query": "Keytruda",
  "source": "FDA_SRLC",
  "results": [
    {
      "drug_id": 12,
      "drug_name": "KEYTRUDA",
      "active_ingredient": "PEMBROLIZUMAB",
      "application_number": "BLA125514",
      "safety_change_count": 8,
      "last_verified_at": "2026-03-01T10:00:00"
    }
  ]
}
```

---

### 4.2 Get Full Safety Changes & Detail
* **Method**: `GET`
* **URL**: `https://api.yourdomain.com/api/drugs/{drug_id}`
* **Sample Response**:
```json
{
  "id": 12,
  "display_name": "KEYTRUDA",
  "active_ingredient": "PEMBROLIZUMAB",
  "application_number": "BLA125514",
  "safety_changes": [
    {
      "id": 45,
      "source_date": "02/15/2026",
      "supplement_number": "S-089",
      "section_names": ["WARNINGS AND PRECAUTIONS", "ADVERSE REACTIONS"],
      "change_description": "Updated immune-mediated adverse reactions...",
      "application_type": "BLA"
    }
  ]
}
```

---

### 4.3 Get Formatted Adverse Reactions Report
* **Method**: `GET`
* **URL**: `https://api.yourdomain.com/api/drugs/{drug_id}/adverse-reactions`
* **Sample Response**:
```json
{
  "drug_name": "KEYTRUDA",
  "active_ingredient": "PEMBROLIZUMAB",
  "source_date": "02/15/2026",
  "adverse_reactions_sections": [
    {
      "heading": "6.1 Clinical Trials Experience",
      "content": "The following clinically significant adverse reactions are described..."
    }
  ]
}
```

---

### 4.4 Direct Export Download (CSV / JSON)
* **Method**: `GET`
* **URL**: `https://api.yourdomain.com/api/drugs/{drug_id}/export?format=csv`
* **Result**: Direct download file stream for the user (`.csv` or `.json`).

---

## 5. Concrete Code Snippets for the Client

Here are the exact code templates we will provide to the client:

### 5.1 Client's Frontend Button (HTML & JavaScript)

The client can drop this directly into their product/drug page:

```html
<!-- Client Website: Button and Results Container -->
<div class="fda-safety-container">
  <button id="fetch-safety-btn" class="btn-primary" onclick="fetchFdaSafety('KEYTRUDA')">
    <span id="btn-text">🔍 Check FDA Safety Updates</span>
    <span id="btn-spinner" style="display:none;">⏳ Checking FDA...</span>
  </button>

  <!-- Container where results will be rendered -->
  <div id="safety-results-card" style="display:none; margin-top: 15px; border: 1px solid #ddd; padding: 15px; border-radius: 8px;">
    <h3 id="result-drug-title"></h3>
    <p><strong>Active Ingredient:</strong> <span id="result-ingredient"></span></p>
    <p><strong>Latest Update Date:</strong> <span id="result-date"></span></p>
    <div id="result-changes-list"></div>
    <a id="download-csv-btn" href="#" target="_blank" class="btn-secondary" style="margin-top: 10px; display: inline-block;">Download Full CSV Report</a>
  </div>
</div>

<script>
async function fetchFdaSafety(drugName) {
  const btn = document.getElementById('fetch-safety-btn');
  const spinner = document.getElementById('btn-spinner');
  const btnText = document.getElementById('btn-text');
  const resultsCard = document.getElementById('safety-results-card');

  try {
    // 1. Show loading state
    btn.disabled = true;
    btnText.style.display = 'none';
    spinner.style.display = 'inline';

    // 2. Call our API (or client's backend proxy)
    const response = await fetch(`https://api.yourdomain.com/api/drugs/search?q=${encodeURIComponent(drugName)}`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        // Optional API Key header:
        // 'X-API-Key': 'client_api_key_here'
      }
    });

    if (!response.ok) {
      throw new Error(`API returned status ${response.status}`);
    }

    const data = await response.json();

    if (!data.results || data.results.length === 0) {
      alert(`No FDA safety data found for ${drugName}.`);
      return;
    }

    const topDrug = data.results[0];

    // 3. Fetch detailed changes for the top matched drug
    const detailResponse = await fetch(`https://api.yourdomain.com/api/drugs/${topDrug.drug_id}`);
    const detailData = await detailResponse.json();

    // 4. Render the data into the client's webpage
    document.getElementById('result-drug-title').innerText = detailData.display_name;
    document.getElementById('result-ingredient').innerText = detailData.active_ingredient || 'N/A';
    document.getElementById('result-date').innerText = detailData.safety_changes[0]?.source_date || 'N/A';
    
    // Render safety changes
    const changesContainer = document.getElementById('result-changes-list');
    changesContainer.innerHTML = '';
    
    detailData.safety_changes.slice(0, 3).forEach(change => {
      const item = document.createElement('div');
      item.style.marginBottom = '8px';
      item.innerHTML = `<strong>${change.source_date}</strong> (${change.supplement_number || 'Supplement'}): <em>${(change.section_names || []).join(', ')}</em>`;
      changesContainer.appendChild(item);
    });

    // Setup CSV Download link
    const csvBtn = document.getElementById('download-csv-btn');
    csvBtn.href = `https://api.yourdomain.com/api/drugs/${topDrug.drug_id}/export?format=csv`;

    // Reveal results
    resultsCard.style.display = 'block';

  } catch (error) {
    console.error('Error fetching FDA data:', error);
    alert('Failed to retrieve FDA safety information. Please try again later.');
  } finally {
    // 5. Restore button state
    btn.disabled = false;
    btnText.style.display = 'inline';
    spinner.style.display = 'none';
  }
}
</script>
```

---

### 5.2 Client's Backend Proxy Code (Node.js / Express Example)

If the client prefers Approach A (Secure Backend Proxy):

```javascript
// Express.js route on Client's Server
const express = require('express');
const axios = require('axios');
const router = express.Router();

const OUR_PLATFORM_BASE_URL = process.env.OUR_PLATFORM_URL || 'https://api.yourdomain.com';
const API_SECRET_KEY = process.env.MEDICINE_SAFETY_API_KEY;

router.get('/fda-safety/:drugName', async (req, res) => {
  try {
    const { drugName } = req.params;

    // Call our platform with private API key
    const response = await axios.get(`${OUR_PLATFORM_BASE_URL}/api/drugs/search`, {
      params: { q: drugName },
      headers: {
        'X-API-Key': API_SECRET_KEY
      },
      timeout: 15000 // 15s timeout
    });

    // Return the data directly to their frontend
    return res.json({
      success: true,
      data: response.data
    });
  } catch (err) {
    console.error('Failed to proxy request to Medicine Safety API:', err.message);
    return res.status(502).json({
      success: false,
      message: 'Safety data provider unavailable'
    });
  }
});

module.exports = router;
```

---

## 6. What Needs to Be Done on Our Platform (Implementation Checklist)

To make this seamless, secure, and production-ready for the client, here are the exact adjustments we need to configure on our platform:

| Task | Area | Description | Priority |
| :--- | :--- | :--- | :--- |
| **1. CORS Configuration** | `backend/app/config.py` & `main.py` | Add the client's domain to `CORS_ORIGINS` so their browser requests aren't blocked by CORS policy. | High |
| **2. API Key Authentication** | `backend/app/api/auth.py` | Implement a lightweight API Key middleware (`X-API-Key`) so only authorized clients can call the endpoints. | High |
| **3. Domain / SSL Setup** | `nginx/medicine-safety.conf` | Host the backend on a public domain with HTTPS (Let's Encrypt SSL certificate) so the client can make secure `https://` calls. | High |
| **4. Rate Limiting & Timeouts** | Nginx & FastAPI | Configure burst limits so crawler calls cannot be spammed or overloaded. | Medium |
| **5. Webhook / Asynchronous Support** *(Optional)* | Background Tasks | If a drug has never been crawled before and FDA takes 5-10s, return `status: "processing"` with a job ID or send a webhook callback when complete. | Optional |
| **6. Interactive Swagger / OpenAPI Docs** | `/docs` | Provide the client's developers with a clean Swagger API playground (`https://api.yourdomain.com/docs`) to test endpoints interactively. | Medium |

---

## 7. Clarifying Questions for the Client

Before we begin coding the integration features, please review these questions with the client:

1. **Which specific action should the button trigger?**
   - *Option 1*: Quick check of the latest safety changes & date.
   - *Option 2*: Detailed list of all historical safety labeling changes.
   - *Option 3*: Adverse Reactions section extract.
   - *Option 4*: Instant one-click file download (CSV / PDF report).
   - *Option 5*: A combination of the above (e.g., summary popup with a download button).

2. **Which integration approach do they prefer?**
   - **Approach A** (Client Backend Proxy - most secure, recommended).
   - **Approach B** (Direct Frontend JavaScript call - fastest to implement).
   - **Approach C** (Embeddable Widget / Iframe provided by us).

3. **What is the client's website domain?**
   - We need this to configure the CORS security policy (e.g., `https://clientcompany.com`).

4. **Do they want an API Key system?**
   - Recommended so that only their website can call our endpoints and avoid unauthorized usage by third parties.

---

## 8. Summary & Next Step

* **Is it possible?** **Yes**, completely possible and very straightforward.
* **Current Status**: All required documentation, architectural flows, and code examples have been created in this document.
* **Next Step**: Share this document with the client or confirm their preferences on Questions 1 & 2 above. Once you give approval, we will implement the CORS updates, API Key authentication, and any requested response formats.
