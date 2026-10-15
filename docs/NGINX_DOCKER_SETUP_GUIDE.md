# Production Guide: Setting Up Nginx Reverse Proxy with Docker Compose

> **Target Audience:** Any developer or DevOps engineer setting up Nginx as a reverse proxy alongside containerized applications (React/Vite frontends, Python/Node/Go backends, databases, or microservices) using Docker Compose.

---

## Table of Contents
1. [Core Architectural Concept](#1-core-architectural-concept)
2. [Why Shield Ports? (Expose vs. Ports)](#2-why-shield-ports-expose-vs-ports)
3. [Docker Compose Configuration Pattern](#3-docker-compose-configuration-pattern)
4. [Nginx Configuration Anatomy](#4-nginx-configuration-anatomy)
5. [URL Routing & Path Mapping Recipes](#5-url-routing--path-mapping-recipes)
6. [WebSocket & Real-Time Connection Support](#6-websocket--real-time-connection-support)
7. [SSL / TLS & AWS Application Load Balancer (ALB) Setup](#7-ssl--tls--aws-application-load-balancer-alb-setup)
8. [Troubleshooting & Common Gotchas](#8-troubleshooting--common-gotchas)
9. [Step-by-Step Checklist for New Projects](#9-step-by-step-checklist-for-new-projects)

---

## 1. Core Architectural Concept

In modern production deployments, client browsers should **never** connect directly to application containers (e.g., Node.js, Vite, Uvicorn, Gunicorn, Spring Boot). Instead, **Nginx** serves as a unified **Reverse Proxy** at the network boundary.

```mermaid
flowchart TD
    Client["Clients / Browsers / Mobile Apps"] -->|"Public Traffic (Port 80 / 443 / 8443)"| Nginx["Nginx Reverse Proxy Container"]

    subgraph DockerNetwork ["Private Isolated Docker Network (e.g., app_default)"]
        Nginx -->|"Internal: http://app_backend:5173"| Frontend["Frontend Container (Vite / React / Next.js)"]
        Nginx -->|"Internal: http://api_backend:8000"| API["API Backend Container (FastAPI / Express / Django)"]
        API -->|"Internal: 5432"| DB[("PostgreSQL / MySQL Container")]
    end
```

### Why Use Nginx as a Reverse Proxy?
- **Unified Domain & Single Entry Point:** Serve your frontend, API endpoints, webhooks, and documentation under a single domain without messy CORS issues.
- **Security & Port Shielding:** Backend application runtimes are hidden inside the private Docker bridge network. Only Nginx opens a public port.
- **SSL / TLS Termination:** Decouple HTTPS certificate handling from your application code.
- **Performance:** Handle static file serving, keepalive connection pooling, and Gzip/Brotli compression at high speed.
- **WebSocket & HTTP/2 Support:** Seamlessly proxy persistent connections and upgrades.

---

## 2. Why Shield Ports? (Expose vs. Ports)

Understanding the difference between `ports` and `expose` in `docker-compose.yml` is critical for security:

| Directive | Behavior | Where Accessible | Example Use Case |
| :--- | :--- | :--- | :--- |
| `ports` | Maps host port to container port (`host:container`). | **Publicly** to the host, local network, and internet. | **Only Nginx** (`"80:80"`, `"443:443"`, or `"8443:443"`). |
| `expose` | Declares ports available **only** to linked containers on the same Docker network. | **Internal Docker network only** (never reaches host port). | **All Application & DB Services** (`5173`, `8000`, `5432`). |

> [!IMPORTANT]
> **Golden Rule:** In a reverse proxy setup, **only the Nginx container** should have a `ports:` section. All other services (frontend, backend, database) should use `expose:` or internal default networking.

---

## 3. Docker Compose Configuration Pattern

Here is the standard, production-ready `docker-compose.yml` structure:

```yaml
version: "3.8"

services:
  # ============================================================================
  # 1. Application Backend / Frontend Service
  # ============================================================================
  app-service:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ${APP_CONTAINER_NAME:-my_application}
    env_file:
      - .env
    # DO NOT use 'ports' here! Keep internal:
    expose:
      - "5173" # (e.g. 5173 for Vite, 8000 for FastAPI, 3000 for Next.js)
    networks:
      default:
        aliases:
          - app_backend
    restart: unless-stopped

  # ============================================================================
  # 2. Database Service (Optional)
  # ============================================================================
  db:
    image: postgres:15-alpine
    container_name: my_postgres_db
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-app_db}
    expose:
      - "5432"
    volumes:
      - db_data:/var/lib/postgresql/data
    restart: unless-stopped

  # ============================================================================
  # 3. Nginx Reverse Proxy Gateway
  # ============================================================================
  nginx:
    image: nginx:alpine
    container_name: ${NGINX_CONTAINER_NAME:-my_nginx_proxy}
    depends_on:
      - app-service
    ports:
      # Use 80 for HTTP or 8443 / 443 for HTTPS:
      - "${HTTP_PORT:-80}:80"
    volumes:
      # Mount Nginx configuration as read-only (:ro)
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      # If using SSL certificates:
      # - ./certs:/etc/nginx/certs:ro
    restart: unless-stopped

volumes:
  db_data:
    driver: local

networks:
  default:
    driver: bridge
```

---

## 4. Nginx Configuration Anatomy

Below is the annotated production `nginx/nginx.conf` file:

```nginx
events {
    # Maximum simultaneous connections per worker process
    worker_connections 1024;
}

http {
    # 1. MIME types & default encoding
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    # 2. Kernel performance tuning
    sendfile        on;
    tcp_nopush     on;
    tcp_nodelay    on;
    keepalive_timeout 65;

    # 3. Request payload limit (adjust based on your app, e.g. 50M for file uploads)
    client_max_body_size 50M;

    # 4. Gzip Compression for accelerated web assets
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
        application/atom+xml
        image/svg+xml;

    # 5. WebSocket Connection Upgrade Mapping
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    # 6. Upstream Service Definitions (Matches container names or aliases in Docker Compose)
    upstream app_backend {
        server app-service:5173;   # <service_name_or_alias>:<internal_port>
        keepalive 32;              # Reuses idle TCP connections to reduce latency
    }

    server {
        listen 80;
        server_name _;

        # Client header forwarding
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket & HTTP/1.1 persistence
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        # Timeouts (tune for long queries or file uploads)
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;

        # Reverse Proxy Routing
        location / {
            proxy_pass http://app_backend;
        }
    }
}
```

---

## 5. URL Routing & Path Mapping Recipes

Different applications require different routing patterns. Choose the recipe that matches your project:

### Recipe A: Single Single-Page App (SPA / Vite / React / Next.js)
Forward everything to the app container:
```nginx
location / {
    proxy_pass http://app_backend;
}
```

### Recipe B: Frontend + Separate Backend API
Route `/api/` traffic to the backend API service, and all other traffic to the frontend:
```nginx
upstream frontend_upstream {
    server frontend:3000;
    keepalive 32;
}

upstream backend_upstream {
    server backend_api:8000;
    keepalive 32;
}

server {
    listen 80;

    # API routes go directly to backend
    location /api/ {
        proxy_pass http://backend_upstream;
    }

    # All frontend pages & assets
    location / {
        proxy_pass http://frontend_upstream;
    }
}
```

### Recipe C: Path Stripping vs. Path Preserving (The Trailing Slash Rule)

> [!CAUTION]
> The presence or absence of a trailing slash in `proxy_pass` changes the request path forwarded to the backend!

- **Preserve Path (No trailing slash):**
  ```nginx
  location /crawler {
      proxy_pass http://crawler_backend;
  }
  ```
  Client requests `/crawler/search` $\rightarrow$ Backend receives **`/crawler/search`**.

- **Strip Prefix (With trailing slash):**
  ```nginx
  location /crawler/ {
      proxy_pass http://crawler_backend/;
  }
  ```
  Client requests `/crawler/search` $\rightarrow$ Backend receives **`/search`**.

---

## 6. WebSocket & Real-Time Connection Support

Vite HMR (Hot Module Reload), Next.js real-time reload, Socket.io, and backend WebSockets require HTTP/1.1 upgrade headers. 

Without this block in your `nginx.conf`, WebSocket connections will fail with `400 Bad Request` or drop immediately:

```nginx
# Top of http block:
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# Inside your server or location block:
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
```

---

## 7. SSL / TLS & AWS Application Load Balancer (ALB) Setup

### Architecture 1: Behind AWS ALB (Recommended for Cloud Deployments)
When running on EC2 behind an AWS ALB:
- The **ALB Listener** operates on public port **443** (with AWS ACM certificate).
- The **ALB Target Group** forwards traffic to your EC2 instance on port **8443**.
- **Advantage:** Running Docker on port **8443** avoids needing `sudo`/root privileges on Linux (`ports below 1024 require root`).

```yaml
# docker-compose.yml:
nginx:
  ports:
    - "${HTTPS_PORT:-8443}:443"
```

```nginx
# nginx.conf:
server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # ALB Health Check endpoint
    location /api/health {
        proxy_pass http://app_backend/api/health;
    }
}
```

### Architecture 2: Direct Internet Access (Standalone Host / Let's Encrypt)
If your EC2/VPS has a public IP directly connected to users:
- Forward HTTP (80) to HTTPS (443):
```nginx
server {
    listen 80;
    server_name example.com www.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name example.com www.example.com;

    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    location / {
        proxy_pass http://app_backend;
    }
}
```

---

## 8. Troubleshooting & Common Gotchas

### 1. `502 Bad Gateway`
- **Cause 1:** Upstream container is stopped or crashing. Run `docker ps` to verify all containers are healthy.
- **Cause 2:** Container name mismatch. If `nginx.conf` has `server app_backend:5173;`, Docker Compose service name or network alias **must** match `app_backend`.
- **Cause 3:** Network isolation. If running separate compose files, containers are in different Docker networks and cannot resolve each other's DNS. Always run unified compose stacks or link via external networks.
- **Cause 4:** Port mismatch. If the container listens on port `8000`, the upstream definition must be `:8000`, not `:5173`.

### 2. `405 Method Not Allowed`
- **Cause:** Using `curl -I` (capital `I`) sends an HTTP `HEAD` request. By default, many FastAPI/Python endpoints only accept `GET` requests (`allow: GET`).
- **Fix:** Use `curl -i` (lowercase `i`) to send a `GET` request with response headers. Browsers always use `GET`.

### 3. Database Password Special Characters (e.g., `@`)
- **Cause:** In URLs like `postgresql://user:pass@123@db:5432/app`, SQLAlchemy splits on `@` and thinks `123@db` is the hostname!
- **Fix:** URL-encode the password (`@` becomes `%40`).

### 4. `depends_on: condition: service_healthy` Stalls Nginx
- **Cause:** If Nginx waits for backend healthchecks, a temporary delay in backend startup blocks Nginx from starting entirely.
- **Fix:** Use standard dependency list `depends_on: [app-service]` so Nginx starts immediately and buffers incoming connections.

---

## 9. Step-by-Step Checklist for New Projects

When copying this pattern to any new project, complete this 5-minute checklist:

- [ ] **1. Choose Internal Ports:**
  - Vite/React dev: `5173`
  - Next.js: `3000`
  - FastAPI/Uvicorn: `8000`
  - Flask/Django: `5000` or `8000`
- [ ] **2. Configure `docker-compose.yml`:**
  - Place your app under `services:` with `expose: ["<PORT>"]`.
  - Add the `nginx:` service with `ports: ["${HTTP_PORT:-80}:80"]`.
  - Mount `./nginx/nginx.conf:/etc/nginx/nginx.conf:ro`.
- [ ] **3. Configure `nginx/nginx.conf`:**
  - Set `upstream app_backend { server <service_name>:<port>; keepalive 32; }`.
  - Ensure the WebSocket upgrade map is present.
  - Set `client_max_body_size` to your application's expected upload size.
- [ ] **4. Test Locally:**
  ```bash
  docker compose up --build -d
  docker ps
  curl -i http://localhost
  ```
- [ ] **5. Deploy to Production:**
  - For HTTPS/ALB: set `HTTPS_PORT=8443` in `.env` and mount `./certs`.
  - Verify container health: `docker ps`.
