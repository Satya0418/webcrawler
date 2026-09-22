import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from backend.config import BASE_DIR
from backend.database.models import Base

_raw_db_path = os.getenv("SQLITE_DB_PATH")
if _raw_db_path:
    p = Path(_raw_db_path)
    DB_PATH = p if p.is_absolute() else (BASE_DIR / p)
else:
    DB_PATH = BASE_DIR / "extractor.db"

# Ensure parent directory of the database file exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initializes the database schema."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency provider for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
