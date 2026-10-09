import os
from pathlib import Path
from typing import List

# Base directory: /Users/.../excel_calculus
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Data and Storage Paths
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads")))
REPORT_OUTPUT_DIR = Path(os.getenv("REPORT_OUTPUT_DIR", str(DATA_DIR / "reports")))
LOG_DIR = Path(os.getenv("LOG_DIR", str(DATA_DIR / "logs")))

# Ensure runtime directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Database Configuration (PostgreSQL production-ready with SQLite local development fallback)
_DEFAULT_SQLITE_URL = f"sqlite:///{DATA_DIR / 'excel_calculus.db'}"
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_SQLITE_URL)

# Normalize postgres:// to postgresql+psycopg2:// for SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

# Connection Pool Settings
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))

# Reference Data Paths
SMQ_REFERENCE_PATH = os.getenv("SMQ_REFERENCE_PATH", "")

# Server & Security Configuration
ENV = os.getenv("ENV", "development").lower()
DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

# CORS Configuration
_CORS_RAW = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://localhost")
CORS_ORIGINS: List[str] = [origin.strip() for origin in _CORS_RAW.split(",") if origin.strip()]
if ENV == "development" and "*" not in CORS_ORIGINS:
    CORS_ORIGINS.append("http://localhost:8000")
