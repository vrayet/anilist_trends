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

## Problems hit & how they were solved

- **Sort enum casing:** `sort: [TRENDING_DESC, id]` was wrong — GraphQL enum values are uppercase, so it's `ID`. (2026-10-24)
- **Marts built as views, not tables:** the `marts:` block in `dbt_project.yml` was indented under `staging:`, so its `+materialized: table` never applied. Unindented it to be a sibling of `staging:`. (2026-10-26)
- **Fact model in the wrong folder:** `fct_title_daily.sql` was created in `models/staging/`, so it picked up staging config; moved to `models/marts/`. (2026-10-26)
- **`dim_title` had the fact's columns:** its final `select` was copied from the fact model (measures instead of attributes); fixed to select title, country, status and cover fields. (2026-10-26)
- **dbt `.user.yml`:** dbt generates a per-user `transform/.user.yml`; added to `transform/.gitignore`. (2026-10-26)

## Open questions / next steps

- dbt doesn't run in CI yet — only the dlt load does.
- Next modelling beyond the first marts (e.g. day-over-day trending changes).
- `transform/.user.yml` is still tracked in git even though it's now ignored — needs `git rm --cached`.

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

<!--
Entry template:
### YYYY-MM-DD — Short title
- What was built/changed
- Decisions made and why (also add to the table above)
- Problems hit and the fix (also add to the section above)
- What I learned
-->
