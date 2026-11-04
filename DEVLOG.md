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
| Delete v1 code from the `databricks` branch instead of keeping it alongside | v1 stays on `main`; the v2 branch only holds the Databricks rebuild | 2026-11-02 |
| Pin Python 3.12 (`requires-python = ">=3.12,<3.13"`) | Match Databricks serverless | 2026-11-02 |
| `fetch.py` fetches every country before writing any file | A failure leaves the day absent, never partial | 2026-11-02 |
| `write_raw` opens files with mode `"x"` | Raw files can't be refetched, so a filename clash must fail loudly instead of overwriting | 2026-11-02 |
| `main(argv=None)` passed to `parse_args` | Databricks notebook kernels inject `-f` into `sys.argv`; callers can pass their own args | 2026-11-02 |
| pytest (dev) with `pythonpath = ["src"]`, `testpaths = ["tests"]` | pytest only puts the test file's own folder on the import path, so `import fetch` needs `src` added; keeps `src` from becoming a package | 2026-11-04 |

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
- **`fetch.py` broke when run from a notebook:** Databricks notebook kernels inject `-f` into `sys.argv`, so `argparse` choked on it. Fixed with `main(argv=None)` → `parser.parse_args(argv)` (`3e70a15`). (2026-11-02)
- **`databricks fs ls` timestamps:** they show IST times but with a `Z` (UTC) suffix, so they can't be read as UTC. (2026-11-02)

## Open questions / next steps

- Growth for other measures (e.g. `trending`, `average_score`); so far `fct_title_growth` only covers popularity.
- v2: landing ingestion exists (`src/fetch.py`); still to do: bronze/silver/gold tables, a Databricks job, and porting `page/` to read from gold.

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
- Egress test from a Free Edition notebook to graphql.anilist.co returned 200 `{"data":{"Media":{"id":30002,"title":{"romaji":"Berserk"}}}}`, so `fetch.py` can run on Databricks.
- Databricks CLI v1.23.0, logged in through OAuth (profile `anilist`, `auth_type = databricks-cli`).
- Created the `anilist` catalog by hand in the workspace; the bundle only creates schemas and volumes inside it, so the catalog is a prerequisite to list in the README.
- `databricks bundle deploy`: first run created 5 resources (4 schemas + the `raw` volume); a second run reported all 5 unchanged.
- Checked that `.env` is not synced to the workspace by the bundle.
- Known limit: I'm running as a workspace admin, so nothing has been tested yet with narrower permissions.
- `databricks fs cp` into the volume fails unless the target folder exists; run `databricks fs mkdir` first.
- 2026-11-02 ~00:46, merged PR #1 (`databricks` → `main`) by accident, which deleted v1's workflow from `main`. Fixed with `git reset --hard cc34d24` and `git push --force-with-lease origin main`. Chose reset over `git revert -m 1` because reverting a merge commit makes git treat those changes as already merged, so the real `databricks` → `main` merge at cutover would silently drop them.
- Kimball four-step, applied:
  - Business process: AniList's daily trending ranking of manga per country of origin, captured once a day.
  - Grain: one row = one title on one snapshot_date. A title has a row only on days it is in its country's top 200; no row means not ranked, not zero.
  - Dimensions: dim_title (titles, cover, status, genres; SCD2 on status) and dim_date.
  - Facts: trending and popularity. title_id is a foreign key, not a fact. Popularity is semi-additive: sum across titles on one day, never across days.
  - Dropping the catalog deletes the managed Volume's raw files: infra rebuilds with one deploy, data does not.

### 2026-11-02 — Clearing v1 out of the v2 branch
- Removed the v1 code from the `databricks` branch (`c8bdf72`): `pipeline.py`, `explore.py`, the dbt project in `transform/`, the GitHub Actions workflow and the `src/` stub. It stays on `main`.
- Dropped `dlt` and `dbt-postgres` from dependencies (only `requests` remains) along with the build backend and console script; project description is now "a medallion pipeline on Databricks".
- Stopped tracking `.vscode/settings.json` (`92dcbc8`).
- `page/` was kept, but it doesn't run on this branch yet: `psycopg2` went away with dlt/dbt, and it reads Supabase `analytics.*` tables.
- Refreshed `CLAUDE.md` for the v2 branch and this dev log.

### 2026-11-04 — Offline tests for fetch.py
- From session 2a (2026-11-02):
  - Pinned Python 3.12 to match Databricks serverless (`978957d`).
  - Added `src/fetch.py` (`2a2437f`): fetches trending manga for JP/KR/CN and writes the raw API pages to the landing Volume as `snapshot_date=<date>/country=<CC>/run=<UTC ts>.json`. All countries are fetched before any file is written (all-or-nothing), and files are never overwritten.
  - Databricks notebook kernels inject `-f` into `sys.argv`, which broke `argparse`; changed to `main(argv=None)` (`3e70a15`).
  - `databricks fs ls` shows IST times with a `Z` suffix.
- Added pytest to the dev group, with `pythonpath = ["src"]` in `[tool.pytest.ini_options]` because pytest only puts the test file's own folder on the import path (and `testpaths = ["tests"]`).
- 3 offline tests in `tests/test_fetch.py` (no network, no Databricks):
  - `write_raw` writes to the partitioned path layout.
  - `write_raw` refuses to overwrite an existing file.
  - `fetch_page` raises on an HTTP 200 whose body has GraphQL `errors`, using `monkeypatch` to swap out `requests.post`.
- Proved the overwrite test actually tests something: switched `"x"` to `"w"` in `write_raw` and saw pytest report `DID NOT RAISE`.
- ruff catches missing imports before pytest runs.
- Added comments in `fetch.py` explaining the `"x"` mode and the fetch-all-then-write order; dropped the unused `PER_PAGE` constant.
- Refreshed `CLAUDE.md` and this dev log.

<!--
Entry template:
### YYYY-MM-DD — Short title
- What was built/changed
- Decisions made and why (also add to the table above)
- Problems hit and the fix (also add to the section above)
- What I learned
-->
