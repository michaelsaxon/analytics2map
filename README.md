# analytics2map

Convert Google Analytics and Clustrmaps visitor telemetry into self-hosted SVG
visitor maps that you can embed anywhere.

## Features

- Pull incremental visitor stats from the Google Analytics Data API (GA4)
- Look up city coordinates on-demand via the `geonamescache` dataset
- Store visits locally in SQLite for reproducible rendering
- Import legacy Clustrmaps CSV exports to backfill historical data
- Render multi-scale SVG maps with aggregated hotspots sized and labeled by volume

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
- Optional **Clustrmaps CSV export** for seeding historical visits

## Workflow

1. **Ingest Google Analytics events**

   ```bash
   analytics2map ingest-ga --config-path config/prod.yml
   ```

   The CLI remembers the last ingested timestamp per source to avoid duplicate pulls.

2. **Import historic Clustrmaps data (once)**

   ```bash
   # CSV export
   analytics2map ingest-clustrmaps --config-path config/prod.yml --csv-path data/clustrmaps.csv

   # or paste the dashboard dump into a text file and parse it directly
   analytics2map ingest-clustrmaps --config-path config/prod.yml --text-path data/clustrmaps.txt
   ```

   The text parser understands the “Country / Top locations” blocks shown in the Clustrmaps UI. Any
   entries such as “Unknown location” are grouped into a country-level bucket and rendered using the
   country centroid.

   Alternatively, you can build a summarized CSV of unique visitors per city without inserting rows
   into the SQLite DB:

   ```bash
   analytics2map clustrmaps-summary clustrdump.txt --output data/clustrmaps_summary.csv
   ```

   Point `renderer.clustrmaps_overlay_path` at the generated CSV to overlay the historical counts
   when rendering.
3. **Render SVG visitor maps**

   ```bash
   analytics2map render --config-path config/prod.yml
   ```

   SVG files for every configured scale end up in `renderer.output_dir` (default `output/`).

## Project roadmap

- [ ] Improve city-name normalization for geonames lookups
- [ ] Add automated tests and CI
- [ ] Support additional render themes (dark/light)
- [ ] Publish Docker image for scheduled ingests
