"""
Shared pytest fixtures for Health Canada InfoWatch test suite.

Provides an in-memory SQLite database session (db fixture) identical to
the existing integration test setup, so these tests run without a real DB.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base


TEST_DATABASE_URL = "sqlite:///:memory:"

_test_engine = create_engine(
    TEST_DATABASE_URL,
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
)
_TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


@pytest.fixture
def db():
    """
    Provide an in-memory SQLite session scoped to a single test.
    Tables are created before and dropped after each test.
    """
    Base.metadata.create_all(bind=_test_engine)
    session = _TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_test_engine)
