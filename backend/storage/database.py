"""Explicit, idempotent SQLite initialization and short-lived transactions."""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = """
CREATE TABLE IF NOT EXISTS cvs (
    id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    cv_text TEXT NOT NULL,
    filename TEXT,
    target_role TEXT,
    headline TEXT,
    source_type TEXT NOT NULL CHECK(source_type IN ('text','txt','pdf','docx')),
    page_count INTEGER,
    extraction_quality TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_analyzed_at TEXT,
    latest_cv_score INTEGER CHECK(latest_cv_score BETWEEN 0 AND 100)
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    job_title TEXT NOT NULL,
    job_description TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    cv_id INTEGER NOT NULL REFERENCES cvs(id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK(status IN ('saved','applied','interview','offer','rejected','withdrawn')),
    date_applied TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(job_id, cv_id)
);
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY,
    cv_id INTEGER NOT NULL REFERENCES cvs(id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    mode TEXT NOT NULL CHECK(mode IN ('cv_only','job_match')),
    cv_quality_score INTEGER NOT NULL CHECK(cv_quality_score BETWEEN 0 AND 100),
    job_match_score INTEGER CHECK(job_match_score BETWEEN 0 AND 100),
    analysis_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK((mode='cv_only' AND job_id IS NULL AND job_match_score IS NULL)
       OR (mode='job_match' AND job_match_score IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_analysis_cv ON analyses(cv_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_job ON analyses(job_id, cv_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_application_cv ON applications(cv_id);
CREATE INDEX IF NOT EXISTS idx_application_job ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_application_status ON applications(status);
"""


def configured_database_path() -> Path:
    path = os.environ.get("CVISION_DB_PATH")
    if path is None:
        path = dotenv_values(PROJECT_ROOT / ".env", interpolate=False, encoding="utf-8-sig").get("CVISION_DB_PATH")
    resolved = Path(path or "data/cvision.db").expanduser()
    return resolved if resolved.is_absolute() else PROJECT_ROOT / resolved


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else configured_database_path()

    @contextmanager
    def transaction(self, connection=None):
        if connection is not None:
            yield connection
            return
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as connection:
            connection.executescript(SCHEMA)


def initialize_database(path: str | Path | None = None) -> Database:
    database = Database(path)
    database.initialize()
    return database
