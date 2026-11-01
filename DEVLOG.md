# AniList Trends — Dev Log

Raw notes for a portfolio blog post once the project is done. Newest session at the bottom.

**Goal:** track which manga are trending on AniList, by country of origin (JP/KR/CN), as a daily time series.
**Stack:** Python 3.14 · uv · dlt · Supabase Postgres · dbt · GitHub Actions · ruff

---

## Key decisions (running list)

| Decision | Why | Date |
|---|---|---|
| dlt for ingestion instead of hand-rolled inserts | Schema inference, merge/upsert, and retrying HTTP client built in | 2026-10-15 |
| Composite key `(id, snapshot_date)` | One row per title per day turns a "current trending" API into a time series | 2026-10-15 |
| DuckDB → Supabase Postgres | Needed a hosted DB the scheduled job could write to (local DuckDB file can't live in CI) | 2026-10-17 |
| GitHub Actions cron for scheduling | Free, lives next to the code, no server to run | 2026-10-17 |
| `merge_key="snapshot_date"` | Rerunning on the same day replaces that day's whole snapshot, so titles that dropped off don't linger | 2026-10-17 |
| dbt for transforms, staging layer first | Keep raw data untouched; staging models only rename/clean, no business logic | 2026-10-17 |
| Secondary sort `ID` after `TRENDING_DESC` | Ties in trending score could shuffle between pages (duplicates/misses); a unique tiebreaker makes paging stable | 2026-10-18 |
| `snapshot_date` computed once per run | A run crossing midnight UTC would otherwise split into two snapshots | 2026-10-18 |
| Star-schema marts: `fct_title_daily` + `dim_title` | Separate the daily measurements (fact, grain title × day) from descriptive attributes (dimension, one row per title) | 2026-10-24 |
| `dim_title` attributes from the latest snapshot | Titles/status/cover can change over time; latest value via `row_number()` over `snapshot_date desc` | 2026-10-24 |
| Marts as tables, staging as views | Configured per folder in `dbt_project.yml` | 2026-10-24 |
| `dbt build` as a CI step after the dlt load | Marts stay in sync with each day's snapshot, and data tests run every day | 2026-10-27 |
| `fct_title_growth` uses `LAG` over the title's previous snapshot, plus `days_between` | Titles can drop out of trending and return, so "previous snapshot" isn't always yesterday; `popularity_per_day` normalises for the gap | 2026-10-29 |
| Databricks bundle with a schema `prefix` variable per target (`dev_` / none) | Dev and prod never share tables | 2026-11-01 |

## Problems hit & how they were solved

- **Sort enum casing:** `sort: [TRENDING_DESC, id]` was wrong — GraphQL enum values are uppercase, so it's `ID`. (2026-10-24)
- **Marts built as views, not tables:** the `marts:` block in `dbt_project.yml` was indented under `staging:`, so its `+materialized: table` never applied. Unindented it to be a sibling of `staging:`. (2026-10-26)
- **Fact model in the wrong folder:** `fct_title_daily.sql` was created in `models/staging/`, so it picked up staging config; moved to `models/marts/`. (2026-10-26)
- **`dim_title` had the fact's columns:** its final `select` was copied from the fact model (measures instead of attributes); fixed to select title, country, status and cover fields. (2026-10-26)
- **dbt `.user.yml`:** dbt generates a per-user `transform/.user.yml`; added to `transform/.gitignore`. (2026-10-26)
- **`.user.yml` ignore never matched:** `transform/.gitignore` had `transform/.user.yml`, but nested `.gitignore` paths are relative to their own folder, so it pointed at `transform/transform/.user.yml`. Changed it to `.user.yml` and untracked the file with `git rm --cached`. (2026-11-01)
- **`databricks fs cp` into a volume failed:** the target folder didn't exist yet; create it with `databricks fs mkdir` first. (2026-11-01)
- **Page script couldn't import `psycopg2`:** ran it with the system `/bin/python` instead of the project venv; `uv run python ...` uses `.venv`. (2026-11-01)
- **Page script `KeyError` on `DESTINATION__POSTGRES__CREDENTIALS`:** the credentials live in `.env`, which nothing loads automatically (and its lines have no `export`, so `source .env` isn't enough). Fixed with `uv run --env-file .env ...`. (2026-11-01)

## Open questions / next steps

- Growth for other measures (e.g. `trending`, `average_score`); so far `fct_title_growth` only covers popularity.

---

## Sessions

### 2026-10-15 — Exploring the API and first pipeline
- Explored the AniList GraphQL API with a plain `requests` script (`explore.py`) to learn the response shape (`data.Page.media[]`).
- Built `pipeline.py`: a single dlt resource looping over JP/KR/CN, flattening camelCase API fields into snake_case columns plus `country` and `snapshot_date`.
- Loaded into local DuckDB with `write_disposition="merge"`.
- Added ruff for linting/formatting.

### 2026-10-17 — Going to the cloud, scheduling, and dbt
- Switched the destination from DuckDB to Supabase Postgres (`raw.titles`).
- Added a GitHub Actions workflow to run the pipeline daily at 00:30 UTC (06:00 IST), with credentials in a repo secret.
- Expanded fetching: 50 per page, up to 4 pages per country, stopping on `hasNextPage`, 2s delay between pages for AniList's rate limit.
- Added cover image URL and colour columns.
- Added `merge_key="snapshot_date"` so same-day reruns replace the day's snapshot.
- Set up a dbt project in `transform/` with source `raw.titles` and the first staging model `stg_titles` (view in `analytics`).
- Refreshed `CLAUDE.md` and started this dev log.

### 2026-10-18 — Stable paging
- Changed the query sort to `[TRENDING_DESC, id]` to add a tiebreaker so pages don't overlap or skip titles.
- Moved `snapshot_date` out of the per-row dict so it is computed once per run.
- Updated `CLAUDE.md` and this dev log.

### 2026-10-24 — First marts
- Fixed the sort tiebreaker to `ID` (enum values are uppercase).
- Added `fct_title_daily` (one row per title per day: popularity, trending, average_score, chapters) and `dim_title` (one row per title, attributes from its latest snapshot).
- Added `marts/schema.yml` with data tests: uniqueness of `title_id || '-' || snapshot_date` on the fact, unique/not-null `title_id` on the dimension.

### 2026-10-26 — Fixing the marts
- Found the marts weren't materializing as tables: `marts:` config was nested under `staging:` in `dbt_project.yml`, and `fct_title_daily` lived in `models/staging/`. Fixed both.
- Fixed `dim_title`'s column list (it had the fact's measures).
- Ignored dbt's `.user.yml`.
- Refreshed `CLAUDE.md` (marts, dbt test/build commands) and this dev log.

### 2026-10-27 — dbt in CI
- Added a "Build dbt models" step to the GitHub Actions workflow: after the dlt load it runs `dbt build --profiles-dir .` in `transform/`, with `SUPABASE_HOST`/`USER`/`PASSWORD` from repo secrets.

### 2026-10-29 — Growth mart
- Added `fct_title_growth`: built on `fct_title_daily`, it uses `LAG` per title to compute `popularity_change`, `days_between` and `popularity_per_day` since the previous snapshot; each title's first snapshot is dropped (nothing to compare against).
- Added grain-uniqueness and not-null key tests for it in `marts/schema.yml`.
- Refreshed `CLAUDE.md` (CI now runs dbt, new mart) and this dev log.

### 2026-11-01 — Static "trending today" page (in progress, uncommitted)
- Added `page/top10.sql`: top 10 titles per country from the latest snapshot, `fct_title_daily` joined to `dim_title`, display title falls back from English to romaji.
- Added `page/build_page.py`: runs the SQL with `psycopg2` and renders `site/index.html` (three sections JP/KR/CN with covers, rank, trending and popularity). The SQL holds the logic; the script only renders.
- Guard: the script refuses to publish unless exactly 30 rows come back.
- Ignored `site/` (generated output); fixed the `.user.yml` ignore pattern and untracked the file.
- First local run: hit the system-Python and missing-env-var problems above; with `--env-file .env` it wrote all 30 titles for the 2026-11-01 snapshot.
- Added page deployment to the daily workflow: after `dbt build` it runs `build_page.py`, uploads `site/` with `actions/upload-pages-artifact@v3` and deploys with `actions/deploy-pages@v4` to GitHub Pages.
- Refreshed `CLAUDE.md` and this dev log.

### 2026-11-01 — Page shipped; starting a Databricks branch
- Committed the trending page and its Pages deploy (`22b44ef`), then restyled the page CSS (`cc34d24`).
- Started a `databricks` branch with a Databricks Asset Bundle (`databricks.yml`, uncommitted): Unity Catalog `anilist` with `landing`/`bronze`/`silver`/`gold` schemas and a managed `landing.raw` volume for raw JSON files (one per country per run).
- Two targets, `dev` (default) and `prod`, both on CLI profile `anilist`; a schema-name `prefix` variable (`dev_` vs none) so dev and prod never share tables.
- Ignored `.databricks/` (bundle state).
- Refreshed `CLAUDE.md` and this dev log.

### 2026-11-01 — Databricks session 1
- Egress test (can the workspace reach the AniList API?): `TODO: paste the output line`
- Databricks CLI v1.23.0, logged in through OAuth (profile `anilist`, `auth_type = databricks-cli`).
- Created the `anilist` catalog by hand in the workspace; the bundle only creates schemas and volumes inside it, so the catalog is a prerequisite to list in the README.
- `databricks bundle deploy`: first run created 5 resources (4 schemas + the `raw` volume); a second run reported all 5 unchanged.
- Checked that `.env` is not synced to the workspace by the bundle.
- Known limit: I'm running as a workspace admin, so nothing has been tested yet with narrower permissions.
- `databricks fs cp` into the volume fails unless the target folder exists; run `databricks fs mkdir` first.
- Kimball notes (what it says → where it lands in AniList Trends):
  - What it says:
    The big idea (from Star Schemas and OLAP Cubes)
    Dimensional modeling splits data into two kinds:
    - Facts: the measurements from a business event.
    - Dimensions: the "who, what, where, when, why and how" context around it.

    A star schema builds this in a relational database: a central fact table joined to dimension tables by primary/foreign keys. An OLAP cube is a multidimensional version, usually built from a star schema and queried with languages more analytic than SQL. The approach works whichever warehouse architecture you follow, Kimball's or Inmon's.

    The method (from Four Step Dimensional Design Process)
    1. Select the business process (Business Processes)
      - A real operational activity, like taking an order or processing a claim.
      - Each process's events produce the metrics that become facts. Most fact tables cover one process.
      - Choosing the process gives the design a clear target.
    2. Declare the grain (Grain), the most important step
      - The grain states exactly what one row of the fact table represents. It's a binding contract.
      - Declare it before choosing dimensions or facts, because everything else must match it.
      - Start with atomic grain, the lowest level the process captures, because it can answer questions nobody predicted. Summaries are only for performance.
      - Never mix grains in one table. A different grain means a separate table.
    3. Identify the dimensions (Dimensions for Descriptive Context)
      - The descriptive attributes BI tools use to filter and group facts.
      - Where possible, each dimension should have a single value per fact row.
      - Dimensions are called the "soul" of the warehouse because they drive the user's expegovernance effort.
    4. Identify the facts (Facts for Measurements)
      - Measurements of the event, almost always numeric.
      - One row matches one measurement event at the declared grain, and is based on what actually happened, not on what a report needs.
      - Only include facts that match the grain. In retail sales, quantity sold and price qulary doesn't.

    After these four steps, the team picks table and column names and business rules, with buso they buy in.
    
    
    → TODO where it lands in AniList Trends.

<!--
Entry template:
### YYYY-MM-DD — Short title
- What was built/changed
- Decisions made and why (also add to the table above)
- Problems hit and the fix (also add to the section above)
- What I learned
-->
