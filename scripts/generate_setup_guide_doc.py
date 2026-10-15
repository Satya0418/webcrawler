#!/usr/bin/env python3
"""
Generates a professional Word Document (.docx) for:
Nginx Reverse Proxy & Docker Compose Production Engineering Guide
"""
import os
import shutil
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def add_code_block(doc, code_text):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, "F4F6F8")
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)
    
    # Border styling
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:top w:val="single" w:sz="6" w:space="0" w:color="D0D7DE"/><w:left w:val="single" w:sz="18" w:space="0" w:color="0969DA"/><w:bottom w:val="single" w:sz="6" w:space="0" w:color="D0D7DE"/><w:right w:val="single" w:sz="6" w:space="0" w:color="D0D7DE"/></w:tcBorders>')
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(code_text.strip())
    run.font.name = "Consolas"
    run.font.size = Pt(9.5)
    run.font.color.rgb = RGBColor(36, 41, 47)
    
    # Spacer
    sp = doc.add_paragraph()
    sp.paragraph_format.space_before = Pt(0)
    sp.paragraph_format.space_after = Pt(6)

def add_callout(doc, title, text, color_hex="0969DA", bg_hex="EBF5FF"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, bg_hex)
    set_cell_margins(cell, top=120, bottom=120, left=180, right=180)
    
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:top w:val="none"/><w:left w:val="single" w:sz="24" w:space="0" w:color="{color_hex}"/><w:bottom w:val="none"/><w:right w:val="none"/></w:tcBorders>')
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    run_title = p.add_run(f"[{title}] ")
    run_title.bold = True
    run_title.font.name = "Calibri"
    run_title.font.size = Pt(10.5)
    run_title.font.color.rgb = RGBColor.from_string(color_hex)
    
    run_text = p.add_run(text)
    run_text.font.name = "Calibri"
    run_text.font.size = Pt(10.5)
    run_text.font.color.rgb = RGBColor(36, 41, 47)
    
    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(6)

def build_document():
    doc = Document()
    
    # Page Setup (1 inch margins)
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        
    # Styles
    styles = doc.styles
    normal_style = styles['Normal']
    normal_style.font.name = 'Calibri'
    normal_style.font.size = Pt(11)
    normal_style.font.color.rgb = RGBColor(36, 41, 47)
    
    # Title
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(4)
    run_title = title_p.add_run("Production Architecture & Engineering Guide")
    run_title.bold = True
    run_title.font.size = Pt(24)
    run_title.font.color.rgb = RGBColor(15, 34, 64) # Navy Blue
    
    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_after = Pt(18)
    run_sub = sub_p.add_run("Setting Up Nginx Reverse Proxy & Docker Compose for Multi-Service Web Applications")
    run_sub.font.size = Pt(14)
    run_sub.font.color.rgb = RGBColor(87, 96, 106)
    
    # Metadata Block
    meta_tbl = doc.add_table(rows=2, cols=2)
    meta_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_data = [
        ("Target Audience:", "Full-Stack Engineers, DevOps, System Architects"),
        ("Version & Status:", "Production Standard 1.0 (Ready for Enterprise & AWS)")
    ]
    for row_idx, (label, val) in enumerate(meta_data):
        c1 = meta_tbl.cell(row_idx, 0)
        c2 = meta_tbl.cell(row_idx, 1)
        c1.text = label
        c2.text = val
        c1.paragraphs[0].runs[0].bold = True
        c1.paragraphs[0].runs[0].font.size = Pt(10)
        c2.paragraphs[0].runs[0].font.size = Pt(10)
        set_cell_background(c1, "F6F8FA")
        set_cell_background(c2, "F6F8FA")
        set_cell_margins(c1, 60, 60, 100, 100)
        set_cell_margins(c2, 60, 60, 100, 100)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(12)
    
    # Divider
    hr = doc.add_paragraph()
    hr.paragraph_format.space_after = Pt(14)
    pBdr = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="12" w:space="1" w:color="0969DA"/></w:pBdr>')
    hr._p.get_or_add_pPr().append(pBdr)

    # Section 1
    h1 = doc.add_heading("1. Executive Summary & Core Architectural Concept", level=1)
    h1.paragraph_format.space_before = Pt(16)
    h1.paragraph_format.space_after = Pt(8)
    
    p = doc.add_paragraph(
        "In production environments, client browsers and mobile applications should never connect "
        "directly to application runtime engines (Node.js, Vite, FastAPI/Uvicorn, Gunicorn, Django, etc.). "
        "Instead, an Nginx Reverse Proxy acts as the single unified perimeter gateway."
    )
    p.paragraph_format.line_spacing = 1.2
    
    add_callout(
        doc,
        "CORE VALUE PROPOSITION",
        "By placing Nginx in front of Docker containers, you achieve unified routing under a single domain "
        "(eliminating cross-origin CORS errors), port shielding, centralized SSL/TLS termination, Gzip asset compression, "
        "and persistent WebSocket support.",
        color_hex="0969DA",
        bg_hex="F0F6FF"
    )
    
    # Architecture Flow Description
    doc.add_heading("Traffic Flow Architecture", level=2)
    p_flow = doc.add_paragraph()
    p_flow.add_run("1. Public Ingress: ").bold = True
    p_flow.add_run("External clients send requests over HTTPS/HTTP to Port 80, 443, or 8443 (via AWS Load Balancer).\n")
    p_flow.add_run("2. Reverse Proxy Inspection: ").bold = True
    p_flow.add_run("Nginx receives the request, terminates SSL, applies rate limits, and inspects the URL path.\n")
    p_flow.add_run("3. Internal Routing: ").bold = True
    p_flow.add_run("Nginx forwards the request over the private, isolated Docker bridge network to the target container (e.g. Frontend on port 5173 or API on port 8000).\n")
    p_flow.add_run("4. Shielded Database: ").bold = True
    p_flow.add_run("Databases (PostgreSQL, Redis) remain strictly internal to the network and are completely unreachable from the public internet.")

    # Section 2
    h2 = doc.add_heading("2. The Port Shielding Rule (expose vs. ports)", level=1)
    h2.paragraph_format.space_before = Pt(16)
    h2.paragraph_format.space_after = Pt(8)
    
    p = doc.add_paragraph(
        "A critical security rule when authoring docker-compose.yml is understanding the difference between ports: and expose:."
    )
    
    # Table of Ports vs Expose
    tbl_ports = doc.add_table(rows=3, cols=4)
    tbl_ports.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Directive", "Network Scope", "Host Visibility", "Applicable Services"]
    for col_idx, text in enumerate(headers):
        cell = tbl_ports.cell(0, col_idx)
        cell.text = text
        cell.paragraphs[0].runs[0].bold = True
        set_cell_background(cell, "0F2240")
        cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)
        set_cell_margins(cell, 80, 80, 100, 100)
        
    data_ports = [
        ("ports:", "Public & Host", "Maps container port to host interface (0.0.0.0:host:container)", "Nginx Gateway Only (e.g., 80:80, 8443:443)"),
        ("expose:", "Internal Docker Only", "Completely hidden from host; accessible ONLY by peer containers", "All App Backends, APIs, Vite Frontends, Databases")
    ]
    for row_idx, row_data in enumerate(data_ports, start=1):
        for col_idx, text in enumerate(row_data):
            cell = tbl_ports.cell(row_idx, col_idx)
            cell.text = text
            set_cell_background(cell, "F8FAFC" if row_idx % 2 == 1 else "FFFFFF")
            set_cell_margins(cell, 80, 80, 100, 100)
            cell.paragraphs[0].runs[0].font.size = Pt(9.5)
            
    doc.add_paragraph().paragraph_format.space_after = Pt(10)
    
    add_callout(
        doc,
        "IMPORTANT SECURITY DIRECTIVE",
        "Never use 'ports:' on database containers (Postgres, MongoDB) or internal backend APIs in production. "
        "Only the Nginx container should expose external host ports.",
        color_hex="D1242F",
        bg_hex="FFF5F5"
    )

    # Section 3
    h3 = doc.add_heading("3. Production Docker Compose Configuration", level=1)
    h3.paragraph_format.space_before = Pt(16)
    h3.paragraph_format.space_after = Pt(8)
    
    p = doc.add_paragraph(
        "Below is the standardized docker-compose.yml template. It defines an application service, an internal database, "
        "and the Nginx gateway service communicating across a dedicated bridge network:"
    )
    
    docker_compose_code = """# ==============================================================================
# DOCKER COMPOSE PRODUCTION SPECIFICATION
# ==============================================================================
services:

  # 1. Main Application Runtime / Backend
  app-backend:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ${APP_CONTAINER_NAME:-app_backend}
    env_file:
      - .env
    expose:
      - "5173" # Internal application port (e.g. 5173 for Vite, 8000 for FastAPI)
    networks:
      default:
        aliases:
          - app_backend
    restart: unless-stopped

  # 2. Production Database (Private to Docker network)
  db:
    image: postgres:15-alpine
    container_name: app_postgres_db
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-production_db}
    expose:
      - "5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  # 3. Nginx Reverse Proxy Ingress Gateway
  nginx:
    image: nginx:alpine
    container_name: ${NGINX_CONTAINER_NAME:-app_nginx_gateway}
    depends_on:
      - app-backend
    ports:
      - "${HTTP_PORT:-80}:80"
      # For SSL / AWS ALB deployments:
      # - "${HTTPS_PORT:-8443}:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    restart: unless-stopped

volumes:
  postgres_data:
    driver: local

networks:
  default:
    driver: bridge"""
    add_code_block(doc, docker_compose_code)

    # Section 4
    h4 = doc.add_heading("4. Production Nginx Configuration (nginx.conf)", level=1)
    h4.paragraph_format.space_before = Pt(16)
    h4.paragraph_format.space_after = Pt(8)
    
    p = doc.add_paragraph(
        "Below is the comprehensive nginx/nginx.conf file. It includes kernel socket optimizations, Gzip compression, "
        "bidirectional WebSocket upgrade mapping, upstream keepalive pooling, and client header preservation:"
    )
    
    nginx_code = """events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    # Performance Tuning
    sendfile        on;
    tcp_nopush     on;
    tcp_nodelay    on;
    keepalive_timeout 65;
    client_max_body_size 50M;

    # Gzip Asset Compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/xml
        application/json
        application/javascript
        application/xml+rss
        image/svg+xml;

    # WebSocket Upgrade Mapping
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    # Upstream Container Definition (matches service name in docker-compose)
    upstream app_backend {
        server app-backend:5173;
        keepalive 32;
    }

    server {
        listen 80;
        server_name _;

        # Client Identity Forwarding
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket & Persistent HTTP/1.1
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;

        # Default Routing
        location / {
            proxy_pass http://app_backend;
        }
    }
}"""
    add_code_block(doc, nginx_code)

    # Section 5
    h5 = doc.add_heading("5. URL Routing & Path Mapping Recipes", level=1)
    h5.paragraph_format.space_before = Pt(16)
    h5.paragraph_format.space_after = Pt(8)
    
    p = doc.add_paragraph(
        "Different projects require different URL structures. Engineers can adapt these modular routing blocks:"
    )
    
    # Recipe 1
    doc.add_heading("Recipe A: Single-Page Application (SPA / React / Vite / Next.js)", level=2)
    p = doc.add_paragraph("Routes all incoming requests directly to the frontend application container:")
    add_code_block(doc, "location / {\n    proxy_pass http://app_backend;\n}")
    
    # Recipe 2
    doc.add_heading("Recipe B: Frontend on Root + API on /api/ Path", level=2)
    p = doc.add_paragraph("Decouples frontend static pages from backend API microservices under one domain:")
    recipe_b = """# Backend REST API
location /api/ {
    proxy_pass http://api_backend;
}

# Frontend User Interface
location / {
    proxy_pass http://frontend_backend;
}"""
    add_code_block(doc, recipe_b)
    
    # Recipe 3: Trailing Slash Rule
    doc.add_heading("Recipe C: The Trailing Slash Rule (Path Stripping vs. Preserving)", level=2)
    add_callout(
        doc,
        "CRITICAL NGINX ROUTING RULE",
        "A trailing slash on the proxy_pass URL changes how Nginx forwards the URI path:\n"
        "• Without Trailing Slash (proxy_pass http://crawler;): Preserves full path. Client /crawler/run -> Backend /crawler/run.\n"
        "• With Trailing Slash (proxy_pass http://crawler/;): Strips prefix. Client /crawler/run -> Backend /run.",
        color_hex="0969DA",
        bg_hex="F0F6FF"
    )

    # Section 6
    h6 = doc.add_heading("6. Cloud Deployment & AWS Application Load Balancer (ALB)", level=1)
    h6.paragraph_format.space_before = Pt(16)
    h6.paragraph_format.space_after = Pt(8)
    
    p = doc.add_paragraph(
        "When deploying to AWS EC2 behind an Application Load Balancer (ALB), Linux security prevents non-root "
        "users from binding to privileged ports below 1024 (e.g. port 80 and 443). To solve this cleanly without "
        "modifying Linux root privileges, use the Port 8443 Target Group architecture:"
    )
    
    p_alb = doc.add_paragraph()
    p_alb.add_run("1. Public ALB Listener: ").bold = True
    p_alb.add_run("Listens on Port 443 (HTTPS) with AWS ACM Certificate.\n")
    p_alb.add_run("2. ALB Target Group: ").bold = True
    p_alb.add_run("Forwards encrypted HTTPS traffic to the EC2 host on Port 8443.\n")
    p_alb.add_run("3. Nginx Port Binding: ").bold = True
    p_alb.add_run("Maps host 8443 into container 443 ('${HTTPS_PORT:-8443}:443').\n")
    p_alb.add_run("4. Health Check Path: ").bold = True
    p_alb.add_run("The ALB Target Group sends health probes to /api/health.")
    
    alb_nginx_code = """server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;
    ssl_protocols       TLSv1.2 TLSv1.3;

    location /api/health {
        proxy_pass http://app_backend/api/health;
    }

    location / {
        proxy_pass http://app_backend;
    }
}"""
    add_code_block(doc, alb_nginx_code)

    # Section 7
    h7 = doc.add_heading("7. Production Troubleshooting & Diagnostic Guide", level=1)
    h7.paragraph_format.space_before = Pt(16)
    h7.paragraph_format.space_after = Pt(8)
    
    tbl_trouble = doc.add_table(rows=4, cols=3)
    tbl_trouble.alignment = WD_TABLE_ALIGNMENT.CENTER
    trouble_headers = ["Symptom / Error", "Root Cause", "Actionable Solution"]
    for col_idx, text in enumerate(trouble_headers):
        cell = tbl_trouble.cell(0, col_idx)
        cell.text = text
        cell.paragraphs[0].runs[0].bold = True
        set_cell_background(cell, "0F2240")
        cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)
        set_cell_margins(cell, 80, 80, 100, 100)
        
    trouble_data = [
        (
            "502 Bad Gateway",
            "Nginx cannot reach upstream container due to wrong service name, port mismatch, or stopped backend.",
            "1. Run 'docker ps' to confirm backend is Up.\n2. Verify upstream host matches service name.\n3. Ensure all containers share the same network."
        ),
        (
            "405 Method Not Allowed",
            "Testing with 'curl -I' (capital I) sends an HTTP HEAD request. Python/FastAPI only accepts GET by default.",
            "Use 'curl -i' (lowercase i) to send a GET request with response headers. Web browsers always send GET."
        ),
        (
            "Database Host Lookup Failure",
            "Special characters like '@' in database password split the URL (e.g. postgresql://user:pwd@123@db).",
            "Automatically URL-encode the password in your application database initialization (turn '@' into '%40')."
        )
    ]
    for row_idx, row_data in enumerate(trouble_data, start=1):
        for col_idx, text in enumerate(row_data):
            cell = tbl_trouble.cell(row_idx, col_idx)
            cell.text = text
            set_cell_background(cell, "F8FAFC" if row_idx % 2 == 1 else "FFFFFF")
            set_cell_margins(cell, 80, 80, 100, 100)
            cell.paragraphs[0].runs[0].font.size = Pt(9.5)
            
    doc.add_paragraph().paragraph_format.space_after = Pt(10)

    # Section 8
    h8 = doc.add_heading("8. New Project Implementation Checklist", level=1)
    h8.paragraph_format.space_before = Pt(16)
    h8.paragraph_format.space_after = Pt(8)
    
    checklist_items = [
        "[ ] 1. Identify internal application port (Vite: 5173, Next.js: 3000, FastAPI: 8000, Flask: 5000).",
        "[ ] 2. In docker-compose.yml, place app under services: using 'expose: [\"<PORT>\"]'.",
        "[ ] 3. In docker-compose.yml, configure nginx service with 'ports: [\"${HTTP_PORT:-80}:80\"]'.",
        "[ ] 4. Mount nginx configuration as read-only: './nginx/nginx.conf:/etc/nginx/nginx.conf:ro'.",
        "[ ] 5. In nginx.conf, set 'upstream app_backend { server <service_name>:<port>; keepalive 32; }'.",
        "[ ] 6. Ensure WebSocket upgrade map block is included for modern hot-reloading and sockets.",
        "[ ] 7. Launch stack: 'docker compose up --build -d' and verify: 'docker ps'.",
        "[ ] 8. Verify endpoints: 'curl -i http://localhost' (HTTP 200 OK)."
    ]
    for item in checklist_items:
        p_check = doc.add_paragraph(item)
        p_check.paragraph_format.space_before = Pt(2)
        p_check.paragraph_format.space_after = Pt(2)
        p_check.runs[0].font.name = "Consolas"
        p_check.runs[0].font.size = Pt(10)

    # Save documents
    workspace_path = "/Users/satya/projects/webcrwler/docs/NGINX_DOCKER_SETUP_GUIDE.docx"
    desktop_path = "/Users/satya/Desktop/random/NGINX_SETUP_GUIDE.docx"
    
    os.makedirs(os.path.dirname(workspace_path), exist_ok=True)
    os.makedirs(os.path.dirname(desktop_path), exist_ok=True)
    
    doc.save(workspace_path)
    shutil.copyfile(workspace_path, desktop_path)
    print(f"Generated DOCX: {workspace_path}")
    print(f"Generated DOCX: {desktop_path}")

if __name__ == "__main__":
    build_document()
