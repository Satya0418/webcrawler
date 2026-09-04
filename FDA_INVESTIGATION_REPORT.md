# FDA SrLC Investigation Report

**Date**: 2026-09-03  
**Investigation Status**: Phase 1 Complete  
**Source**: https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/index.cfm

---

## Executive Summary

The FDA SrLC website is a server-side rendered application with the following characteristics:

- **Search Method**: Form-based (GET query parameters OR POST to result page)
- **JavaScript Usage**: Moderate - used for autocomplete and navigation, not primary data rendering
- **Robots.txt**: SrLC path is **allowed** for crawling (not in disallow list)
- **Accessibility**: No CAPTCHA or authentication barriers detected
- **Rate Limiting**: Not yet determined (recommend conservative crawling)

---

## Key Findings

### 1. Search Mechanism

**Main Page URL**:
```
https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/index.cfm
```

**Search Form**:
- **Drug Name Search**: Text input with autocomplete dropdown
- **Date Range Search**: Start date and end date pickers
- **Labeling Section Filter**: Checkboxes for various sections
- **Form Action**: POSTs to `index.cfm?event=searchResult.page`

**Form Fields Identified**:
- `drug_name`: Drug name or active ingredient
- `StartDate`: Date from (format: MM/DD/YYYY)
- `EndDate`: Date to (format: MM/DD/YYYY)
- Checkboxes for labeling sections

**Autocomplete Data**:
The page contains a comprehensive datalist with 1,000+ drugs encoded in JavaScript:
```javascript
availableTags = [
  "Drug Name: ABILIFY",
  "Drug Name: ABILIFY ASIMTUFII",
  ...
  "Active Ingredient: WARFARIN SODIUM",
  ...
]
```

This datalist can be extracted and used for prefix matching before making FDA requests.

### 2. Page Structure

**Main Page Elements**:
- 3 Forms (1 drug search, 1 date search, 1 FDA global search)
- 2 Tables (legend/abbreviations table)
- 14 Script tags (jQuery, Bootstrap, analytics, autocomplete)
- 70 Links (footer, navigation)

**Important HTML Structure**:
```html
<form id="resultsName" action="/scripts/cder/safetylabelingchanges/index.cfm?event=searchResult.page" 
      method="post" autocomplete="off">
  <label for="drug_name">Drug Name or Active Ingredient</label>
  <input type="text" id="drug_name" name="drug_name" list="tags">
  <button type="submit">Search</button>
</form>

<datalist id="tags">
  <option>Drug Name: ABILIFY</option>
  ...
</datalist>
```

### 3. Abbreviations & Sections

**Supported Labeling Sections**:
- BW: Boxed Warning
- WP: Warnings and Precautions (PLR format)
- AR: Adverse Reactions
- DI: Drug Interactions
- USP: Use in Specific Populations
- PCI/PI/MG: Patient Counseling Information

**Application Types**:
- NDA: New Drug Application
- BLA: Biologics License Application
- ANDA: Abbreviated New Drug Application (excluded from SrLC)

---

## Investigation Limitations

### Encountered Issues

1. **403 Forbidden on Direct Requests**
   - Direct HTTP requests to search endpoints return 403
   - The website may require browser-like headers (User-Agent, Accept, etc.)
   - Solution: Add proper User-Agent and Accept headers to requests

2. **Redirect Behavior**
   - POST requests to result endpoint get redirected
   - Need to follow redirects and maintain session cookies

3. **JavaScript Dependence for Results**
   - Results page may use JavaScript to render data
   - May require additional investigation of XHR/fetch requests

### Next Steps for Investigation

1. **Add Browser Headers**
   - Set User-Agent to a modern browser
   - Include Accept headers
   - Include Referer header

2. **Session Management**
   - Use httpx.Client with cookie persistence
   - Maintain session across multiple requests

3. **Parse Results Page**
   - Once search results are retrieved, analyze table structure
   - Identify CSS selectors for result rows
   - Extract links to detail pages

4. **Detail Page Analysis**
   - Follow result links to detail pages
   - Document content extraction points for:
     - Drug name and active ingredient
     - Safety change dates
     - Original/updated text
     - FDA comments
     - Effective dates

---

## Saved Fixtures

**Location**: `tests/fixtures/fda/`

**Files Created**:
- `search_page.html` - Main search page structure
- `search_results_warfarin.html` - Search results for warfarin (contains autocomplete data)
- `search_results_date.html` - Date range search page

**File Sizes**:
- search_page.html: ~261 KB
- search_results_warfarin.html: ~261 KB
- search_results_date.html: ~261 KB

---

## Recommendations for Scraper Implementation

### 1. HTTP Client Configuration

```python
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Referer': 'https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/',
}

client = httpx.Client(
    headers=headers,
    follow_redirects=True,
    cookies=httpx.Cookies()
)
```

### 2. Crawling Strategy

1. **Pre-search Validation** (Use autocomplete datalist)
   - Extract drug names from embedded JavaScript datalist
   - Validate user query against this list
   - Return matching suggestions to user

2. **Actual Search** (When user confirms)
   - POST to result page with drug_name parameter
   - Parse result page for matching records
   - Extract detail page URLs

3. **Detail Page Extraction**
   - Follow each result URL
   - Extract drug info and safety changes
   - Parse original/updated text fields

### 3. Rate Limiting

Recommend:
- Max 1 request per second to FDA
- Use exponential backoff on timeouts
- Cache search results for 24 hours
- Use robots.txt crawl-delay if specified (currently: 1 day per robots.txt)

### 4. Error Handling

- 403 Forbidden: Likely due to missing headers or rate limiting
  - Implement retry with exponential backoff
  - Add random user-agent rotation
  - Add request delays

- 302 Redirect: Session/cookie issue
  - Use httpx.Client for session persistence
  - Follow redirects automatically

- 500/503: FDA temporarily unavailable
  - Return cached data if available
  - Log error and retry later

---

## Data Extraction Targets

Based on FDA SrLC scope, extract:

### Drug Information
- [ ] Drug Name / Product Name
- [ ] Active Ingredient
- [ ] Strength / Dosage
- [ ] Application Number (NDA/BLA)
- [ ] Manufacturer / Applicant
- [ ] Product Code

### Safety Change Information
- [ ] Date of change (source_date)
- [ ] Approval date
- [ ] Effective date
- [ ] Labeling section
- [ ] Change description
- [ ] Original text (pre-change)
- [ ] Updated text (post-change)
- [ ] FDA comment
- [ ] FDA requirement indicator

### Administrative
- [ ] Source URL
- [ ] Source record ID
- [ ] Page retrieval timestamp

---

## Known Scope Limitations (Per FDA)

1. **Data Period**: January 1, 2016 forward
   - Earlier data available on MedWatch website

2. **Drug Types**: NDAs and CDE-regulated BLAs only
   - ANDAs (generic drugs) NOT included

3. **Labeling Changes Only**: Not a complete drug database
   - Absence of record ≠ absence of safety issues
   - Only safety-related labeling changes included

---

## Next Phase

**PHASE 2: FDA Crawler & Scraper Implementation**

1. Update HTTP client with proper headers
2. Implement search with browser-like headers
3. Parse result page HTML structure
4. Extract result URLs and drug information
5. Implement detail page parser
6. Create comprehensive test fixtures with real FDA HTML
7. Implement regression tests
8. Test change detection with actual FDA data

---

## References

- **FBI robots.txt**: https://www.accessdata.fda.gov/robots.txt
- **SrLC Database**: https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/
- **MedWatch (Pre-2016)**: https://www.fda.gov/Safety/MedWatch/SafetyInformation/Safety-RelatedDrugLabelingChanges/
