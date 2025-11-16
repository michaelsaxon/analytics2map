from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

from .schemas import Location


class VisitStore:
    """Simple TSV-based append-only log of visits."""

    def __init__(self, tsv_path: Path, last_seen_path: Path | None = None):
        self.tsv_path = tsv_path
        self.last_seen_path = last_seen_path or tsv_path.parent / "last_seen.txt"
        self.tsv_path.parent.mkdir(parents=True, exist_ok=True)

    def append_visit(
        self, city: str | None, country: str, timestamp: datetime, num_unique: int
    ) -> None:
        """Append a single visit record to the TSV file.

        Column order: timestamp, country, city, num_unique.
        City is written as the literal string "NULL" when missing.
        """
        file_exists = self.tsv_path.exists()
        with self.tsv_path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter="\t")
            if not file_exists:
                writer.writerow(["timestamp", "country", "city", "num_unique"])
            writer.writerow(
                [timestamp.isoformat(), country, city if city is not None else "NULL", num_unique]
            )

    def get_last_timestamp(self) -> datetime | None:
        """Get the most recent timestamp from the TSV file or last_seen.txt."""
        # First check last_seen.txt (faster)
        if self.last_seen_path.exists():
            try:
                content = self.last_seen_path.read_text(encoding="utf-8").strip()
                if content:
                    return datetime.fromisoformat(content)
            except (ValueError, OSError):
                pass

        # Fallback: scan TSV file
        if not self.tsv_path.exists():
            return None

        last_timestamp: datetime | None = None
        with self.tsv_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                try:
                    ts = datetime.fromisoformat(row["timestamp"])
                    if last_timestamp is None or ts > last_timestamp:
                        last_timestamp = ts
                except (KeyError, ValueError):
                    continue

        # Update last_seen.txt for next time
        if last_timestamp:
            self.last_seen_path.write_text(last_timestamp.isoformat(), encoding="utf-8")

        return last_timestamp

    def update_last_seen(self, timestamp: datetime) -> None:
        """Update the last_seen.txt file with the given timestamp."""
        self.last_seen_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_seen_path.write_text(timestamp.isoformat(), encoding="utf-8")

    def aggregate_locations(self) -> Dict[str, Tuple[Location, int]]:
        """Read all visits and aggregate by city/country, summing num_unique."""
        if not self.tsv_path.exists():
            return {}

        aggregates: Dict[str, Tuple[Location, int]] = {}
        city_counts: Dict[Tuple[str | None, str], int] = defaultdict(int)

        with self.tsv_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                try:
                    raw_city = row["city"].strip()
                    city = None if raw_city == "NULL" or raw_city == "" else raw_city
                    country = row["country"].strip()
                    num_unique = int(row["num_unique"])
                    city_counts[(city, country)] += num_unique
                except (KeyError, ValueError):
                    continue

        for (city, country), total in city_counts.items():
            location = Location(city=city, country=country)
            key = location.normalized_key()
            aggregates[key] = (location, total)

        return aggregates

    def aggregate_locations_with_last_seen(
        self,
    ) -> Dict[str, Tuple[Location, int, datetime | None]]:
        """Aggregate visits by city/country, including most recent timestamp per location.

        Returns:
            Dict mapping normalized location key -> (Location, total_visits, last_timestamp)
        """
        if not self.tsv_path.exists():
            return {}

        aggregates: Dict[str, Tuple[Location, int, datetime | None]] = {}

        with self.tsv_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                try:
                    raw_city = row["city"].strip()
                    city = None if raw_city == "NULL" or raw_city == "" else raw_city
                    country = row["country"].strip()
                    num_unique = int(row["num_unique"])
                    ts = datetime.fromisoformat(row["timestamp"])
                except (KeyError, ValueError):
                    continue

                location = Location(city=city, country=country)
                key = location.normalized_key()
                if key in aggregates:
                    existing_location, total, last_ts = aggregates[key]
                    new_total = total + num_unique
                    if last_ts is None or ts > last_ts:
                        aggregates[key] = (existing_location, new_total, ts)
                    else:
                        aggregates[key] = (existing_location, new_total, last_ts)
                else:
                    aggregates[key] = (location, num_unique, ts)

        return aggregates

    def aggregate_recent_locations(self, limit: int) -> Dict[str, Tuple[Location, int]]:
        """Aggregate only the most recent N visits."""
        if not self.tsv_path.exists() or limit <= 0:
            return {}

        # Collect last N data rows (skip header)
        lines: list[str] = []
        with self.tsv_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                lines.append(line)
        if len(lines) <= 1:
            return {}
        header = lines[0].rstrip("\n")
        data_lines = lines[1:]
        recent_lines = data_lines[-limit:]

        aggregates: Dict[str, Tuple[Location, int]] = {}
        city_counts: Dict[Tuple[str | None, str], int] = defaultdict(int)

        from io import StringIO

        buffer = StringIO("\n".join([header] + recent_lines))
        reader = csv.DictReader(buffer, delimiter="\t")
        for row in reader:
            try:
                raw_city = row["city"].strip()
                city = None if raw_city == "NULL" or raw_city == "" else raw_city
                country = row["country"].strip()
                num_unique = int(row["num_unique"])
                city_counts[(city, country)] += num_unique
            except (KeyError, ValueError):
                continue

        for (city, country), total in city_counts.items():
            location = Location(city=city, country=country)
            key = location.normalized_key()
            aggregates[key] = (location, total)

        return aggregates
