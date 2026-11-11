# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

AniList Trends tracks which manga are trending on AniList by country of origin (JP/KR/CN) as a daily time series. Branch `databricks` is v2: a rebuild as a medallion pipeline on Databricks. The v1 code (dlt `pipeline.py` → Supabase Postgres → dbt `transform/` → GitHub Actions + Pages) was deleted from this branch in `c8bdf72` and still lives on `main`. Use `git show main:<path>` to see how v1 did something (query shape, paging, merge semantics).

Built so far: landing (`src/fetch.py`), Bronze, Silver, and the first two Gold dimensions (`dim_date`, `dim_title`), all run by one daily Job. Not built yet: the Gold facts (`fct_title_daily`, `fct_title_growth`), the page report tables, and the port of `page/`.

- `src/fetch.py`: landing ingestion. Fetches JP/KR/CN and writes raw pages to `<landing_dir>/snapshot_date=<date>/country=<CC>/run=<UTC ts>.json`. Two invariants to keep: every country is fetched before any file is written (a failure leaves the day absent, never partial), and files are opened with mode `"x"` so nothing is ever overwritten. `main(argv=None)` is there because Databricks notebook kernels inject `-f` into `sys.argv`.
- `src/pipeline/*.sql`: one Lakeflow Declarative Pipeline (SQL), each file listed under `libraries` in `databricks.yml`.
- `page/` (v1 leftover, **does not run here**): `build_page.py` imports `psycopg2`, which is no longer in the lockfile, and `top10.sql` reads `analytics.fct_title_daily`/`analytics.dim_title` from Supabase. Both need porting to Gold. `top10.sql` also uses `title_english` and `cover_image_url`, which Silver does not carry yet.
- `tests/test_fetch.py`: offline pytest tests (`tmp_path`, `monkeypatch` on `requests.post`; no network or Databricks). There are no tests for the SQL, no CI workflow, and the README is empty.

## Commands

Uses `uv` with Python 3.12 (pinned in `.python-version` and `requires-python`) to match Databricks serverless. There is no build backend or `[project.scripts]`, so the project itself is not installable. The only runtime dependency is `requests`. pytest config sets `pythonpath = ["src"]`, so tests `import fetch` directly.

```sh
uv sync                      # install deps (incl. dev group: ruff, pytest)
uv run pytest                # offline tests in tests/
uv run pytest tests/test_fetch.py::test_write_raw_refuses_to_overwrite   # single test
uv run ruff check .          # lint (default settings, no [tool.ruff] config)
uv run ruff format .

databricks bundle validate             # check databricks.yml
databricks bundle deploy               # deploy to dev (default target)
databricks bundle deploy -t prod       # deploy prod too; a change isn't live in prod until this runs
databricks bundle run daily            # run the Job on demand (fetch -> medallion); add -t prod for prod
databricks fs mkdir dbfs:/Volumes/...  # needed before `databricks fs cp` into a volume folder that doesn't exist yet
                                       # note: `databricks fs ls` prints IST times with a Z suffix
```

## Architecture (Databricks bundle)

Everything is declared in `databricks.yml`:
- Catalog `${var.catalog}` (default `anilist`). It must already exist: it was created by hand, and the bundle only creates what goes inside it.
- Targets `dev` (default, schema prefix `dev_`) and `prod` (no prefix) share the catalog but never share tables. Both use Databricks CLI profile `anilist` (OAuth, `auth_type = databricks-cli`). `.databricks/` is gitignored bundle state.
- Schemas `landing`, `bronze`, `silver`, `gold`, plus managed volume `landing.raw` (one JSON file per country per run).
- Job `daily`: task `fetch` (`spark_python_task` on `src/fetch.py`, serverless env with `requests`) then task `medallion` (the pipeline), which runs only if fetch succeeded. Scheduled 00:40 UTC, but `schedule_status` is `PAUSED` in dev and `UNPAUSED` only in prod. Emails the deploying user on failure. Job parameter `snapshot_date` defaults to the trigger date; there is no backfill, because AniList only returns today's data and a past date would stamp today's numbers as history.
- Pipeline `medallion` (serverless): its default schema is Bronze, so Bronze tables are referenced unqualified (`raw_pages`). Other layers are written and read with `${silver_schema}` / `${gold_schema}`, and Bronze reads only `${landing_path}/snapshot_date=*/country=*/run=*.json` (a stray file would fail Silver on every update); all three come from the pipeline `configuration`, so dev and prod each use their own schemas.

Data flow and grain:
- **Bronze** `raw_pages`: streaming table over `read_files(landing_path, json, multiLine)`. One row per API page (not per title), plus `source_file` and `ingested_at`. Each landing file is read once.
- **Silver** `title_daily`: materialized view, one row per `(title_id, snapshot_date)`. It explodes `data.Page.media` and takes `snapshot_date`, `country` and `run_id` from the file path with `regexp_extract`, because they are not in the API body. Reruns: the whole day comes from its newest `run_id` (so titles that dropped out between runs don't linger), plus `ROW_NUMBER` for a title repeated within one run. Expectations `ON VIOLATION FAIL UPDATE` on title_id, snapshot_date, and country.
- **Gold** `dim_date`: generated calendar 2026-10-01 to 2027-12-31, with an integer key `date_key` in `yyyymmdd` form. Extend the end date before 2028.
- **Gold** `dim_title`: SCD Type 2 on `status` only, built with gaps and islands (`LAG` change flag → running `SUM` → `LEAD` for `valid_to`). The other attributes are Type 1 via `max_by(col, snapshot_date)`. The surrogate key `title_key = xxhash64(title_id, valid_from)` is one per version row, and it is a hash rather than `ROW_NUMBER` so keys stay stable across refreshes. Current row: `is_current`, `valid_to = 9999-12-31`.
- Planned Gold facts, carried over from v1: `fct_title_daily` (popularity, trending, average_score, chapters) and `fct_title_growth` (`LAG` per title, with `days_between` because titles can drop off and come back). A title has a row only on days it is in its country's top 200; a missing row means not ranked, not zero.

## Credentials

Locally they live in a gitignored root `.env`. Its lines have no `export`, so load it with `uv run --env-file .env ...`. v1 used `DESTINATION__POSTGRES__CREDENTIALS` and `SUPABASE_*`; Databricks auth comes from the CLI profile, not `.env`.

## Dev log

`DEVLOG.md` is the user's running log for a future portfolio blog post. Whenever `/init` is run, also update `DEVLOG.md`:
- Add a dated session entry (template at the bottom of the file) for work since the last entry. Use `git log` since that date plus what happened in the current session. If `/init` is given arguments, they are the user's own session notes: put them in that entry.
- Add new decisions to the "Key decisions" table and problems/fixes to "Problems hit". Update "Open questions / next steps" (remove resolved items).
- Record facts, the reasoning behind choices, and problems hit. Don't invent lessons or opinions the user didn't express. Append; don't rewrite earlier entries, including the user's in-progress TODOs.

## Code explainer

`.archive/CODE_EXPLAINED.md` (gitignored) explains the codebase so the user can feed it to NotebookLM for slides and an audio overview. Whenever `/init` is run, also update it to match the current code:
- Cover every code file on the branch; add sections for new files and layers, and remove anything that no longer exists.
- Keep the style: one analogy per concept, then how the code implements it and why. Pitch it at a learner, but don't make it babyish.
- Keep it NotebookLM-friendly: numbered sections with one idea per heading (each becomes a slide), mostly prose (it's read aloud), very little code, no ASCII diagrams, and end with a design-principles summary.
- Mark each layer as built, next, or planned to match the current state.

## AniList API notes

- Single GraphQL endpoint `https://graphql.anilist.co`, no auth for public queries; POST `{"query": ..., "variables": ...}`. Response rows are at `data.Page.media[]`.
- v1 query: `type: MANGA`, `countryOfOrigin` per country, `perPage: 50`, up to 4 pages, `sort: [TRENDING_DESC, ID]`. `ID` is a tiebreaker so paging is stable, and sort values are uppercase GraphQL enums. It stops on `pageInfo.hasNextPage == false`.
- Rate-limited (~90/min, sometimes lower): expect HTTP 429 with `Retry-After`; v1 slept 2s between pages.
- `title.english`, `chapters` and `averageScore` can be `null` (the page falls back from English to romaji).
