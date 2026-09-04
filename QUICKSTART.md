# Quick Start Guide

**Status**: Phase 1 Complete ✅ - Backend Ready  
**Next**: Phase 2 - Implement Crawler & Scraper

---

## What You Have

### Project Structure
```
webcrwler/
├── backend/                        Backend API (FastAPI + PostgreSQL)
│   ├── app/                       Main application code
│   ├── tests/                     38 passing tests
│   ├── investigate_fda.py         FDA investigation script
│   ├── requirements.txt           All dependencies
│   ├── pytest.ini                 Test config
│   └── .venv/                     Virtual environment (ready to use)
│
├── FDA_INVESTIGATION_REPORT.md    FDA website analysis
├── PHASE1_COMPLETION.md           What we built
├── PHASE2_PLAN.md                 What's next
├── README.md                      Full documentation
└── .env.example                   Environment template

```

### Core Components Built

**Database** (SQLAlchemy ORM):
- ✅ Drug table
- ✅ SafetyLabelingChange table
- ✅ SafetyChangeVersion table (version history)
- ✅ CrawlRun table (crawler logging)

**Services** (Ready to use):
- ✅ `NormalizationService` - Standardize drug names, sections, text
- ✅ `ValidationService` - Check data integrity, detect corruption
- ✅ `ChangeDetectionService` - SHA-256 hashing, version detection

**API Framework** (FastAPI, Ready to implement):
- ✅ `/api/health` - Health check
- ✅ `/api/drugs/search?q=warfarin` - Search (stub)
- ✅ `/api/drugs/{id}` - Get drug detail (stub)
- ✅ `/api/drugs/{id}/safety-changes` - Get safety records (stub)
- ✅ `/api/safety-changes/{id}` - Get record detail (stub)
- ✅ `/api/admin/crawl/fda` - Trigger crawl (stub)

**Crawler & Scraper** (Stubs, ready for implementation):
- ✅ HTTP client structure (httpx, async)
- ✅ HTML parser framework (BeautifulSoup + lxml)
- ✅ URL tracking (no duplicates)
- ✅ Error handling stubs

---

## Quick Start (5 minutes)

### 1. Set Up Environment
```bash
cd /Users/satya/Desktop/webcrwler/backend

# Activate virtual environment
source .venv/bin/activate

# Verify setup
python3 -c "import fastapi; import sqlalchemy; print('✓ All deps ready')"
```

### 2. Run Tests
```bash
cd backend
pytest -v --cov=app
# Should see: 38 tests pass
```

### 3. Start Development Server
```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. Test Health Endpoint
```bash
# In another terminal
curl http://127.0.0.1:8000/api/health
# Returns: {"status":"healthy","service":"medicine-safety-backend","version":"1.0.0"}
```

---

## What's Next (Phase 2)

### To Implement:

1. **Update Crawler** (30 min)
   - Add browser headers (User-Agent, Accept, Referer)
   - Implement POST search to FDA
   - Handle redirects and sessions

2. **Implement Scraper** (2 hours)
   - Parse search results table
   - Parse detail page HTML
   - Extract drug info and safety changes

3. **Database Logic** (1.5 hours)
   - Insert/update drug records
   - Create version history on change
   - Track crawl runs

4. **API Endpoints** (1 hour)
   - Implement `/api/drugs/search`
   - Implement `/api/drugs/{id}`
   - Integrate crawler/scraper

5. **Tests & Logging** (1.5 hours)
   - Add integration tests
   - Implement structured logging
   - Test full workflow

**Total Phase 2 Time**: ~6 hours

---

## Key Documentation

📄 **Read These First**:
1. `PHASE1_COMPLETION.md` - What we built
2. `FDA_INVESTIGATION_REPORT.md` - FDA website findings
3. `PHASE2_PLAN.md` - Detailed implementation plan

📄 **Reference**:
- `README.md` - Complete project documentation
- `.env.example` - Environment variables

🔧 **Code Files**:
- `backend/app/models/drug.py` - Database models
- `backend/app/schemas/drug.py` - API schemas
- `backend/app/services/` - Services (normalization, validation, change detection)
- `backend/app/crawler/fda_crawler.py` - Crawler (stub, ready for impl)
- `backend/app/scrapers/fda_srlc_scraper.py` - Scraper (stub, ready for impl)

---

## Important Design Decisions

✅ **No Docker** - Native Ubuntu deployment (as specified)  
✅ **Strong Backend First** - Skip frontend for now  
✅ **Version History** - Never overwrites records  
✅ **SHA-256 Hashing** - Detect changes accurately  
✅ **Fail Safe Parsing** - Detect corruption, never insert bad data  
✅ **Original FDA Text** - Always preserve source material  

---

## Development Workflow

### 1. Make Changes
```bash
cd backend
# Edit code in backend/app/

# Make sure you have venv activated
source .venv/bin/activate
```

### 2. Run Tests
```bash
pytest -v
# Or specific test:
pytest tests/test_fda_scraper.py -v
```

### 3. Start Server
```bash
uvicorn app.main:app --reload
# Server hot-reloads on file changes
```

### 4. Test Endpoint
```bash
curl http://127.0.0.1:8000/api/health
# Or use VS Code REST client / Postman
```

---

## Current Test Coverage

```
tests/test_fda_scraper.py          9 tests (scraper methods)
tests/test_change_detection.py    15 tests (normalization + hashing)
tests/test_validation.py          14 tests (data validation)
                                  ──────────
TOTAL:                            38 tests ✅ ALL PASSING
```

### View Test Results
```bash
cd backend
pytest -v --cov=app --cov-report=html
# Opens htmlcov/index.html for coverage visualization
```

---

## Database Setup (When Ready)

```bash
# Create PostgreSQL database
createdb medicine_safety

# Set environment variables in .env
DATABASE_URL=postgresql://user:password@localhost:5432/medicine_safety

# Initialize database tables
python3 -c "
import asyncio
from app.database import init_db
asyncio.run(init_db())
print('✓ Database ready')
"
```

---

## Useful Commands

### Check Project Size
```bash
wc -l backend/app/**/*.py
find backend -name "*.py" | xargs wc -l
```

### Run Specific Tests
```bash
pytest tests/test_change_detection.py::TestChangeDetectionService::test_generate_content_hash -v
```

### View Installed Packages
```bash
pip list
pip show fastapi
```

### Check Virtual Environment
```bash
which python3
python3 --version
pip --version
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'fastapi'"
```bash
# Activate virtual environment
source backend/.venv/bin/activate

# Or install dependencies
pip install -r backend/requirements.txt
```

### "Server already running on port 8000"
```bash
# Kill existing process
lsof -i :8000
kill -9 <PID>

# Or use different port
uvicorn app.main:app --port 8001
```

### "pytest: command not found"
```bash
# Activate virtual environment
source backend/.venv/bin/activate

# Or install pytest
pip install pytest
```

---

## Architecture Overview

```
User Search Request
       ↓
  FastAPI Endpoint
       ↓
Check Database/Cache ← Redis
       ↓
  If Cache Miss:
       ↓
  FDA Crawler → FDA Website
       ↓
  FDA Scraper ← Parse HTML
       ↓
  Normalize Data ← NormalizationService
       ↓
  Validate Data ← ValidationService
       ↓
  Check Hash ← ChangeDetectionService
       ↓
  Save to DB ← PostgreSQL
       ↓
  Return Response
       ↓
   User Gets Data
```

---

## Next Actions

### Immediate (Right Now)
- [ ] Read `PHASE1_COMPLETION.md`
- [ ] Read `PHASE2_PLAN.md`
- [ ] Verify tests pass: `pytest backend/tests -v`
- [ ] Verify server starts: `uvicorn app.main:app --reload`

### Short Term (Next Session)
- [ ] Implement crawler with browser headers
- [ ] Implement HTML parsers
- [ ] Capture real FDA HTML fixtures
- [ ] Write integration tests

### Medium Term
- [ ] Implement database insert/update logic
- [ ] Implement API endpoints
- [ ] Add Redis caching
- [ ] Set up Celery background jobs

### Long Term
- [ ] Ubuntu deployment configuration
- [ ] Nginx setup
- [ ] systemd services
- [ ] HTTPS/SSL configuration
- [ ] Frontend (React/Next.js) - after backend is stable

---

## Key Files to Edit (Phase 2)

1. **`backend/app/crawler/fda_crawler.py`**
   - Add browser headers
   - Implement POST search
   - Handle redirects

2. **`backend/app/scrapers/fda_srlc_scraper.py`**
   - Implement `parse_search_results()`
   - Implement `parse_detail_page()`

3. **`backend/app/api/drugs.py`**
   - Implement `/api/drugs/search` endpoint

4. **`backend/app/services/database_service.py`** (NEW)
   - Create database insert/update logic

5. **`backend/tests/test_integration.py`** (NEW)
   - End-to-end tests

---

## Success Metrics

### After Phase 1 ✅
- [x] Backend architecture complete
- [x] Database models designed
- [x] Services implemented
- [x] 38 tests passing
- [x] FDA website investigated
- [x] Documentation complete

### After Phase 2 (Target)
- [ ] Crawler fetches FDA pages successfully
- [ ] Parser extracts data accurately
- [ ] Database saves records correctly
- [ ] Search endpoint works end-to-end
- [ ] 50+ tests passing
- [ ] Version history tested
- [ ] Change detection tested

### After Phase 3
- [ ] All API endpoints working
- [ ] Redis caching functional
- [ ] Celery jobs scheduled
- [ ] Admin dashboard working

### After Phase 4
- [ ] Running on Ubuntu native
- [ ] Nginx configured
- [ ] HTTPS enabled
- [ ] systemd services active
- [ ] Backup scripts working

---

## Recommended IDE Setup

### VS Code Extensions
- Python
- Pylance
- SQLAlchemy
- FastAPI
- Postman/Thunder Client (for API testing)

### VS Code Settings
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/backend/.venv/bin/python",
  "python.linting.enabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true
}
```

---

## Questions?

Check these files in order:
1. `README.md` - General overview
2. `FDA_INVESTIGATION_REPORT.md` - FDA details
3. `PHASE2_PLAN.md` - Next steps
4. Code comments in `backend/app/`

---

**Status**: Ready to proceed with Phase 2 ✅

Let's build the FDA crawler and scraper next!
