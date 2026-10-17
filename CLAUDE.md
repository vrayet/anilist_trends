# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Early-stage Python project that pulls trending manga data from the AniList GraphQL API and loads it into DuckDB with `dlt`. The installable package (`src/anilist_trends/`) is still the `uv init` stub; the real code lives in two top-level scripts, `explore.py` and `pipeline.py`. No tests are set up yet; `ruff` is installed as a dev dependency with default settings (no `[tool.ruff]` config).

## Commands

Managed with `uv` (build backend `uv_build`), Python 3.14 (pinned in `.python-version`).

```sh
uv sync                    # install deps (incl. dev group: ruff) into .venv
uv run python pipeline.py  # fetch trending manga for JP/KR/CN and load into DuckDB (hits the live API)
uv run python explore.py   # print the raw AniList response shape (hits the live API)
uv run ruff check .        # lint
uv run ruff format .       # format
uv run anilist-trends      # package entry point -> anilist_trends:main (stub)
uv add <pkg>               # add a dependency (updates pyproject.toml + uv.lock)
```

## Architecture

- `pipeline.py` — the actual ingestion. A single `dlt` resource, `trending_titles`, loops over countries `JP`/`KR`/`CN`, POSTs the GraphQL query (page 1, `perPage: 10`, `sort: TRENDING_DESC`, `type: MANGA`), and yields flattened rows (camelCase API fields → snake_case columns, plus `country` and a UTC `snapshot_date`).
  - The pipeline is `pipeline_name="anilist"`, `destination="duckdb"`, `dataset_name="raw"`, so data lands in table `raw.titles` in `anilist.duckdb` in the working directory (gitignored).
  - `write_disposition="merge"` with `primary_key=["id", "snapshot_date"]`: rerunning on the same UTC day upserts; each new day adds a new snapshot row per title. This is what makes the table a daily time series of trends.
  - Uses `dlt.sources.helpers.requests` (dlt's drop-in wrapper with built-in retries) rather than plain `requests`.
- `explore.py` — standalone exploration script using plain `requests`; reference for the query format and response structure (`data.Page.media[]`).
- `src/anilist_trends/__init__.py` — package root; `main()` is the console-script entry point in `[project.scripts]`. Not yet wired to the pipeline.
- dlt secrets go in `.dlt/secrets.toml` (gitignored); none are needed currently.

## AniList API notes

- Single GraphQL endpoint (`https://graphql.anilist.co`), no auth needed for public queries; send `{"query": ..., "variables": ...}` as JSON.
- AniList rate-limits requests (around 90/min, sometimes lowered); expect HTTP 429 with a `Retry-After` header when paginating.
- `title.english` (and other fields such as `chapters` or `averageScore`) can be `null`.
