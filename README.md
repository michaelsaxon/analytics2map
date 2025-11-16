# analytics2map

Convert Google Analytics and Clustrmaps visitor telemetry into self-hosted SVG
visitor maps that you can embed anywhere. All you have to do is fork it and do a little setup!

## Features

- Pull incremental visitor stats from the Google Analytics Data API (GA4)
- Look up city coordinates on-demand via the `geonamescache` dataset
- Store visits in a simple append-only TSV file (`data/visits.tsv`)
- Import legacy Clustrmaps text dumps with date markers to backfill historical data
- Render multi-scale SVG maps with aggregated hotspots sized logarithmically by unique visitor count

## Getting started

```bash
# set up your virtual environment of choice
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

### Getting

## Workflow

The workflow is simple: initialize your `visits.tsv` with historical data, then periodically ingest new GA4 events.

### 0. [Optional] Initialize with historical data (first time only)

If you aren't planning to initialize with previous data, skip to 1

If you have Clustrmaps data, import it first:

```bash
analytics2map ingest-clustrmaps \
    --config-path config/prod.yml \
    --text-path clustrdump.txt
```

This parses the text dump (which should have date markers like `====== YYYY-MM-DD`), extracts city/country/uniques per period, and writes directly to `data/visits.tsv`. Each record includes the dump date as the timestamp and the number of unique visitors for that city/country.

### 1. Ingest Google Analytics events

Find your `property_id` for your project from the Google Analytics dashboard. This will be a many-digit number. 
Put your GCP json credential file at the path you specify with the `credentials_path` key in the YAML config.

For ease of integration with github actions I store my key at `secret.json`. Doing this will make your script work with the existing `update-map` workflow.

> [WARNING]
> `secret.json` **is a magic filename which is included in .gitignore. Do not add keys under any other filename (or if you do, put them in .gitignore). This is very important to avoid committing your keys.**

```bash
analytics2map ingest-ga --config-path config/prod.yml
```

This fetches new events since the last timestamp in `visits.tsv` (or `data/last_seen.txt`), appends each event as a row with `num_unique=1`, and updates the last-seen timestamp.

### 2. Render SVG visitor maps

```bash
analytics2map render --config-path config/prod.yml
```

The renderer reads all rows from `visits.tsv`, groups by `(city, country)`, sums `num_unique`, and renders SVG files for every configured scale to `renderer.output_dir` (default `output/`).

### [Optional] Automation with Github actions and Github pages

If you set up this repo as a Github pages project (in settings) it will appear at `yourusername.github.io/analytics2map/`.
You can then use the path `https://yourusername.github.io/analytics2map/output/visitors-small.svg` in any of your projects to get the page.

To have the map update automatically, you can enable the `update-map` action in your Github actions settings. The config is in `/.github/workflows/update-map.yaml`.
It is currently set to run every hour. To change this, update the cron job lines:

```yaml
on:
  schedule:
    - cron: '0 * * * *' # On the top of the hour
```

`cron: '0 0 * * *` will run once a day at midnight for example.

## Data format

The `visits.tsv` file is a simple tab-separated log:

```
timestamp           country         city        num_unique
2025-11-15T14:05:00	United States	Seattle	    1
2025-11-15T14:14:00	United States	Chapel Hill	2
2025-11-15T14:25:00	United States	Chicago	    1
2025-11-15T14:25:00	China	        Lanzhou     1
2025-11-15T14:25:00	Singapore	    Singapore   1
```

- `timestamp`: ISO format datetime
- `country`: Country name
- `city`: City name (empty for country-only aggregates)
- `num_unique`: Integer (always 1 for GA4 events, can be >1 for Clustrmaps aggregates)

## Project roadmap

- [ ] Improve city-name normalization for geonames lookups
- [ ] Support additional render themes (dark/light)
- [ ] Render to d3js
