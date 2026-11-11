-- Silver: one row per title per snapshot_date, typed, latest run wins.
-- Grain: title_id + snapshot_date. Source: raw_pages (Bronze).
CREATE OR REFRESH MATERIALIZED VIEW ${silver_schema}.title_daily (
  -- FAIL UPDATE: stop the pipeline instead of publishing bad rows
  CONSTRAINT title_id_present  EXPECT (title_id IS NOT NULL)      ON VIOLATION FAIL UPDATE,
  CONSTRAINT date_from_path    EXPECT (snapshot_date IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT country_from_path EXPECT (country IN ('JP', 'KR', 'CN')) ON VIOLATION FAIL UPDATE
)
COMMENT "One row per title per day; reruns deduplicated to the latest run."
AS
WITH exploded AS (
  -- one row per title per page
  SELECT source_file, explode(data.Page.media) AS m
  FROM raw_pages   -- Bronze, in this pipeline's default schema
),

flattened AS (
  -- date, country and run exist only in the file path
  SELECT
    to_date(regexp_extract(source_file, 'snapshot_date=([0-9-]+)', 1)) AS snapshot_date,
    regexp_extract(source_file, 'country=([A-Z]+)', 1)                 AS country,
    regexp_extract(source_file, 'run=([^/]+)[.]json', 1)               AS run_id,
    m.id           AS title_id,
    m.title.romaji AS title_romaji,
    m.status       AS status,
    m.chapters     AS chapters,
    m.genres       AS genres,
    m.description  AS description,
    m.popularity   AS popularity,
    m.trending     AS trending,
    m.averageScore AS average_score
  FROM exploded
),

ranked AS (
  SELECT
    *,
    -- reruns land a second run= file for the same day; the whole day comes from the newest run,
    -- so titles that dropped out of the top 200 between runs don't linger
    -- per country too: a hand-landed single-country file must not drop the other countries
    max(run_id) OVER (PARTITION BY snapshot_date, country) AS latest_run,
    -- a title can appear twice in one run if its rank shifts while pages are fetched;
    -- trending, then popularity, break that tie so the kept row is deterministic
    ROW_NUMBER() OVER (
      PARTITION BY title_id, snapshot_date
      ORDER BY run_id DESC, trending DESC, popularity DESC
    ) AS rn
  FROM flattened
)

SELECT
  snapshot_date, country, title_id, title_romaji, status, chapters,
  genres, description, popularity, trending, average_score, run_id
FROM ranked
WHERE run_id = latest_run AND rn = 1;