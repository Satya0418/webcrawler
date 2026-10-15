"""
Database configuration and session management.
Supports PostgreSQL in production and SQLite for local development and testing.
"""
import logging
import re
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.config import settings

logger = logging.getLogger(__name__)

# SQLAlchemy setup
Base = declarative_base()


def _normalize_db_url(url: str) -> str:
    if not url:
        return url
    m = re.match(r'^(postgres(?:ql)?(?:\+[a-z0-9_]+)?://)([^:]+):(.*)@([^@/]+)(/.*)?$', url)
    if m:
        scheme, user, password, host, rest = m.groups()
        if "%" not in password:
            url = f"{scheme}{user}:{quote_plus(password)}@{host}{rest or ''}"
    return url


_db_url = _normalize_db_url(settings.DATABASE_URL)
connect_args = {"check_same_thread": False} if "sqlite" in _db_url else {}

# Create engine
engine = create_engine(
    _db_url,
    echo=settings.DATABASE_ECHO,
    connect_args=connect_args,
    pool_pre_ping=True,
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def get_db():
    """
    Dependency to get database session.
    Used in FastAPI endpoints.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """Alias for FastAPI dependency."""
    return get_db()


def init_db():
    """Initialize database tables."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified successfully")
    except Exception as e:
        logger.error(f"Error initializing database tables: {e}", exc_info=True)
