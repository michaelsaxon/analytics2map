from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .clustrmaps import (
    export_clustrmaps_summary,
    load_clustrmaps_csv,
    load_clustrmaps_summary_csv,
    load_clustrmaps_text,
)
from .config import AppConfig
from .ga_client import GoogleAnalyticsClient
from .persistence import VisitorDatabase
from .renderer.map_renderer import MapRenderer
from .schemas import Source

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
    """Fetch new Google Analytics events and store them in the visitor DB."""
    _setup_logging(verbose)
    config = AppConfig.load(config_path)

    db = VisitorDatabase(config.database.path)
    db.initialize()
    last_seen = db.last_seen_at(Source.GOOGLE_ANALYTICS)

    client = GoogleAnalyticsClient(config.google_analytics)
    events = client.fetch_events(since=last_seen)

    inserted = db.record_events(events)
    if events:
        newest = max(event.occurred_at for event in events)
        db.update_last_seen(Source.GOOGLE_ANALYTICS, newest)

    console.print(f"Ingested {inserted} Google Analytics events.")


@app.command("ingest-clustrmaps")
def ingest_clustrmaps(
    csv_path: Optional[Path] = typer.Option(None, exists=True, help="Path to Clustrmaps export CSV"),
    text_path: Optional[Path] = typer.Option(None, exists=True, help="Path to Clustrmaps text dump"),
    config_path: Path = typer.Option(..., exists=True),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Import historical Clustrmaps data."""
    _setup_logging(verbose)
    config = AppConfig.load(config_path)

    if csv_path and text_path:
        raise typer.BadParameter("Provide only one of --csv-path or --text-path")

    data_path = text_path or csv_path
    if not data_path:
        data_path = config.clustrmaps.csv_path
    if not data_path:
        raise typer.BadParameter("Clustrmaps data path must be provided")

    path = Path(data_path)
    if text_path or path.suffix.lower() in {".txt", ".md"}:
        events = list(load_clustrmaps_text(path))
    else:
        events = list(load_clustrmaps_csv(path))
    db = VisitorDatabase(config.database.path)
    db.initialize()
    inserted = db.record_events(events)
    newest = max(event.occurred_at for event in events)
    db.update_last_seen(Source.CLUSTRMAPS, newest)

    console.print(f"Ingested {inserted} Clustrmaps events from {data_path}.")


@app.command("render")
def render_maps(
    config_path: Path = typer.Option(..., exists=True),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Render SVG visitor maps for all configured scales."""
    _setup_logging(verbose)
    config = AppConfig.load(config_path)

    db = VisitorDatabase(config.database.path)
    db.initialize()
    aggregates = db.aggregate_locations()
    overlay_path = config.renderer.clustrmaps_overlay_path
    if overlay_path and Path(overlay_path).exists():
        overlay = load_clustrmaps_summary_csv(overlay_path)
        for key, (location, count) in overlay.items():
            if key in aggregates:
                existing_location, existing_count = aggregates[key]
                aggregates[key] = (existing_location, existing_count + count)
            else:
                aggregates[key] = (location, count)

    renderer = MapRenderer(config.renderer)
    renderer.render(aggregates)
    console.print(f"Rendered {len(config.renderer.scales)} map variants to {config.renderer.output_dir}.")


@app.command("clustrmaps-summary")
def clustrmaps_summary(
    text_path: Path = typer.Argument(..., exists=True, help="Path to Clustrmaps text dump"),
    output_path: Path = typer.Option(
        Path("data/clustrmaps_summary.csv"),
        "--output",
        "-o",
        help="Where to write the summarized CSV",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Parse a Clustrmaps text dump and write city-level unique visitor counts to CSV."""
    _setup_logging(verbose)
    export_clustrmaps_summary(text_path, output_path)
    console.print(f"Wrote Clustrmaps summary to {output_path}")


if __name__ == "__main__":
    app()

