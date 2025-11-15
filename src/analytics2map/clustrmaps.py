from __future__ import annotations

import csv
import re
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .schemas import Location, Source, VisitorEvent

UNKNOWN_CITY_TOKENS = {"unknown location", "(not set)", "unknown", "-", "unspecified"}


def load_clustrmaps_csv(path: Path) -> Iterable[VisitorEvent]:
    events: List[VisitorEvent] = []
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            visits = int(row.get("visits", 1))
            events.extend(
                _generate_events(
                    country=row.get("country", "Unknown"),
                    city=_clean_city(row.get("city")),
                    region=row.get("region"),
                    visits=visits,
                    occurred_at=_parse_datetime(row.get("occurred_at")),
                    metadata={"raw": row},
                    latitude=_parse_float(row.get("latitude")),
                    longitude=_parse_float(row.get("longitude")),
                )
            )
    return events


def load_clustrmaps_text(path: Path, label: Optional[str] = None) -> Iterable[VisitorEvent]:
    raw = path.read_text(encoding="utf-8")
    return parse_clustrmaps_text(raw, period_label=label or path.name)


def parse_clustrmaps_text(raw: str, period_label: Optional[str] = None) -> List[VisitorEvent]:
    events: List[VisitorEvent] = []
    current_country: Optional[str] = None
    reported_visits: Optional[int] = None
    city_visit_accumulator = 0

    def flush_country_residual() -> None:
        nonlocal city_visit_accumulator, reported_visits, current_country
        if current_country and reported_visits and reported_visits > city_visit_accumulator:
            residual = reported_visits - city_visit_accumulator
            events.extend(
                _generate_events(
                    country=current_country,
                    city=None,
                    region=None,
                    visits=residual,
                    occurred_at=datetime.utcnow(),
                    metadata={
                        "source": "clustrmaps_text_country_summary",
                        "reported_visits": reported_visits,
                        "period": period_label,
                    },
                )
            )
        city_visit_accumulator = 0
        reported_visits = None

    for line in raw.splitlines():
        if not line.strip():
            continue
        tokens = [tok.strip() for tok in re.split(r"\t+", line) if tok.strip()]
        if not tokens:
            continue
        first_token = tokens[0].lower()
        if first_token.startswith("======"):
            if current_country:
                flush_country_residual()
            current_country = None
            continue
        if first_token in {"country", "locations"} or first_token.startswith("top "):
            continue
        if not line.startswith("\t"):
            # starting a new country summary
            if current_country:
                flush_country_residual()
            current_country = tokens[0]
            reported_visits = _first_int(tokens[1:])
            continue

        # city-level entry
        if current_country is None:
            continue  # skip unexpected entries
        city_raw = tokens[0]
        visits = _first_int(tokens[1:2]) or 0
        uniques = _first_int(tokens[2:3])
        visit_depth = _first_float(tokens[3:4])
        last_visit = tokens[4] if len(tokens) > 4 else None
        city, region = _split_city_region(city_raw)
        events.extend(
            _generate_events(
                country=current_country,
                city=city,
                region=region,
                visits=visits,
                occurred_at=datetime.utcnow(),
                metadata={
                    "source": "clustrmaps_text",
                    "uniques": uniques,
                    "visit_depth": visit_depth,
                    "last_visit": last_visit,
                    "period": period_label,
                },
            )
        )
        city_visit_accumulator += visits

    if current_country:
        flush_country_residual()

    return events


def summarize_clustrmaps_text(path: Path) -> Dict[Tuple[str, Optional[str], Optional[str]], int]:
    raw = path.read_text(encoding="utf-8")
    return summarize_clustrmaps_string(raw)


def summarize_clustrmaps_string(raw: str) -> Dict[Tuple[str, Optional[str], Optional[str]], int]:
    counts: Dict[Tuple[str, Optional[str], Optional[str]], int] = defaultdict(int)
    current_country: Optional[str] = None
    country_total_uniques: int = 0
    city_unique_accumulator: int = 0

    def flush_country_residual() -> None:
        nonlocal city_unique_accumulator, country_total_uniques, current_country
        if current_country and country_total_uniques > city_unique_accumulator:
            residual = country_total_uniques - city_unique_accumulator
            key = (current_country, None, None)
            counts[key] += residual
        city_unique_accumulator = 0
        country_total_uniques = 0

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("======"):
            if current_country:
                flush_country_residual()
            current_country = None
            continue
        parts = [part.strip() for part in line.split("\t")]
        if not parts or parts[0].lower() in {"country", "top locations", "top 10 locations"}:
            continue
        if not line.startswith("\t"):
            if current_country:
                flush_country_residual()
            current_country = parts[0]
            uniques = _parse_int_safe(parts[3] if len(parts) > 3 else "")
            country_total_uniques = uniques or 0
            continue

        if current_country is None:
            continue
        city_entry = parts[1] if len(parts) > 1 else ""
        uniques_value = _parse_int_safe(parts[3] if len(parts) > 3 else "") or 0
        if uniques_value <= 0:
            continue
        city, region = _split_city_region(city_entry)
        key = (current_country, city, region)
        counts[key] += uniques_value
        city_unique_accumulator += uniques_value

    if current_country:
        flush_country_residual()

    return counts


def export_clustrmaps_summary(text_path: Path, output_path: Path) -> None:
    counts = summarize_clustrmaps_text(text_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["country", "city", "region", "uniques"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for (country, city, region), uniques in sorted(
            counts.items(), key=lambda item: (item[0][0], item[0][1] or "")
        ):
            writer.writerow(
                {
                    "country": country,
                    "city": city or "",
                    "region": region or "",
                    "uniques": uniques,
                }
            )


def load_clustrmaps_summary_csv(path: Path) -> Dict[str, Tuple[Location, int]]:
    aggregates: Dict[str, Tuple[Location, int]] = {}
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            uniques = _parse_int_safe(row.get("uniques", "0")) or 0
            if uniques <= 0:
                continue
            location = Location(
                city=_clean_city(row.get("city")),
                region=row.get("region") or None,
                country=row.get("country") or "Unknown",
            )
            key = location.normalized_key()
            if key in aggregates:
                existing_location, count = aggregates[key]
                aggregates[key] = (existing_location, count + uniques)
            else:
                aggregates[key] = (location, uniques)
    return aggregates


def _generate_events(
    *,
    country: str,
    city: Optional[str],
    region: Optional[str],
    visits: int,
    occurred_at: Optional[datetime],
    metadata: Optional[Dict],
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> List[VisitorEvent]:
    """Expand a visit count into individual VisitorEvent rows."""
    if visits <= 0:
        return []
    timestamp = occurred_at or datetime.utcnow()
    city_clean = _clean_city(city)
    base_slug = _slugify(f"{country}-{city_clean or 'unspecified'}")
    visitor_id = f"clustrmaps-{base_slug}"
    events = []
    for _ in range(visits):
        visit_id = f"{visitor_id}-{uuid.uuid4().hex[:10]}"
        events.append(
            VisitorEvent(
                source=Source.CLUSTRMAPS,
                visitor_id=visitor_id,
                visit_id=visit_id,
                occurred_at=timestamp,
                location=Location(
                    city=city_clean,
                    region=region,
                    country=country,
                    latitude=latitude,
                    longitude=longitude,
                ),
                metadata=metadata or {},
            )
        )
    return events


def _split_city_region(raw: str) -> Tuple[Optional[str], Optional[str]]:
    city = raw.strip()
    region = None
    if "," in city:
        city_part, region_part = city.split(",", 1)
        city = city_part.strip()
        region = region_part.strip() or None
    normalized = _clean_city(city)
    return normalized, region


def _clean_city(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip()
    if normalized.lower() in UNKNOWN_CITY_TOKENS:
        return None
    return normalized


def _first_int(candidates: Iterable[str]) -> Optional[int]:
    for token in candidates:
        match = re.search(r"\d+", token.replace(",", ""))
        if match:
            try:
                return int(match.group())
            except ValueError:
                continue
    return None


def _first_float(candidates: Iterable[str]) -> Optional[float]:
    for token in candidates:
        match = re.search(r"\d+(?:\.\d+)?", token.replace(",", ""))
        if match:
            try:
                return float(match.group())
            except ValueError:
                continue
    return None


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower())
    slug = slug.strip("-")
    return slug or "unknown"


def _parse_int_safe(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    digits = re.findall(r"-?\d+", value.replace(",", ""))
    if not digits:
        return None
    try:
        return int(digits[0])
    except ValueError:
        return None

