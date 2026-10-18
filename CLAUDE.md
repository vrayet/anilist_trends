# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Early-stage ELT project: `pipeline.py` pulls trending manga from the AniList GraphQL API and loads it into Supabase Postgres with `dlt`; a dbt project in `transform/` models it. The installable package (`src/anilist_trends/`) is still the `uv init` stub and not wired to anything. No tests yet; `ruff` is a dev dependency with default settings (no `[tool.ruff]` config). README is empty.

## Commands

Managed with `uv` (build backend `uv_build`), Python 3.14 (pinned in `.python-version`).

```sh
uv sync                    # install deps (incl. dev group: ruff) into .venv
uv run python pipeline.py  # fetch trending manga and load into Postgres (hits the live API + DB)
uv run python explore.py   # print the raw AniList response shape (hits the live API)
uv run ruff check .        # lint
uv run ruff format .       # format
uv add <pkg>               # add a dependency (updates pyproject.toml + uv.lock)

# dbt (profiles.yml lives inside transform/, so point dbt at it)
cd transform
uv run dbt run --profiles-dir .                     # build all models
uv run dbt run --profiles-dir . --select stg_titles # build one model
uv run dbt debug --profiles-dir .                   # check the DB connection
```

## Architecture

Data flow: AniList API → `pipeline.py` (dlt) → `raw.titles` in Supabase Postgres → dbt (`transform/`) → `analytics` schema.

- `pipeline.py` — single `dlt` resource `titles` (function `trending_titles`). For each country `JP`/`KR`/`CN` it pages through the GraphQL query (`perPage: 50`, up to `MAX_PAGES = 4`, `sort: TRENDING_DESC`, `type: MANGA`), stopping early on `pageInfo.hasNextPage == false` and sleeping 2s between pages. Rows are flattened camelCase → snake_case (incl. `cover_image_url`/`cover_image_color` from `coverImage`) plus `country` and a UTC `snapshot_date`.
  - Pipeline: `pipeline_name="anilist"`, `destination="postgres"`, `dataset_name="raw"` → table `raw.titles`.
  - `write_disposition="merge"`, `primary_key=["id", "snapshot_date"]`, `merge_key="snapshot_date"`: a rerun on the same UTC day replaces that day's whole snapshot (titles that fell out of the trending list are removed, not left stale); each new day adds a new snapshot. This is what makes the table a daily time series.
  - Uses `dlt.sources.helpers.requests` (dlt's drop-in wrapper with built-in retries) rather than plain `requests`.
  - DuckDB is still installed (`dlt[duckdb,postgres]`) and `*.duckdb` is gitignored — leftover from the original local destination.
- `explore.py` — standalone script using plain `requests`; reference for the query format and response structure (`data.Page.media[]`).
- `transform/` — dbt project (`profile: anilist`, adapter `dbt-postgres`). `models/staging/sources.yml` declares source `raw.titles`; `stg_titles.sql` is a 1:1 rename/select (`id` → `title_id`), materialized as a view. Staging models: no joins, no business logic. dbt writes to schema `analytics`.
- `.github/workflows/daily_pipeline.yml` — runs `pipeline.py` daily at 00:30 UTC (plus manual `workflow_dispatch`). Only the dlt load runs in CI; dbt does not.

## Credentials

- dlt: `DESTINATION__POSTGRES__CREDENTIALS` (connection string) — env var in CI (GitHub secret), or `.dlt/secrets.toml` locally (gitignored).
- dbt: `transform/profiles.yml` reads `SUPABASE_HOST`, `SUPABASE_USER`, `SUPABASE_PASSWORD` from the environment (`.env` is gitignored).

## Dev log

`DEVLOG.md` is the user's running log for a future portfolio blog post. Whenever `/init` is run, also update `DEVLOG.md`:
- Add a dated session entry (template at the bottom of the file) for work since the last entry — use `git log` since that date plus what happened in the current session.
- Add new decisions to the "Key decisions" table and problems/fixes to "Problems hit". Update "Open questions / next steps" (remove resolved items).
- Record facts, the reasoning behind choices, and problems hit; don't invent lessons or opinions the user didn't express. Append — don't rewrite earlier entries.

## AniList API notes

- Single GraphQL endpoint (`https://graphql.anilist.co`), no auth needed for public queries; send `{"query": ..., "variables": ...}` as JSON.
- AniList rate-limits requests (around 90/min, sometimes lowered); expect HTTP 429 with a `Retry-After` header when paginating.
- `title.english` (and other fields such as `chapters` or `averageScore`) can be `null`.
