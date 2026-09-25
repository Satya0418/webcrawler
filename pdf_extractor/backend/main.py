import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import BASE_DIR, DEBUG
from backend.database.db import init_db, check_db_health, DB_DIALECT
from backend.services.scanner_service import scanner_service

# Routers
from backend.api.upload import router as upload_router
from backend.api.files import router as files_router
from backend.api.extraction import router as extraction_router
from backend.api.products import router as products_router

logger = logging.getLogger("pdf_extractor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager:
    Initializes database schema and starts automated 30-minute background folder scanner.
    """
    logger.info("Initializing PDF Section Extraction System...")
    init_db()
    scanner_service.start()
    yield
    logger.info("Shutting down PDF Section Extraction System...")
    await scanner_service.stop()


app = FastAPI(
    title="Intelligent PDF Section Extraction & Product API",
    description=(
        "Production-grade deterministic PDF section extractor and automated 30-minute "
        "folder scanner with instant Section 16 retrieval for client websites."
    ),
    version="1.1.0",
    debug=DEBUG,
    lifespan=lifespan,
)

# Enable CORS for cross-origin client website access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(products_router)     # /api/v1/products/... & /api/v1/scanner/...
app.include_router(upload_router)       # /api/upload
app.include_router(files_router)        # /api/files/...
app.include_router(extraction_router)   # /api/extract/...

# Mount frontend directory for static assets
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def serve_index():
    """Serves the main extraction dashboard UI."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "status": "online",
        "service": "Intelligent PDF Section Extraction System",
        "docs": "/docs",
        "client_api": "/api/v1/products/section-16",
    }


from fastapi import Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from backend.database.db import get_db
from backend.database.models import ProductSectionRecord
from backend.api.products import get_product_section_16


@app.get("/p/{product_name}", response_class=HTMLResponse, summary="Short URL for Product Section 16 HTML view")
async def short_product_view(
    product_name: str,
    db: Session = Depends(get_db),
):
    """Clean short URL for viewing a product's Section 16 HTML (e.g. /p/ofloxacin)."""
    return await get_product_section_16(
        product_name=product_name,
        subsection=None,
        section=None,
        format="html",
        response_format=None,
        embed_only=False,
        include_tables=False,
        table_mode="neglect",
        db=db,
        _auth=True,
    )


@app.get("/p/{product_name}/{subsection}", response_class=HTMLResponse, summary="Short URL for Product Subsection HTML view")
async def short_subsection_view(
    product_name: str,
    subsection: str,
    db: Session = Depends(get_db),
):
    """Clean short URL for viewing a product's subsection HTML (e.g. /p/ofloxacin/16.1)."""
    return await get_product_section_16(
        product_name=product_name,
        subsection=subsection,
        section=None,
        format="html",
        response_format=None,
        embed_only=False,
        include_tables=False,
        table_mode="neglect",
        db=db,
        _auth=True,
    )


@app.get("/catalog", response_class=HTMLResponse, summary="Visual Product Directory & Quick Links")
@app.get("/products", response_class=HTMLResponse, summary="Visual Product Directory & Quick Links")
async def product_catalog(db: Session = Depends(get_db)):
    """Interactive visual catalog showing all indexed products with 1-click links to HTML, JSON, and Data views."""
    records = db.query(ProductSectionRecord).order_by(ProductSectionRecord.product_name).all()
    
    rows_html = []
    for r in records:
        prod = r.product_name
        p_slug = prod.lower().replace(" ", "%20")
        is_success = r.status == "success"
        status_badge = '<span style="background: #10b98122; color: #10b981; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">Indexed</span>' if is_success else '<span style="background: #ef444422; color: #ef4444; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">Not Found</span>'
        
        rows_html.append(f"""
        <tr class="product-row" data-name="{prod.lower()}">
            <td style="font-weight: 600; color: #f8fafc; font-size: 15px;">{prod}</td>
            <td style="color: #94a3b8; font-size: 12.5px; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{r.filename}</td>
            <td>{status_badge}</td>
            <td>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                    <a href="/p/{p_slug}/16.1" target="_blank" class="btn btn-primary" title="Open Section 16.1 text-only HTML view">
                        🌐 Subsection 16.1
                    </a>
                    <a href="/p/{p_slug}" target="_blank" class="btn btn-secondary" title="Open Section 16 HTML view">
                        📄 Section 16
                    </a>
                    <a href="/api/v1/products/section-16?product_name={p_slug}&subsection=16.1" target="_blank" class="btn btn-code" title="View JSON API response">
                        ⚡ JSON
                    </a>
                    <a href="/api/v1/products/section-16?product_name={p_slug}&subsection=16.1&format=data" target="_blank" class="btn btn-code" title="View HTML Table Data response">
                        📦 Data
                    </a>
                </div>
            </td>
        </tr>
        """)

    catalog_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pharmaceutical Products - Section 16 Catalog</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-dark: #0b0f19;
            --card-bg: #131b2e;
            --border-color: #1e293b;
            --accent: #38bdf8;
            --accent-glow: #0284c7;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Outfit', -apple-system, sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-main);
            min-height: 100vh;
            padding: 40px 24px;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        .header {{
            margin-bottom: 32px;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .title-group h1 {{
            font-size: 26px;
            font-weight: 700;
            background: linear-gradient(135deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }}
        .title-group p {{
            font-size: 14px;
            color: var(--text-muted);
        }}
        .stats-badge {{
            background: rgba(56, 189, 248, 0.1);
            border: 1px solid rgba(56, 189, 248, 0.25);
            color: var(--accent);
            padding: 8px 16px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
        }}
        .search-bar {{
            width: 100%;
            margin-bottom: 24px;
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px 18px;
            font-size: 15px;
            color: var(--text-main);
            outline: none;
            transition: border-color 0.2s;
        }}
        .search-bar:focus {{
            border-color: var(--accent);
        }}
        .table-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}
        th {{
            background: #0f172a;
            color: var(--text-muted);
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 14px 18px;
            border-bottom: 1px solid var(--border-color);
        }}
        td {{
            padding: 14px 18px;
            border-bottom: 1px solid var(--border-color);
            vertical-align: middle;
        }}
        tr:last-child td {{ border-bottom: none; }}
        tr:hover td {{ background: rgba(255,255,255,0.02); }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.2s;
        }}
        .btn-primary {{
            background: #0284c7;
            color: #ffffff;
        }}
        .btn-primary:hover {{
            background: #0369a1;
            transform: translateY(-1px);
        }}
        .btn-secondary {{
            background: #334155;
            color: #f1f5f9;
        }}
        .btn-secondary:hover {{
            background: #475569;
        }}
        .btn-code {{
            background: rgba(148, 163, 184, 0.1);
            color: #cbd5e1;
            border: 1px solid rgba(148, 163, 184, 0.2);
            font-family: 'JetBrains Mono', monospace;
            font-size: 11.5px;
        }}
        .btn-code:hover {{
            background: rgba(56, 189, 248, 0.15);
            color: var(--accent);
            border-color: var(--accent);
        }}
        .short-url-box {{
            margin-top: 32px;
            padding: 20px;
            background: rgba(30, 41, 59, 0.5);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            font-size: 13.5px;
            color: var(--text-muted);
            line-height: 1.6;
        }}
        .short-url-box code {{
            background: #0f172a;
            color: #38bdf8;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'JetBrains Mono', monospace;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="title-group">
                <h1>⚡ Pharmaceutical Products Section 16 Catalog</h1>
                <p>Real-time indexed medical documents with instant, table-neglected Section 16 retrieval.</p>
            </div>
            <div class="stats-badge">
                ● {len(records)} Products In Database
            </div>
        </header>

        <input type="text" id="searchInput" class="search-bar" placeholder="🔍 Search medicine or brand name (e.g. Ofloxacin, Amikacin, Lipitor)...">

        <div class="table-card">
            <table>
                <thead>
                    <tr>
                        <th>Product / Medicine</th>
                        <th>Source Document</th>
                        <th>Status</th>
                        <th>Quick Actions</th>
                    </tr>
                </thead>
                <tbody id="productTableBody">
                    {''.join(rows_html)}
                </tbody>
            </table>
        </div>

        <div class="short-url-box">
            <strong style="color: #f8fafc;">💡 Short URL Quick Reference (No long URLs needed!):</strong><br>
            • View Subsection 16.1 in browser: <code>http://127.0.0.1:8000/p/&lt;medicine&gt;/16.1</code> (e.g. <a href="/p/ofloxacin/16.1" style="color: #38bdf8;">/p/ofloxacin/16.1</a>)<br>
            • View Section 16 in browser: <code>http://127.0.0.1:8000/p/&lt;medicine&gt;</code> (e.g. <a href="/p/ofloxacin" style="color: #38bdf8;">/p/ofloxacin</a>)<br>
            • JSON API endpoint: <code>/api/v1/products/section-16?product_name=&lt;medicine&gt;&amp;subsection=16.1</code><br>
            • Whenever any new PDF is dropped into your folder, it will appear here automatically!
        </div>
    </div>

    <script>
        const searchInput = document.getElementById('searchInput');
        const rows = document.querySelectorAll('.product-row');
        searchInput.addEventListener('input', (e) => {{
            const query = e.target.value.toLowerCase().trim();
            rows.forEach(row => {{
                const name = row.getAttribute('data-name') || '';
                row.style.display = name.includes(query) ? '' : 'none';
            }});
        }});
    </script>
</body>
</html>"""
    return HTMLResponse(content=catalog_html)


@app.get("/api/health")
async def health_check():
    """Comprehensive system, database, and background scanner health check."""
    db_health = check_db_health()
    scanner_info = scanner_service.get_status()
    
    overall_status = "healthy" if db_health.get("connected") else "degraded"
    
    return {
        "status": overall_status,
        "engine": "deterministic_hierarchical_extractor",
        "database": {
            "status": db_health.get("status"),
            "dialect": DB_DIALECT,
            "connected": db_health.get("connected"),
        },
        "background_scanner": {
            "status": scanner_info.get("status"),
            "watch_directory": scanner_info.get("watch_directory"),
            "interval_minutes": scanner_info.get("scan_interval_minutes"),
            "target_section": scanner_info.get("target_section"),
            "total_products_indexed": scanner_info.get("total_products_indexed"),
            "last_scan": scanner_info.get("last_scan_time"),
            "next_scan": scanner_info.get("next_scan_time"),
        },
        "version": "1.1.0",
    }

