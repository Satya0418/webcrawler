import logging
import os
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError

from backend.config import BASE_DIR, DATABASE_URL as CONFIG_DATABASE_URL
from backend.database.models import Base

logger = logging.getLogger("pdf_extractor.db")

# Fallback SQLite path
_raw_sqlite_path = os.getenv("SQLITE_DB_PATH")
if _raw_sqlite_path:
    p = Path(_raw_sqlite_path)
    SQLITE_PATH = p if p.is_absolute() else (BASE_DIR / p)
else:
    SQLITE_PATH = BASE_DIR / "extractor.db"

SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
SQLITE_URL = f"sqlite:///{SQLITE_PATH}"


def _normalize_database_url(url: str) -> str:
    """Ensures PostgreSQL URLs use postgresql+psycopg2 for SQLAlchemy 2.0 compatibility."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def create_configured_engine():
    """
    Creates an optimized SQLAlchemy engine.
    Prioritizes PostgreSQL for production and concurrent client workloads.
    Falls back gracefully to SQLite WAL mode if PostgreSQL is not reachable locally.
    """
    target_url = _normalize_database_url(CONFIG_DATABASE_URL or os.getenv("DATABASE_URL", ""))

    if target_url and target_url.startswith("postgresql"):
        try:
            logger.info("Connecting to PostgreSQL database at %s", target_url.split("@")[-1])
            pg_engine = create_engine(
                target_url,
                pool_size=10,
                max_overflow=20,
                pool_timeout=30,
                pool_recycle=1800,
                pool_pre_ping=True,
                echo=False,
            )
            # Verify connectivity immediately
            with pg_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Successfully connected to PostgreSQL engine.")
            return pg_engine, "postgresql", target_url
        except OperationalError as err:
            logger.warning(
                "PostgreSQL configured but connection failed: %s. "
                "Falling back to local SQLite with WAL mode enabled.",
                err
            )

    # SQLite Configuration (Local Dev / Fallback)
    logger.info("Initializing SQLite database at %s", SQLITE_PATH)
    sqlite_engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(sqlite_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()

    return sqlite_engine, "sqlite", SQLITE_URL


engine, DB_DIALECT, ACTIVE_DATABASE_URL = create_configured_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initializes all database tables defined in models."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema initialized successfully (%s).", DB_DIALECT)
    except Exception as exc:
        logger.error("Failed to initialize database tables: %s", exc)
        raise


def get_db() -> Generator[Session, None, None]:
    """Dependency provider for FastAPI route handlers."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for standalone background worker sessions."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_db_health() -> dict:
    """Verifies database connectivity and returns health status."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "dialect": DB_DIALECT,
            "connected": True,
        }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "dialect": DB_DIALECT,
            "connected": False,
            "error": str(exc),
        }
