"""
UrbanSense AI — Database session management
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from backend.app.core.config import get_settings


def get_engine():
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )


def get_session_factory(engine=None):
    if engine is None:
        engine = get_engine()
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


SessionLocal = get_session_factory()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()