# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

AniList Trends tracks which manga are trending on AniList by country of origin (JP/KR/CN) as a daily time series. Branch `databricks` is v2: a rebuild as a medallion pipeline on Databricks. The v1 code (dlt `pipeline.py` → Supabase Postgres → dbt `transform/` → GitHub Actions + Pages) was deleted from this branch in `c8bdf72` and still lives on `main`. Use `git show main:<path>` to see how v1 did something (query shape, paging, merge semantics).

What exists on this branch so far:
- `databricks.yml`: Asset Bundle that declares only Unity Catalog schemas and a volume. No jobs, notebooks or ingestion code yet.
- `page/` (v1 leftover, **does not run here**): `build_page.py` imports `psycopg2`, which is no longer in the lockfile, and `top10.sql` reads `analytics.fct_title_daily`/`analytics.dim_title` from Supabase. Both need porting to the gold layer.
- No tests, no CI workflow. README is empty.

## Commands

Uses `uv` with Python 3.14 (pinned in `.python-version`). There is no build backend or `[project.scripts]`, so the project itself is not installable. The only runtime dependency is `requests`.

```sh
uv sync                      # install deps (incl. dev group: ruff)
uv run ruff check .          # lint (default settings, no [tool.ruff] config)
uv run ruff format .

databricks bundle validate             # check databricks.yml
databricks bundle deploy               # deploy to dev (default target)
databricks bundle deploy -t prod
databricks fs mkdir dbfs:/Volumes/...  # needed before `databricks fs cp` into a volume folder that doesn't exist yet
```

## Architecture (Databricks bundle)

- Catalog `${var.catalog}` (default `anilist`). It must already exist: it was created by hand, and the bundle only creates what goes inside it.
- Medallion schemas: `landing` (raw API files exactly as received), `bronze` (raw JSON as append-only tables), `silver` (typed, deduped, one row per title per day), `gold` (Kimball star schema + page report tables).
- Managed volume `landing.raw`: one JSON file per country per run.
- Targets `dev` (default, schema prefix `dev_`) and `prod` (no prefix) share the catalog but never share tables. Both use Databricks CLI profile `anilist` (OAuth, `auth_type = databricks-cli`). `.databricks/` is gitignored bundle state.
- Intended grain, carried over from v1: one row per `(title_id, snapshot_date)`, where `snapshot_date` is UTC and computed once per run. v1 star schema: `fct_title_daily` (popularity, trending, average_score, chapters), `dim_title` (attributes from the latest snapshot), `fct_title_growth` (`LAG` per title, with `days_between` because titles can drop off and come back).

## Credentials

Locally they live in a gitignored root `.env`. Its lines have no `export`, so load it with `uv run --env-file .env ...`. v1 used `DESTINATION__POSTGRES__CREDENTIALS` and `SUPABASE_*`; Databricks auth comes from the CLI profile, not `.env`.

## Dev log

`DEVLOG.md` is the user's running log for a future portfolio blog post. Whenever `/init` is run, also update `DEVLOG.md`:
- Add a dated session entry (template at the bottom of the file) for work since the last entry. Use `git log` since that date plus what happened in the current session.
- Add new decisions to the "Key decisions" table and problems/fixes to "Problems hit". Update "Open questions / next steps" (remove resolved items).
- Record facts, the reasoning behind choices, and problems hit. Don't invent lessons or opinions the user didn't express. Append; don't rewrite earlier entries, including the user's in-progress TODOs.

## AniList API notes

- Single GraphQL endpoint `https://graphql.anilist.co`, no auth for public queries; POST `{"query": ..., "variables": ...}`. Response rows are at `data.Page.media[]`.
- v1 query: `type: MANGA`, `countryOfOrigin` per country, `perPage: 50`, up to 4 pages, `sort: [TRENDING_DESC, ID]`. `ID` is a tiebreaker so paging is stable, and sort values are uppercase GraphQL enums. It stops on `pageInfo.hasNextPage == false`.
- Rate-limited (~90/min, sometimes lower): expect HTTP 429 with `Retry-After`; v1 slept 2s between pages.
- `title.english`, `chapters` and `averageScore` can be `null` (the page falls back from English to romaji).
