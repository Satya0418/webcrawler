# Unified Client API Documentation: Website Crawler + PDF Extractor

## 1. Overview & Architecture

The Unified Client API provides a single, high-performance integration endpoint that orchestrates two independent medical intelligence subsystems:
1. **Website Crawler (`backend/`)**: Scrapes, parses, and normalizes live and indexed drug safety labeling changes (currently integrated with **US FDA SrLC** — Safety-related Labeling Changes).
2. **PDF Extractor (`pdf_extractor/`)**: Parses indexed pharmaceutical product monograph PDFs to extract structured Section 16 (*Risk & Signal Management* / *Summary of Safety Concerns*) text and clinical tables.

### Key Architecture Principles:
- **One Call, Two Independent Responses**: The client sends a single HTTP request with 6 standardized parameters.
- **Independent Response Objects**: Results are segregated into `website_Data` and `pdf_extractor_Data` with distinct titles. Neither subsystem ever overwrites, merges, or mislabels data from the other subsystem.
- **Independent Execution & Fault Tolerance**: If one subsystem has no records or experiences an upstream error, the other subsystem's data is still delivered in full with HTTP 200. Total failure (neither system has data) returns HTTP 404.
- **Preserved Existing Contracts**: The internal structured response of the PDF extractor is preserved intact under `pdf_extractor_Data.data`, and the crawler HTML is preserved under `website_Data.data[0].Data`.

---

## 2. API Endpoint Details

- **HTTP Method**: `POST` (primary integration) / `GET` (browser and manual testing)
- **Primary Endpoint**: `/api/v1/products/signal-and-risk`
- **Short Alias Endpoint**: `/api/v1/signal-and-risk`
- **Singular Alias Endpoint**: `/api/v1/product/signal-and-risk`
- **Default Port**:
  - Direct PDF Extractor Service: `8000`
  - Reverse Proxy (Nginx): `80` (or `443` over HTTPS)
- **Content-Type**: `application/json`

---

## 3. Request Parameters & Validation Contract

The endpoint accepts standard camelCase field names (with snake_case aliases accepted for flexibility).

| Parameter | Type | Required? | Format / Allowed Values | Description |
| :--- | :--- | :--- | :--- | :--- |
| `submissionId` | String | **Yes** | Alphanumeric (e.g. `"a0CAq00004acdq7MAA"`) | Unique client submission identifier. Preserved and echoed in output. |
| `productName` | String | **Yes** | String (e.g. `"ARIKAYCE KIT"` or `"amikacin"`) | Target medicine or product name. Case-insensitive matching. |
| `startDate` | String | No | Strict `DD-MM-YYYY` (e.g. `"01-01-2025"`) | Inclusive start date boundary for crawler safety changes. |
| `endDate` | String | No | Strict `DD-MM-YYYY` (e.g. `"01-01-2026"`) | Inclusive end date boundary for crawler safety changes. |
| `genericName` | String | No | String (e.g. `"amikacin"`) | Generic name search filter. Empty string `""` treated as omitted filter. |
| `activeIngredients`| String | No | String (e.g. `"amikacin sulfate"`) | Active ingredient(s) filter. Multi-ingredients supported via commas. |
| `callbackUrl` | String | No | URL string or `"skip"` | Optional Salesforce Apex REST webhook for asynchronous event dispatch. |

### Validation Rules:
1. **Date Format**: Must strictly follow `DD-MM-YYYY` (e.g. `01-01-2025`). Invalid formats (e.g. `2025-01-01` or `bad-date`) are rejected immediately with **HTTP 422**.
2. **Reversed Date Ranges**: If `startDate` is later than `endDate`, the API rejects the request with **HTTP 422** (`startDate cannot be later than endDate`).
3. **Empty String Handling**: Empty strings (`""`) for `startDate`, `endDate`, `genericName`, and `activeIngredients` are treated as omitted filters.
4. **Inclusive Boundaries**: Records exactly on `startDate` (at `00:00:00.000000`) and records exactly on `endDate` (at `23:59:59.999999`) are included. Records with missing dates are excluded when a date range is requested.
5. **No Implicit Date Filters**: If no date range is provided, the crawler defaults to returning the most recent authoritative safety supplement without fabricating historical dates.

---

## 4. Response Contract

The API returns one unified JSON response containing two separate top-level subsystem objects:

```json
{
  "submissionId": "a0CAq00004acdq7MAA",
  "productName": "ARIKAYCE KIT",
  "website_Data": {
    "title": "Website Crawler Data",
    "status": "success",
    "data": [
      {
        "website_Name": "FDA_details",
        "title": "Website Safety Data",
        "productName": "ARIKAYCE KIT",
        "genericName": "amikacin sulfate",
        "activeIngredients": "AMIKACIN SULFATE",
        "startDate": "01-01-2025",
        "endDate": "01-01-2026",
        "Data": "<!DOCTYPE html><html>...website safety changes HTML...</html>",
        "submissionId": "a0CAq00004acdq7MAA"
      }
    ]
  },
  "pdf_extractor_Data": {
    "title": "PDF Extractor Data",
    "status": "success",
    "data": {
      "status": "success",
      "product_name": "Amikacin",
      "target_section": "16",
      "target_subsection": null,
      "section_title": "Section 16: Risk & Signal Management",
      "source_document": "Amikacin_Monograph.pdf",
      "total_pages": 42,
      "pages": {
        "start": 28,
        "end": 31
      },
      "extraction_status": "success",
      "confidence_score": 0.98,
      "last_updated": "2026-02-15T10:30:00",
      "Data": "<!DOCTYPE html><html><body><p>Summary of Safety Concerns...</p></body></html>",
      "data": {
        "text": "Summary of Safety Concerns...",
        "tables": [],
        "subsections": ["16.1", "16.2"],
        "html": "<!DOCTYPE html><html><body><p>Summary of Safety Concerns...</p></body></html>",
        "html_snippet": "<p>Summary of Safety Concerns...</p>"
      }
    }
  }
}
```

### How the Client Consumes Results:
- **To inspect Website Crawler results**: Read `response.website_Data`. Check `status === "success"`. The array `data` contains matching website records with rendered HTML in `Data`.
- **To inspect PDF Extractor results**: Read `response.pdf_extractor_Data`. Check `status === "success"`. The preserved structured Section 16 data is in `data`, with paragraph HTML in `data.Data`.
- **Titles**:
  - `response.website_Data.title` is always `"Website Crawler Data"`.
  - `response.pdf_extractor_Data.title` is always `"PDF Extractor Data"`.

---

## 5. Request & Response Examples

### Example 1: Successful Query (Both Subsystems Return Data)

**Request (`POST /api/v1/products/signal-and-risk`)**:
```json
{
  "submissionId": "a0CAq00004acdq7MAA",
  "productName": "ARIKAYCE KIT",
  "startDate": "01-01-2025",
  "endDate": "01-01-2026",
  "genericName": "",
  "activeIngredients": ""
}
```

**Response (`200 OK`)**:
```json
{
  "submissionId": "a0CAq00004acdq7MAA",
  "productName": "ARIKAYCE KIT",
  "website_Data": {
    "title": "Website Crawler Data",
    "status": "success",
    "data": [
      {
        "website_Name": "FDA_details",
        "title": "Website Safety Data",
        "productName": "ARIKAYCE KIT",
        "genericName": "amikacin sulfate",
        "activeIngredients": "AMIKACIN SULFATE",
        "startDate": "01-01-2025",
        "endDate": "01-01-2026",
        "Data": "<!DOCTYPE html><html>...</html>",
        "submissionId": "a0CAq00004acdq7MAA"
      }
    ]
  },
  "pdf_extractor_Data": {
    "title": "PDF Extractor Data",
    "status": "success",
    "data": {
      "status": "success",
      "product_name": "Amikacin",
      "target_section": "16",
      "Data": "<!DOCTYPE html><html><body><p>...</p></body></html>",
      "data": { "text": "...", "tables": [] }
    }
  }
}
```

---

### Example 2: Partial Success (Crawler Success, Product Not Indexed in PDF)

When a drug is found in the FDA crawler database but does not have an uploaded monograph PDF in the PDF system:

**Response (`200 OK`)**:
```json
{
  "submissionId": "sub_crawler_only",
  "productName": "Lipitor",
  "website_Data": {
    "title": "Website Crawler Data",
    "status": "success",
    "data": [
      {
        "website_Name": "FDA_details",
        "title": "Website Safety Data",
        "productName": "Lipitor",
        "genericName": "atorvastatin calcium",
        "activeIngredients": "ATORVASTATIN CALCIUM",
        "startDate": "",
        "endDate": "",
        "Data": "<!DOCTYPE html><html>...</html>",
        "submissionId": "sub_crawler_only"
      }
    ]
  },
  "pdf_extractor_Data": {
    "title": "PDF Extractor Data",
    "status": "not_found",
    "data": null,
    "message": "No indexed PDF Section 16 data found for product 'Lipitor'."
  }
}
```

---

### Example 3: Partial Success (PDF Success, Website Crawler Unavailable)

When a product is indexed in the PDF extractor but the crawler service encounters an upstream timeout or connection error:

**Response (`200 OK`)**:
```json
{
  "submissionId": "sub_pdf_only",
  "productName": "Amikacin",
  "website_Data": {
    "title": "Website Crawler Data",
    "status": "error",
    "data": [],
    "message": "Website crawler service unavailable or timed out."
  },
  "pdf_extractor_Data": {
    "title": "PDF Extractor Data",
    "status": "success",
    "data": {
      "status": "success",
      "product_name": "Amikacin",
      "Data": "<!DOCTYPE html><html><body><p>...</p></body></html>"
    }
  }
}
```

---

### Example 4: Total Failure (Neither Subsystem Has Data)

When an unknown medicine is not indexed in the PDF extractor AND has no matching FDA safety labeling changes in the crawler:

**Response (`404 Not Found`)**:
```json
{
  "detail": "No data found for product 'unknown_medicine_xyz' in either website crawler or PDF extractor."
}
```

---

### Example 5: Validation Error (Invalid Date Format or Reversed Range)

**Request (`POST /api/v1/products/signal-and-risk`)**:
```json
{
  "submissionId": "sub_bad_range",
  "productName": "amikacin",
  "startDate": "01-01-2026",
  "endDate": "01-01-2025"
}
```

**Response (`422 Unprocessable Content`)**:
```json
{
  "detail": "startDate ('01-01-2026') cannot be later than endDate ('01-01-2025')."
}
```

---

## 6. Authentication & Security

- **API Key Header**: If `API_KEY` is set in the environment, clients must supply the `X-API-KEY` HTTP header:
  ```http
  X-API-KEY: YOUR_API_KEY
  ```
- **Unauthorized**: Requests missing or supplying an invalid `X-API-KEY` receive **HTTP 401 Unauthorized**.
- **Public Sandbox**: If `API_KEY` is empty or omitted from the environment, requests are allowed freely for local development.

---

## 7. Working cURL Examples

Replace `YOUR_HOST` (e.g. `127.0.0.1:8000` or `api.yourdomain.com`) and `YOUR_API_KEY` with your actual host and credentials.

### cURL POST Request (Automated Integration):
```bash
curl -X POST "http://YOUR_HOST/api/v1/products/signal-and-risk" \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: YOUR_API_KEY" \
  -d '{
    "submissionId": "a0CAq00004acdq7MAA",
    "productName": "ARIKAYCE KIT",
    "startDate": "01-01-2025",
    "endDate": "01-01-2026",
    "genericName": "",
    "activeIngredients": ""
  }'
```

### cURL GET Request (Browser / Ad-hoc Testing):
```bash
curl -X GET "http://YOUR_HOST/api/v1/products/signal-and-risk?productName=amikacin&startDate=01-01-2025&endDate=01-01-2026&submissionId=manual_test_101" \
  -H "X-API-KEY: YOUR_API_KEY"
```

---

## 8. Current Website Source & Historical Limitations

- **Current Active Source**: **US FDA SrLC** (*Safety-related Labeling Changes* database).
- **Date Filtering Basis**: Uses the authoritative FDA Supplement Action Date / Approval Date recorded in the official SrLC database.
- **Historical Coverage**:
  - The crawler queries FDA SrLC search indexes and paginated results.
  - If a requested date range specifies older years, the crawler queries the historical pages up to the search result limits exposed by the source.
  - If no records exist in the requested date range, HTTP 404 is returned for the crawler section (`No safety labeling changes found within requested date range`).
- **Future Extensibility**: The architecture uses modular source identifiers (`website_Name: "FDA_details"`, `"TGA_details"`, `"Health_Canada_details"`), allowing additional regulatory authorities to be plugged into the same unified contract.

---

## 9. Verification & Automated Test Commands

Run the test suites in both subsystems from the repository root:

```bash
# 1. Run backend (crawler) test suite (72 tests)
backend/.venv/bin/pytest backend/tests

# 2. Run PDF extractor test suite (65 tests)
pdf_extractor/.venv/bin/pytest pdf_extractor/tests
```
All 137 tests run isolated in-memory with deterministic fixtures, verifying contract compliance, date filtering, and independent fault tolerance.
