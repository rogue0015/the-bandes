import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import settings


def database_path() -> Path:
    return settings.database_file()


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(database_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database() -> None:
    with connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY,
                canonical_url TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                organization TEXT,
                summary TEXT NOT NULL,
                record_type TEXT NOT NULL DEFAULT 'opportunity',
                category TEXT NOT NULL DEFAULT 'opportunity',
                source_ref TEXT,
                location TEXT,
                eligibility TEXT,
                deadline TEXT,
                matched_recipient TEXT,
                match_reason TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_opportunities_deadline
                ON opportunities(status, deadline);
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY,
                opportunity_id INTEGER NOT NULL REFERENCES opportunities(id)
                    ON DELETE CASCADE,
                offset_days INTEGER NOT NULL,
                scheduled_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                last_error TEXT,
                UNIQUE(opportunity_id, offset_days)
            );
            CREATE INDEX IF NOT EXISTS idx_reminders_due
                ON reminders(status, scheduled_at);
            CREATE TABLE IF NOT EXISTS notification_outbox (
                id INTEGER PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                message TEXT NOT NULL,
                recipients_json TEXT NOT NULL DEFAULT '[]',
                broadcast INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                scheduled_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_outbox_due
                ON notification_outbox(status, scheduled_at);
            CREATE TABLE IF NOT EXISTS managed_sites (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_scanned_at TEXT,
                scan_requested INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(managed_sites)")
        }
        if "scan_requested" not in columns:
            conn.execute(
                "ALTER TABLE managed_sites ADD COLUMN scan_requested INTEGER NOT NULL DEFAULT 1"
            )
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(opportunities)")
        }
        if "record_type" not in columns:
            conn.execute(
                "ALTER TABLE opportunities ADD COLUMN record_type TEXT NOT NULL DEFAULT 'opportunity'"
            )
        if "source_ref" not in columns:
            conn.execute("ALTER TABLE opportunities ADD COLUMN source_ref TEXT")
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunities_source_ref
               ON opportunities(source_ref)"""
        )
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(notification_outbox)")
        }
        if "broadcast" not in columns:
            conn.execute(
                "ALTER TABLE notification_outbox ADD COLUMN broadcast INTEGER NOT NULL DEFAULT 0"
            )
