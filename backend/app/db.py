"""SQLAlchemy engine / session wiring (SQLite by default, zero setup)."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from sqlalchemy import inspect

    from app import models  # noqa: F401  (register tables)

    # weather_readings is a rebuildable audit cache: if its columns changed (station schema
    # update) drop and recreate it instead of failing on an old dev SQLite file.
    insp = inspect(engine)
    if "weather_readings" in insp.get_table_names():
        have = {c["name"] for c in insp.get_columns("weather_readings")}
        want = {c.name for c in models.WeatherReading.__table__.columns}
        if not want <= have:
            models.WeatherReading.__table__.drop(bind=engine)
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
