"""SQLite connection handling and schema initialization for the hub."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from config import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    node_id TEXT NOT NULL,
    sensor TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL,
    message TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events (timestamp);
CREATE INDEX IF NOT EXISTS idx_events_sensor ON events (sensor);

CREATE TABLE IF NOT EXISTS devices (
    node_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'offline',
    last_seen TEXT,
    capabilities TEXT
);

CREATE TABLE IF NOT EXISTS known_cards (
    card_uid TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL,
    last_seen TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    """Open a new connection to the SentinelAI SQLite database.

    Row factory is set to `sqlite3.Row` so callers can access columns
    by name (e.g. `row["timestamp"]`) instead of brittle index access.
    """
    os.makedirs(os.path.dirname(config.database.path), exist_ok=True)
    conn = sqlite3.connect(config.database.path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_cursor() -> Iterator[sqlite3.Cursor]:
    """Context manager that yields a cursor and commits/closes automatically.

    Usage:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM events")
            rows = cur.fetchall()
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't already exist. Safe to call on every startup."""
    with db_cursor() as cur:
        cur.executescript(_SCHEMA)
