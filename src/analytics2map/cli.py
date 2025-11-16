from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .clustrmaps import ingest_clustrmaps_dump_to_tsv
from .config import AppConfig
from .ga_client import GoogleAnalyticsClient
from .persistence import VisitStore
from .renderer.map_renderer import MapRenderer
from .renderer.interactive_globe_renderer import InteractiveGlobeRenderer
from .renderer.interactive_map_renderer import InteractiveMapRenderer

app = typer.Typer(add_completion=False, help="analytics2map command line interface")
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


@app.command("ingest-ga")
def ingest_ga(
    config_path: Path = typer.Option(..., exists=True, help="Path to YAML config"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Fetch new Google Analytics events and append them to visits.tsv."""
    _setup_logging(verbose)
    config = AppConfig.load(config_path)

    store = VisitStore(config.database.path)
    last_seen = store.get_last_timestamp()

    if verbose:
        console.print(f"Last seen: {last_seen}")

    client = GoogleAnalyticsClient(config.google_analytics)
    events = client.fetch_events(since=last_seen)

    # Ensure oldest-first order before appending to the TSV log
    events = sorted(events, key=lambda e: e.occurred_at)

    if verbose:
        console.print(f"Found {len(events)} events")
        for idx, event in enumerate(events):
            if event.location:
                location = event.location
                console.print(f"Event {idx} location: {location}")
            else:
                console.print(f"Event {idx} location: none")
            if event.occurred_at:
                console.print(f"Event {idx} occurred at: {event.occurred_at}")
            else:
                console.print(f"Event {idx} occurred at: none")

    written = 0
    newest: datetime | None = None
    for event in events:
        timestamp = event.occurred_at
        if event.occurred_at <= last_seen:
            continue

        city = event.location.city if event.location else None
        if city and city.strip().lower() == "(not set)":
            city = None
        store.append_visit(
            city=city,
            country=event.location.country or "Unknown",
            timestamp=timestamp,
            num_unique=1,
        )
        written += 1
        if newest is None or event.occurred_at > newest:
            newest = event.occurred_at

    if newest:
        store.update_last_seen(newest)

    console.print(f"Ingested {written} Google Analytics events.")


@app.command("ingest-clustrmaps")
def ingest_clustrmaps(
    text_path: Path = typer.Option(..., exists=True, help="Path to Clustrmaps text dump"),
    config_path: Path = typer.Option(..., exists=True),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Import historical Clustrmaps data from text dump into visits.tsv."""
    _setup_logging(verbose)
    config = AppConfig.load(config_path)

    store = VisitStore(config.database.path)
    written = ingest_clustrmaps_dump_to_tsv(text_path, store)

    console.print(f"Ingested {written} Clustrmaps records from {text_path}.")


@app.command("render")
def render_maps(
    config_path: Path = typer.Option(..., exists=True),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Render SVG visitor maps for all configured scales."""
    _setup_logging(verbose)
    config = AppConfig.load(config_path)

    store = VisitStore(config.database.path)
    aggregates = store.aggregate_locations()

    recent: Dict[str, Tuple[Location, int]] | None = None
    if config.renderer.most_recent_visits:
        from .schemas import Location  # local import to avoid cycles at module import time

        recent = store.aggregate_recent_locations(config.renderer.most_recent_visits)

    renderer = MapRenderer(config.renderer)
    renderer.render(aggregates, recent)
    console.print(f"Rendered {len(config.renderer.scales)} map variants to {config.renderer.output_dir}.")


@app.command("render-interactive")
def render_interactive_map(
    config_path: Path = typer.Option(..., exists=True),
    output_html: Optional[Path] = typer.Option(
        None,
        "--output-html",
        "-o",
        help="Path for the interactive HTML map output (defaults to output/visitors-interactive.html)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Render an interactive D3.js visitor map as a standalone HTML file."""
    _setup_logging(verbose)
    config = AppConfig.load(config_path)

    store = VisitStore(config.database.path)
    aggregates = store.aggregate_locations_with_last_seen()

    renderer = InteractiveMapRenderer(config.renderer)
    output_path = renderer.render(aggregates, output_html)
    console.print(f"Rendered interactive map to {output_path}")


@app.command("render-globe")
def render_globe(
    config_path: Path = typer.Option(..., exists=True),
    output_html: Optional[Path] = typer.Option(
        None,
        "--output-html",
        "-o",
        help="Path for the globe HTML output (defaults to output/visitors-globe.html)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Render a rotating 3D globe visualization as a standalone HTML file."""
    _setup_logging(verbose)
    config = AppConfig.load(config_path)

    store = VisitStore(config.database.path)
    aggregates = store.aggregate_locations_with_last_seen()

    renderer = InteractiveGlobeRenderer(config.renderer)
    output_path = renderer.render(aggregates, output_html)
    console.print(f"Rendered rotating globe to {output_path}")


if __name__ == "__main__":
    app()

