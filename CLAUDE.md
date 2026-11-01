# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Early-stage ELT project: `pipeline.py` pulls trending manga from the AniList GraphQL API and loads it into Supabase Postgres with `dlt`; a dbt project in `transform/` models it into staging + marts. The installable package (`src/anilist_trends/`) is still the `uv init` stub and not wired to anything. No Python tests (only dbt data tests); `ruff` is a dev dependency with default settings (no `[tool.ruff]` config). README is empty.

## Commands

Managed with `uv` (build backend `uv_build`), Python 3.14 (pinned in `.python-version`).

```sh
uv sync                    # install deps (incl. dev group: ruff) into .venv
uv run --env-file .env python pipeline.py  # fetch trending manga and load into Postgres (hits the live API + DB)
uv run python explore.py   # print the raw AniList response shape (hits the live API)
uv run --env-file .env python page/build_page.py  # render site/index.html from the analytics marts (hits the DB)
uv run ruff check .        # lint
uv run ruff format .       # format
uv add <pkg>               # add a dependency (updates pyproject.toml + uv.lock)

# dbt (profiles.yml lives inside transform/, so point dbt at it)
cd transform
uv run dbt run --profiles-dir .                     # build all models
uv run dbt run --profiles-dir . --select stg_titles # build one model
uv run dbt test --profiles-dir .                    # run data tests (marts/schema.yml)
uv run dbt build --profiles-dir .                   # run + test in DAG order
uv run dbt debug --profiles-dir .                   # check the DB connection
```

## Architecture

Data flow: AniList API → `pipeline.py` (dlt) → `raw.titles` in Supabase Postgres → dbt (`transform/`) → `analytics` schema.

- `pipeline.py` — single `dlt` resource `titles` (function `trending_titles`). For each country `JP`/`KR`/`CN` it pages through the GraphQL query (`perPage: 50`, up to `MAX_PAGES = 4`, `sort: [TRENDING_DESC, ID]`, `type: MANGA`; `ID` is a tiebreaker so paging is stable — sort values are GraphQL enums, so uppercase), stopping early on `pageInfo.hasNextPage == false` and sleeping 2s between pages. Rows are flattened camelCase → snake_case (incl. `cover_image_url`/`cover_image_color` from `coverImage`) plus `country` and a UTC `snapshot_date` computed once per run (so a run crossing midnight stays one snapshot).
  - Pipeline: `pipeline_name="anilist"`, `destination="postgres"`, `dataset_name="raw"` → table `raw.titles`.
  - `write_disposition="merge"`, `primary_key=["id", "snapshot_date"]`, `merge_key="snapshot_date"`: a rerun on the same UTC day replaces that day's whole snapshot (titles that fell out of the trending list are removed, not left stale); each new day adds a new snapshot. This is what makes the table a daily time series.
  - Uses `dlt.sources.helpers.requests` (dlt's drop-in wrapper with built-in retries) rather than plain `requests`.
  - DuckDB is still installed (`dlt[duckdb,postgres]`) and `*.duckdb` is gitignored — leftover from the original local destination.
- `explore.py` — standalone script using plain `requests`; reference for the query format and response structure (`data.Page.media[]`).
- `transform/` — dbt project (`profile: anilist`, adapter `dbt-postgres`). `models/staging/sources.yml` declares source `raw.titles`; `stg_titles.sql` is a 1:1 rename/select (`id` → `title_id`). Staging models: no joins, no business logic. dbt writes to schema `analytics`.
  - Materialization is set per folder in `dbt_project.yml`: `staging` → view, `marts` → table. The `marts:` key must be a sibling of `staging:` (indentation matters; nesting it under `staging` silently does nothing).
  - Marts (`models/marts/`): `fct_title_daily` — one row per `(title_id, snapshot_date)` with the daily measures (popularity, trending, average_score, chapters). `dim_title` — one row per title with descriptive attributes taken from its latest snapshot (`row_number()` over `snapshot_date desc`). `fct_title_growth` — built on `fct_title_daily`; per `(title_id, snapshot_date)` it uses `LAG` to get the change in popularity since that title's previous snapshot, plus `days_between` and `popularity_per_day` (handles gaps when a title drops off and returns). A title's first snapshot has no previous row, so it is filtered out. Tests in `marts/schema.yml` cover grain uniqueness and not-null keys.
- `page/` — static "trending today" page. `top10.sql` holds the logic (top 10 per country from the latest `snapshot_date`, joining `analytics.fct_title_daily` to `analytics.dim_title`, ranked by `trending desc, popularity desc, title_id`); `build_page.py` only runs that SQL and writes `site/index.html`. It connects with `DESTINATION__POSTGRES__CREDENTIALS` and `psycopg2` (a transitive dependency via `dlt[postgres]`/`dbt-postgres`, not declared in `pyproject.toml`), and refuses to write unless it gets exactly 30 rows (10 × JP/KR/CN). `site/` is gitignored build output.
- `.github/workflows/daily_pipeline.yml` — daily at 00:30 UTC (plus manual `workflow_dispatch`): runs `pipeline.py`, then `dbt build --profiles-dir .` in `transform/` (models + tests), then `page/build_page.py`, then uploads `site/` with `actions/upload-pages-artifact` and publishes it with `actions/deploy-pages` (job has `pages: write`/`id-token: write` and the `github-pages` environment; the repo's Pages source must be "GitHub Actions"). Steps run in order, so a failed dbt test or a non-30-row result stops the deploy and the previous page stays live. Each step gets its own secrets (see Credentials).

## Credentials

- All credentials are env vars: GitHub secrets in CI; locally the gitignored root `.env` (there is no `.dlt/secrets.toml`). `.env` lines have no `export`, so `source .env` alone doesn't reach Python — load it with `uv run --env-file .env ...` (from `transform/`: `--env-file ../.env`).
- `DESTINATION__POSTGRES__CREDENTIALS` (connection string): used by dlt (`pipeline.py`) and by `page/build_page.py` (via `os.environ`).
- `SUPABASE_HOST`, `SUPABASE_USER`, `SUPABASE_PASSWORD`: read by `transform/profiles.yml` for dbt.

## Dev log

`DEVLOG.md` is the user's running log for a future portfolio blog post. Whenever `/init` is run, also update `DEVLOG.md`:
- Add a dated session entry (template at the bottom of the file) for work since the last entry — use `git log` since that date plus what happened in the current session.
- Add new decisions to the "Key decisions" table and problems/fixes to "Problems hit". Update "Open questions / next steps" (remove resolved items).
- Record facts, the reasoning behind choices, and problems hit; don't invent lessons or opinions the user didn't express. Append — don't rewrite earlier entries.

## AniList API notes

- Single GraphQL endpoint (`https://graphql.anilist.co`), no auth needed for public queries; send `{"query": ..., "variables": ...}` as JSON.
- AniList rate-limits requests (around 90/min, sometimes lowered); expect HTTP 429 with a `Retry-After` header when paginating.
- `title.english` (and other fields such as `chapters` or `averageScore`) can be `null`.
