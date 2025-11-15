from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, Tuple

from .schemas import Location, Source, VisitorEvent


CREATE_VISITS_TABLE = """
CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    visit_id TEXT NOT NULL UNIQUE,
    visitor_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    city TEXT,
    region TEXT,
    country TEXT,
    latitude REAL,
    longitude REAL,
    metadata TEXT
);
"""

CREATE_IMPORT_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS import_state (
    source TEXT PRIMARY KEY,
    last_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class VisitorDatabase:
    def __init__(self, path: Path):
        self.path = path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def initialize(self) -> None:
        with self.session() as conn:
            conn.execute(CREATE_VISITS_TABLE)
            conn.execute(CREATE_IMPORT_STATE_TABLE)

    def record_events(self, events: Iterable[VisitorEvent]) -> int:
        rows = [
            (
                event.source.value,
                event.visit_id,
                event.visitor_id,
                event.occurred_at.isoformat(),
                event.location.city,
                event.location.region,
                event.location.country,
                event.location.latitude,
                event.location.longitude,
                event.json(),
            )
            for event in events
        ]
        if not rows:
            return 0

        with self.session() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO visits
                (source, visit_id, visitor_id, occurred_at,
                 city, region, country, latitude, longitude, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            return conn.total_changes

    def last_seen_at(self, source: Source) -> datetime | None:
        with self.session() as conn:
            cursor = conn.execute(
                "SELECT last_seen_at FROM import_state WHERE source = ?", (source.value,)
            )
            row = cursor.fetchone()
        if row:
            return datetime.fromisoformat(row["last_seen_at"])
        return None

    def update_last_seen(self, source: Source, last_seen_at: datetime) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO import_state (source, last_seen_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                (source.value, last_seen_at.isoformat(), datetime.utcnow().isoformat()),
            )

    def aggregate_locations(self) -> Dict[str, Tuple[Location, int]]:
        with self.session() as conn:
            cursor = conn.execute(
                """
                SELECT
                    city,
                    MIN(region) AS region,
                    country,
                    COUNT(*) as visits
                FROM visits
                GROUP BY city, country
                """
            )
            rows = cursor.fetchall()

        aggregates: Dict[str, Tuple[Location, int]] = {}
        for row in rows:
            location = Location(
                city=row["city"],
                region=row["region"],
                country=row["country"],
            )
            key = location.normalized_key()
            aggregates[key] = (location, row["visits"])
        return aggregates

