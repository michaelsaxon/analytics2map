# analytics2map

Convert Google Analytics and Clustrmaps visitor telemetry into self-hosted SVG
visitor maps that you can embed anywhere.

## Features

- Pull incremental visitor stats from the Google Analytics Data API (GA4)
- Look up city coordinates on-demand via the `geonamescache` dataset
- Store visits in a simple append-only TSV file (`data/visits.tsv`)
- Import legacy Clustrmaps text dumps with date markers to backfill historical data
- Render multi-scale SVG maps with aggregated hotspots sized logarithmically by unique visitor count

## Getting started

```bash
uv venv          # or python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Cartopy depends on GEOS/Proj libraries. On macOS you can install them with `brew install geos proj`.

Copy `config/example.yml` and fill in your environment-specific values:

```bash
cp config/example.yml config/prod.yml
```

### Required inputs

- **Google Analytics service account** with access to your GA4 property
- Optional **Clustrmaps text dump** for seeding historical visits

## Workflow

The workflow is simple: initialize your `visits.tsv` with historical data, then periodically ingest new GA4 events.

### 1. Initialize with historical data (first time only)

If you have Clustrmaps data, import it first:

```bash
analytics2map ingest-clustrmaps \
    --config-path config/prod.yml \
    --text-path clustrdump.txt
```

This parses the text dump (which should have date markers like `====== YYYY-MM-DD`), extracts city/country/uniques per period, and writes directly to `data/visits.tsv`. Each record includes the dump date as the timestamp and the number of unique visitors for that city/country.

### 2. Ingest Google Analytics events

```bash
analytics2map ingest-ga --config-path config/prod.yml
```

This fetches new events since the last timestamp in `visits.tsv` (or `data/last_seen.txt`), appends each event as a row with `num_unique=1`, and updates the last-seen timestamp.

### 3. Render SVG visitor maps

```bash
analytics2map render --config-path config/prod.yml
```

The renderer reads all rows from `visits.tsv`, groups by `(city, country)`, sums `num_unique`, and renders SVG files for every configured scale to `renderer.output_dir` (default `output/`).

## Data format

The `visits.tsv` file is a simple tab-separated log:

```
city	country	timestamp	num_unique
Lanzhou	China	2025-11-15T16:00:00	1
Singapore	Singapore	2025-11-15T16:00:00	1
Milan	Italy	2025-11-15T16:00:00	1
```

- `city`: City name (empty for country-only aggregates)
- `country`: Country name
- `timestamp`: ISO format datetime
- `num_unique`: Integer (always 1 for GA4 events, can be >1 for Clustrmaps aggregates)

## Project roadmap

- [ ] Improve city-name normalization for geonames lookups
- [ ] Add automated tests and CI
- [ ] Support additional render themes (dark/light)
- [ ] Publish Docker image for scheduled ingests
