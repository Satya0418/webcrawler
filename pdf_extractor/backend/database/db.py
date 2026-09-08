from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.config import BASE_DIR
from backend.database.models import Base

DB_PATH = BASE_DIR / "extractor.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

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
