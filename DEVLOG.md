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

## Problems hit & how they were solved

- _(add as they come up — these make the best blog material)_

## Open questions / next steps

- `snapshot_date` is computed per row, not once per run; a run crossing midnight UTC could split across two dates.
- Query sorts only by `TRENDING_DESC` — ties can shuffle between pages (duplicates/misses). A secondary sort key would make paging stable.
- dbt doesn't run in CI yet — only the dlt load does.
- Next modelling layer beyond `stg_titles` (e.g. day-over-day trending changes).

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

<!--
Entry template:
### YYYY-MM-DD — Short title
- What was built/changed
- Decisions made and why (also add to the table above)
- Problems hit and the fix (also add to the section above)
- What I learned
-->
