import logging
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from excel_calculus.backend.app.config import (
    DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_TIMEOUT, DB_POOL_RECYCLE
)

logger = logging.getLogger("excel_calculus.database")

def create_configured_engine():
    """
    Creates an optimized SQLAlchemy engine.
    Supports production PostgreSQL with connection pooling and pool_pre_ping.
    Falls back gracefully to SQLite with WAL mode for local development.
    """
    if DATABASE_URL.startswith("postgresql"):
        logger.info("Initializing PostgreSQL database engine.")
        pg_engine = create_engine(
            DATABASE_URL,
            pool_size=DB_POOL_SIZE,
            max_overflow=DB_MAX_OVERFLOW,
            pool_timeout=DB_POOL_TIMEOUT,
            pool_recycle=DB_POOL_RECYCLE,
            pool_pre_ping=True,
            echo=False
        )
        return pg_engine, "postgresql"
    else:
        logger.info("Initializing SQLite database engine.")
        sqlite_engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            echo=False
        )

        @event.listens_for(sqlite_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.close()

        return sqlite_engine, "sqlite"

engine, DB_DIALECT = create_configured_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_db_health() -> dict:
    """Verifies database connectivity and returns health status."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "dialect": DB_DIALECT,
            "connected": True
        }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "dialect": DB_DIALECT,
            "connected": False,
            "error": str(exc)
        }
