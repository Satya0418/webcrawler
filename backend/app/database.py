"""
Database configuration and session management.
Supports PostgreSQL in production and SQLite for local development and testing.
"""
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.config import settings

logger = logging.getLogger(__name__)

# SQLAlchemy setup
Base = declarative_base()

connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
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
