"""Database engine, session factory and declarative Base."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")
_is_memory = _is_sqlite and (":memory:" in settings.database_url or settings.database_url == "sqlite://")

engine_options = {}
if _is_sqlite:
    # SQLite refuses to share a connection across threads unless told otherwise;
    # FastAPI runs sync endpoints in a thread pool.
    engine_options["connect_args"] = {"check_same_thread": False}
if _is_memory:
    # An in-memory database vanishes per connection, so keep exactly one.
    engine_options["poolclass"] = StaticPool

engine = create_engine(settings.database_url, **engine_options)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        """SQLite ignores FOREIGN KEY constraints unless this pragma is set."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create any missing tables (called once at application startup)."""
    import app.models  # noqa: F401  - importing registers the tables on Base

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency: one session per request, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
