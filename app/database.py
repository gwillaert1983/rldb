import libsql_experimental as libsql
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from app.config import settings


class _LibSQLConnection:
    """Wraps libsql connection to fill in missing sqlite3-compat methods."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    # SQLAlchemy's SQLite dialect calls this; libsql doesn't support it
    def create_function(self, name, num_params, func, deterministic=False):
        pass

    def cursor(self):
        return self._conn.cursor()

    def execute(self, *a, **kw):
        return self._conn.execute(*a, **kw)

    def executemany(self, *a, **kw):
        return self._conn.executemany(*a, **kw)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()


def _make_connection():
    conn = libsql.connect(
        database=settings.TURSO_DATABASE_URL,
        auth_token=settings.TURSO_AUTH_TOKEN,
    )
    return _LibSQLConnection(conn)


engine = create_engine("sqlite://", creator=_make_connection, poolclass=NullPool)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db():
    from app.models import Base
    from sqlalchemy import text
    Base.metadata.create_all(bind=engine)
    # Add columns introduced after initial table creation
    _migrate(text("ALTER TABLE scraper_settings ADD COLUMN gender_filter TEXT"))
    _migrate(text("ALTER TABLE scraper_settings ADD COLUMN scrape_interval_minutes INTEGER"))
    _migrate(text("ALTER TABLE profiles ADD COLUMN is_archived INTEGER DEFAULT 0"))
    _migrate(text("ALTER TABLE scrape_runs ADD COLUMN profiles_processed INTEGER DEFAULT 0"))
    _migrate(text("ALTER TABLE advertisements ADD COLUMN description TEXT"))
    _migrate(text("ALTER TABLE advertisements ADD COLUMN published_at DATETIME"))
    _migrate(text("ALTER TABLE profiles ADD COLUMN is_contacted BOOLEAN DEFAULT 0"))
    _migrate(text("ALTER TABLE profiles ADD COLUMN contacted_at DATETIME"))
    _migrate(text("ALTER TABLE profiles ADD COLUMN contacted_note TEXT"))
    _migrate(text("ALTER TABLE profiles ADD COLUMN is_visited BOOLEAN DEFAULT 0"))
    _migrate(text("ALTER TABLE profiles ADD COLUMN visited_at DATETIME"))
    _migrate(text("ALTER TABLE profiles ADD COLUMN visited_note TEXT"))
    _migrate(text("ALTER TABLE scrape_runs ADD COLUMN profiles_skipped INTEGER DEFAULT 0"))
    _migrate(text("ALTER TABLE profiles ADD COLUMN is_favourite BOOLEAN DEFAULT 0"))
    _migrate(text("""CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        visited_at DATETIME NOT NULL,
        amount REAL,
        note TEXT
    )"""))
    _migrate(text("ALTER TABLE visits ADD COLUMN hotel_cost REAL"))
    _migrate(text("ALTER TABLE visits ADD COLUMN extra_cost REAL"))
    _migrate(text("""INSERT INTO visits (profile_id, visited_at, note)
        SELECT id, visited_at, visited_note FROM profiles
        WHERE is_visited = 1 AND visited_at IS NOT NULL
          AND id NOT IN (SELECT DISTINCT profile_id FROM visits)"""))
    with engine.connect() as conn:
        conn.execute(text(
            "UPDATE scrape_runs SET status='failed', "
            "error_message='Onderbroken bij herstart', "
            "finished_at=datetime('now') "
            "WHERE status='running'"
        ))
        conn.commit()


def _migrate(stmt):
    try:
        with engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()
    except Exception:
        pass  # Column already exists
