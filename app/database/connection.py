from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def create_tables() -> None:
    """Create any missing tables (safe to run every time; never drops data)."""
    from app.database.models import Base

    Base.metadata.create_all(engine)


@contextmanager
def get_session():
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def describe_database() -> str:
    """Host/database name without the password, for logs."""
    url = engine.url
    return f"{url.get_backend_name()}://{url.host or ''}/{url.database}"
