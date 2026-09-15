# Phase 2 Implementation Plan - FDA Crawler & Scraper

**Objective**: Build working FDA web crawler and HTML parser to extract drug safety data  
**Estimated Effort**: 4-6 hours (backend-focused, no frontend)  
**Success Criteria**: Can search FDA, parse results, extract detail pages, store in database

---

## Phase 2 Breakdown

### Step 1: Enhance FDA Crawler with Browser Headers (30 min)

**File**: `backend/app/crawler/fda_crawler.py`

**Changes**:
```python
class FDACrawler:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': 'https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/',
            'Connection': 'keep-alive',
        }
        self.client_kwargs = {
            'timeout': 30,
            'follow_redirects': True,
            'headers': self.headers,
        }

    async def search_drug(self, drug_name: str) -> Optional[str]:
        """Search FDA using POST form"""
        # POST to the actual result page endpoint
        # Handle redirects and session cookies
        
    async def get_page(self, url: str) -> Optional[str]:
        """Fetch a page with proper headers"""
        # Use configured headers
        # Track visited URLs
        # Implement retry with backoff
```

**Deliverable**: Crawler that successfully fetches FDA pages without 403 errors

---

### Step 2: Implement HTML Parsers (2 hours)

**File**: `backend/app/scrapers/fda_srlc_scraper.py`

**Implement Functions**:

#### 2.1 Parse Search Results Page
```python
def parse_search_results(self, html_content: str) -> List[Dict[str, Any]]:
    """
    Extract drug records from search results
    
    Should extract:
    - Drug name
    - Active ingredient
    - Links to detail pages
    - Application number if visible
    """
    # TODO: Parse results table/list
    # TODO: Extract result URLs
    # TODO: Return list of records
```

**Expected HTML Structure**:
- Results in a table or list
- Each row has: drug name, active ingredient, link to details
- May have pagination

#### 2.2 Parse Detail Page
```python
def parse_detail_page(self, html_content: str) -> Dict[str, Any]:
    """
    Extract safety information from detail page
    
    Should extract:
    - Complete drug information
    - Safety changes for each labeling section
    - Original and updated text
    - FDA comments
    - Dates
    """
    # TODO: Parse detail page structure
    # TODO: Extract all safety information
    # TODO: Return normalized record
```

**Expected Extraction Targets**:
- Drug name and active ingredient
- Application number (NDA/BLA)
- Labeling section (Boxed Warning, Warnings and Precautions, etc.)
- Original safety text
- Updated safety text
- FDA comments
- Safety change date
- Approval/effective dates
- Detail page URL

**Deliverable**: Working HTML parsers with test fixtures

---

### Step 3: Create Test Fixtures with Real Data (1 hour)

**Location**: `backend/tests/fixtures/fda/`

**Capture**:
1. Actual search results page (after fixing browser headers)
2. Actual detail page for at least one safety record
3. Multiple examples of different labeling sections

**Tests**:
```python
def test_parse_search_results():
    """Test parsing real search results fixture"""
    with open('fixtures/fda/search_results_warfarin.html') as f:
        html = f.read()
    
    results = scraper.parse_search_results(html)
    
    assert len(results) > 0
    assert results[0]['drug_name'] is not None
    assert results[0]['detail_url'] is not None

def test_parse_detail_page():
    """Test parsing real detail page fixture"""
    with open('fixtures/fda/detail_warfarin.html') as f:
        html = f.read()
    
    record = scraper.parse_detail_page(html)
    
    assert record['drug_name'] == 'Warfarin'
    assert record['original_text'] is not None
    assert record['updated_text'] is not None
```

**Deliverable**: Real FDA HTML fixtures + regression tests

---

### Step 4: Implement Database Logic (1.5 hours)

**New File**: `backend/app/services/database_service.py`

**Functions**:
```python
class DatabaseService:
    async def insert_or_update_drug(
        self, 
        session: AsyncSession,
        drug_data: Dict[str, Any]
    ) -> Drug:
        """
        Insert drug or return existing
        
        1. Check if drug exists (by normalized_name)
        2. If exists: return it
        3. If not: create and return
        """
        
    async def save_safety_change(
        self,
        session: AsyncSession,
        drug_id: int,
        change_data: Dict[str, Any]
    ) -> SafetyLabelingChange:
        """
        Save safety change with version tracking
        
        1. Calculate content hash
        2. Check if record exists (by drug_id + section + date)
        3. If exists with same hash: return unchanged
        4. If exists with different hash: create new version
        5. If new: create record
        """
        
    async def create_version(
        self,
        session: AsyncSession,
        safety_change_id: int,
        original_hash: str,
        new_hash: str
    ) -> SafetyChangeVersion:
        """
        Create version history record
        """
```

**Deliverable**: Database insert/update logic with change detection

---

### Step 5: Implement Search Endpoint (1 hour)

**File**: `backend/app/api/drugs.py`

**Implement**:
```python
@router.get("/search", response_model=SearchResultResponse)
async def search_drugs(
    q: str = Query(..., min_length=1, max_length=255),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Search for drugs by name or active ingredient
    
    Flow:
    1. Validate query
    2. Check local database
    3. Return cached results if fresh
    4. If no results, query FDA
    5. Parse FDA results
    6. Save to database
    7. Return structured response
    """
    
    # 1. Normalize query
    normalized_q = normalize_drug_name(q)
    
    # 2. Search local database
    existing = await db.execute(
        select(Drug).where(
            Drug.normalized_name.like(f"%{normalized_q}%")
        )
    )
    local_results = existing.scalars().all()
    
    # 3. Check cache TTL
    if local_results and not_stale:
        return {
            "query": q,
            "source": "FDA_SRLC",
            "results": [DrugResponse.from_orm(r) for r in local_results]
        }
    
    # 4. Query FDA
    fda_results = await crawler.search_drug(q)
    
    # 5. Parse results
    parsed = scraper.parse_search_results(fda_results)
    
    # 6. Normalize and validate
    normalized_results = [
        NormalizationService.build_normalized_record(r) 
        for r in parsed
    ]
    
    for nr in normalized_results:
        ValidationService.validate_record(nr)
    
    # 7. Save to database
    saved_drugs = []
    for nr in normalized_results:
        drug = await DatabaseService.insert_or_update_drug(db, nr)
        saved_drugs.append(drug)
    
    await db.commit()
    
    # 8. Return results
    return {
        "query": q,
        "source": "FDA_SRLC",
        "results": [DrugResponse.from_orm(d) for d in saved_drugs]
    }
```

**Deliverable**: Working search endpoint

---

### Step 6: Implement Detail Endpoint (30 min)

**File**: `backend/app/api/drugs.py`

```python
@router.get("/{drug_id}", response_model=DrugDetailResponse)
async def get_drug_detail(
    drug_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """Get drug with all safety changes"""
    
    drug = await db.get(Drug, drug_id)
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found")
    
    # Load related safety changes
    result = await db.execute(
        select(Drug).options(selectinload(Drug.safety_changes))
        .where(Drug.id == drug_id)
    )
    drug = result.scalar_one()
    
    return DrugDetailResponse.from_orm(drug)
```

**Deliverable**: Detail endpoint working

---

### Step 7: Add Logging & Error Handling (30 min)

**File**: `backend/app/services/logging_service.py` (new)

```python
import structlog

logger = structlog.get_logger()

async def log_crawl_event(event_type: str, details: Dict):
    """Log crawler events"""
    logger.info(
        "crawl_event",
        event_type=event_type,
        **details
    )

async def log_parse_error(error: Exception, html_snippet: str):
    """Log parser errors"""
    logger.error(
        "parse_error",
        error=str(error),
        html_length=len(html_snippet),
        first_chars=html_snippet[:100]
    )
```

**Add to Crawler**:
- Log every search
- Log every page fetch
- Log errors with details
- Track timing

**Deliverable**: Structured logging throughout

---

### Step 8: Integration Tests (1 hour)

**File**: `backend/tests/test_integration.py` (new)

```python
@pytest.mark.asyncio
async def test_full_search_workflow():
    """Test complete search to database workflow"""
    # 1. Search for warfarin
    # 2. Verify FDA is queried
    # 3. Verify results are parsed
    # 4. Verify data is normalized
    # 5. Verify data is validated
    # 6. Verify data is saved to DB
    # 7. Verify subsequent search uses cache
    # 8. Verify no duplicate records

@pytest.mark.asyncio
async def test_change_detection():
    """Test version creation on change"""
    # 1. Save initial record
    # 2. Modify record (different text)
    # 3. Save again
    # 4. Verify version created
    # 5. Verify old version preserved
    # 6. Verify hash changed

@pytest.mark.asyncio
async def test_error_handling():
    """Test FDA unavailable scenario"""
    # 1. Mock FDA returning 503
    # 2. Verify graceful fallback
    # 3. Verify cached data returned
    # 4. Verify error logged
```

**Deliverable**: Full integration tests passing

---

## Implementation Checklist

### Day 1: Crawler & Scraper (3 hours)
- [ ] Add browser headers to crawler
- [ ] Implement `parse_search_results()`
- [ ] Implement `parse_detail_page()`
- [ ] Capture real FDA HTML fixtures
- [ ] Write parser tests
- [ ] Test parser with fixtures

### Day 2: Database & API (3 hours)
- [ ] Implement `DatabaseService`
- [ ] Implement search endpoint
- [ ] Implement detail endpoint
- [ ] Implement logging
- [ ] Write integration tests
- [ ] Test end-to-end workflow

---

## Testing Strategy

### Unit Tests
```bash
pytest backend/tests/test_fda_scraper.py -v
pytest backend/tests/test_change_detection.py -v
```

### Integration Tests
```bash
pytest backend/tests/test_integration.py -v
```

### End-to-End Testing
```bash
# Start server
uvicorn app.main:app --reload

# Test search endpoint
curl "http://localhost:8000/api/drugs/search?q=warfarin"

# Check database
psql medicine_safety -c "SELECT * FROM drugs;"
```

---

## Success Criteria

✅ **Crawler**
- Fetches FDA pages without 403 errors
- Tracks visited URLs (no duplicates)
- Implements exponential backoff on timeout
- Logs all requests

✅ **Scraper**
- Parses search results accurately
- Parses detail pages completely
- Handles missing fields gracefully
- Returns structured data

✅ **Database**
- Inserts new drugs
- Updates existing drugs
- Creates versions on change
- Never loses historical data

✅ **API**
- `/api/drugs/search?q=warfarin` returns results
- Results include all required fields
- Caching reduces FDA queries
- Pagination works

✅ **Testing**
- 50+ tests passing
- >80% code coverage
- No corrupted data
- Regression tests protect against HTML changes

---

## Troubleshooting

### If Crawler Returns 403
- Add/update User-Agent header
- Add Referer header
- Add Accept header
- Increase timeout
- Reduce request rate
- Use session/cookies

### If Parser Returns None
- Print raw HTML to inspect
- Check if HTML structure changed
- Look for new selectors/classes
- Fail loudly (raise exception)
- Never silently return bad data

### If Database Insert Fails
- Check for duplicate drug names
- Verify dates are valid
- Ensure text isn't corrupted
- Log full error details
- Roll back transaction

---

## Timeline

| Phase | Task | Duration | Status |
|-------|------|----------|--------|
| Phase 1 | Investigation & Backend Setup | 4 hrs | ✅ DONE |
| **Phase 2** | **Crawler & Scraper Implementation** | **6 hrs** | **TODO** |
| Phase 3 | Database & API Implementation | 3 hrs | PENDING |
| Phase 4 | Caching & Background Jobs | 3 hrs | PENDING |
| Phase 5 | Testing & Documentation | 2 hrs | PENDING |
| Phase 6 | Ubuntu Deployment | 4 hrs | PENDING |

**Next Action**: Start Phase 2 implementation

---

## Files to Modify/Create

**Modify**:
- `app/crawler/fda_crawler.py` - Add headers and real search logic
- `app/scrapers/fda_srlc_scraper.py` - Implement parsers
- `app/api/drugs.py` - Implement endpoints

**Create**:
- `app/services/database_service.py` - Database operations
- `app/services/logging_service.py` - Structured logging
- `tests/test_integration.py` - Integration tests
- `tests/fixtures/fda/detail_warfarin.html` - Real FDA detail page

**No Changes Needed**:
- `app/models/` - Models are complete
- `app/schemas/` - Schemas are complete
- `app/services/normalization.py` - Service is complete
- `app/services/validation.py` - Service is complete
- `app/services/change_detection.py` - Service is complete

---

## Questions to Answer During Implementation

1. What does the actual FDA search results HTML look like?
2. What CSS selectors identify result rows?
3. What does the detail page structure look like?
4. How many safety changes per drug on average?
5. Are there pagination issues to handle?
6. What rate limit should we use (1/sec, 1/min)?
7. How often should background crawler run?

---

## Ready to Start?

✅ Backend infrastructure complete  
✅ Investigation done  
✅ Architecture ready  
✅ Tests framework ready  
✅ All dependencies installed  

**Next**: Implement Phase 2 (Crawler & Scraper)
