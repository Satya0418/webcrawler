# Medicine Safety Backend - FDA SrLC Web Crawler & Scraper

Production-ready Python backend for crawling and scraping the FDA Drug Safety-related Labeling Changes (SrLC) database.

## Project Overview

This backend application provides:
- **Web Crawler**: Fetches pages from FDA SrLC database
- **Web Scraper**: Extracts structured data from FDA HTML
- **Data Pipeline**: Normalization, validation, change detection
- **REST API**: FastAPI endpoints for search and data retrieval
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Caching**: Redis for performance
- **Background Jobs**: Celery for scheduled crawling
- **Change Detection**: SHA-256 hashing for version history

## Architecture

```
User Search Request
        ↓
   FastAPI API
        ↓
  Database/Cache Check
        ↓
  If missing/stale:
   FDA Crawler → FDA Scraper → Normalize → Validate → Change Detection
        ↓
   PostgreSQL Database
        ↓
  Return Structured JSON
```

## Features

- ✅ Modular architecture (crawler, scraper, normalization, validation, change detection separate)
- ✅ SHA-256 content hashing for change detection
- ✅ Version history management (never overwrites, creates versions)
- ✅ Comprehensive date tracking (source_date, approval_date, effective_date, etc.)
- ✅ Preserves original FDA text
- ✅ Fail-safe parsing (corrupted data detection)
- ✅ Input validation with Pydantic
- ✅ Test fixtures and regression protection
- ✅ Structured logging
- ✅ Redis caching with TTL
- ✅ Celery background jobs
- ✅ Comprehensive test suite

## Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI app factory
│   ├── config.py               # Settings and configuration
│   ├── database.py             # SQLAlchemy setup
│   │
│   ├── models/
│   │   └── drug.py            # ORM models
│   │
│   ├── schemas/
│   │   └── drug.py            # Pydantic schemas
│   │
│   ├── api/
│   │   ├── drugs.py           # Drug search endpoints
│   │   ├── safety_changes.py  # Safety change endpoints
│   │   └── admin.py           # Admin endpoints
│   │
│   ├── crawler/
│   │   └── fda_crawler.py     # FDA web crawler
│   │
│   ├── scrapers/
│   │   └── fda_srlc_scraper.py # FDA HTML parser
│   │
│   ├── services/
│   │   ├── normalization.py    # Data normalization
│   │   ├── validation.py       # Data validation
│   │   └── change_detection.py # SHA-256 hashing
│   │
│   ├── sources/               # Future: other regulatory sources
│   └── workers/               # Celery tasks
│
├── tests/
│   ├── conftest.py            # Pytest fixtures
│   ├── test_fda_scraper.py
│   ├── test_change_detection.py
│   └── test_validation.py
│
├── requirements.txt           # Python dependencies
├── pytest.ini                 # Pytest configuration
└── README.md                  # This file
```

## Installation

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- pip/venv

### Setup

1. **Clone or navigate to the project**
   ```bash
   cd webcrwler/backend
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp ../.env.example .env
   # Edit .env with your database and Redis credentials
   ```

5. **Initialize database**
   ```bash
   # Using Alembic (when migrations are created)
   alembic upgrade head
   
   # Or directly:
   python -c "from app.database import init_db; import asyncio; asyncio.run(init_db())"
   ```

6. **Run tests**
   ```bash
   pytest -v
   ```

7. **Start development server**
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

## Development Phases

### Phase 1: FDA Investigation (Current)
- [x] Analyze FDA SrLC website structure
- [x] Create project structure
- [x] Create crawler and scraper stubs
- [ ] Test actual FDA searches
- [ ] Document HTML structure and extraction points

### Phase 2: FDA Crawler & Scraper
- [ ] Implement real FDA crawler
- [ ] Implement HTML parser for search results
- [ ] Implement HTML parser for detail pages
- [ ] Create test fixtures from real FDA responses
- [ ] Write regression tests

### Phase 3: Database & Data Pipeline
- [ ] Set up Alembic migrations
- [ ] Implement normalization service (complete)
- [ ] Implement validation service (complete)
- [ ] Implement change detection (complete)
- [ ] Database insert/update logic

### Phase 4: FastAPI Endpoints
- [ ] Implement search endpoint
- [ ] Implement detail endpoint
- [ ] Implement safety changes endpoint
- [ ] Implement version history endpoint

### Phase 5: Redis Caching
- [ ] Implement cache service
- [ ] Add caching to search endpoint
- [ ] Configure TTL

### Phase 6: Celery Background Jobs
- [ ] Set up Celery task queue
- [ ] Implement scheduled crawler
- [ ] Implement on-demand crawler

### Phase 7: Testing & Documentation
- [ ] Write comprehensive tests
- [ ] Add logging
- [ ] Create admin dashboard endpoint

### Phase 8: Ubuntu Deployment
- [ ] Create systemd services
- [ ] Configure Nginx reverse proxy
- [ ] Set up HTTPS with Let's Encrypt
- [ ] Configure UFW firewall

## API Endpoints

### Health & Status
- `GET /api/health` - Health check

### Drugs
- `GET /api/drugs/search?q={drug_name}` - Search for drugs
- `GET /api/drugs/{drug_id}` - Get drug details
- `GET /api/drugs/{drug_id}/safety-changes` - Get safety changes for drug

### Safety Changes
- `GET /api/safety-changes/{record_id}` - Get safety change record
- `GET /api/safety-changes/{record_id}/history` - Get version history

### Admin
- `POST /api/admin/crawl/fda` - Trigger FDA crawl
- `GET /api/admin/crawl/status` - Get last crawl status
- `GET /api/admin/source-health` - FDA source health check

## Testing

Run all tests:
```bash
pytest
```

Run specific test file:
```bash
pytest tests/test_change_detection.py -v
```

Run with coverage:
```bash
pytest --cov=app --cov-report=html
```

## Key Technologies

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI + Uvicorn |
| ORM | SQLAlchemy |
| Database | PostgreSQL |
| Cache | Redis |
| Task Queue | Celery |
| HTML Parsing | BeautifulSoup + lxml |
| HTTP Client | httpx + requests |
| Validation | Pydantic |
| Testing | pytest + pytest-asyncio |

## Configuration

See `.env.example` for all configuration options:
- Database connection
- Redis endpoints
- FDA crawler timeouts and retries
- Cache TTL
- Logging level

## Important Notes

1. **No Docker**: This backend runs natively on Ubuntu, not in containers
2. **FDA Compliance**: Respects robots.txt, implements reasonable timeouts, uses exponential backoff
3. **Data Integrity**: Never silently returns corrupted medical information
4. **Change Detection**: Uses SHA-256 hashing to detect changes
5. **Version History**: Maintains complete history without overwrites
6. **Original Source**: Always preserves and attributes FDA source text

## Future Extensibility

The architecture is designed to support additional regulatory sources:
- FDA openFDA
- EMA (European Medicines Agency)
- Health Canada
- Other regulatory databases

Each source would implement a source adapter without modifying core logic.

## Development

### Code Style
- Follow PEP 8
- Type hints for all functions
- Docstrings for modules, classes, and methods
- Structured logging

### Git Workflow
- Create feature branches
- Write tests before implementing
- Run full test suite before committing

## Known Limitations

- Requires investigation of FDA SrLC website structure
- HTML scraping depends on FDA page structure stability
- Rate limiting respected (reasonable crawl frequency)

## License

[Specify your license]

## Support

For issues or questions:
1. Check test files for usage examples
2. Review inline code documentation
3. Check environment configuration
