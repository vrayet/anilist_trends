-- dim_title: one row per title per status period (SCD Type 2 on status).
-- Grain: title_id + valid_from. Surrogate key: title_key. Durable key: title_id.
-- Type 2 (history kept): status. Type 1 (latest wins): name, country, genres, description, chapters.
CREATE OR REFRESH MATERIALIZED VIEW ${gold_schema}.dim_title (
  CONSTRAINT title_key_present EXPECT (title_key IS NOT NULL)  ON VIOLATION FAIL UPDATE,
  CONSTRAINT valid_range       EXPECT (valid_from <= valid_to) ON VIOLATION FAIL UPDATE
)
COMMENT "Title dimension, SCD2 on status via gaps and islands."
AS
WITH flagged AS (
  -- 1 on a title's first day and on every day its status differs from the previous snapshot
  SELECT
    title_id,
    snapshot_date,
    status,
    CASE
      WHEN status IS DISTINCT FROM
           LAG(status) OVER (PARTITION BY title_id ORDER BY snapshot_date)
      THEN 1 ELSE 0
    END AS is_new_period
  FROM ${silver_schema}.title_daily
),

islands AS (
  -- running total of flags: days with the same number form one unbroken status period
  SELECT
    *,
    SUM(is_new_period) OVER (
      PARTITION BY title_id
      ORDER BY snapshot_date
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS period_num
  FROM flagged
),

periods AS (
  -- one row per period, starting on its first observed day
  SELECT title_id, period_num, status, min(snapshot_date) AS valid_from
  FROM islands
  GROUP BY title_id, period_num, status
),

versioned AS (
  -- next period's start date; NULL means this is the current version
  SELECT
    *,
    LEAD(valid_from) OVER (PARTITION BY title_id ORDER BY valid_from) AS next_valid_from
  FROM periods
),

latest_attributes AS (
  -- Type 1: max_by(col, ord) returns col from the row with the highest ord, i.e. the latest snapshot
  SELECT
    title_id,
    max_by(title_romaji, snapshot_date) AS title_romaji,
    max_by(country,      snapshot_date) AS country,
    max_by(genres,       snapshot_date) AS genres,
    max_by(description,  snapshot_date) AS description,
    max_by(chapters,     snapshot_date) AS chapters
  FROM ${silver_schema}.title_daily
  GROUP BY title_id
)

SELECT
  -- hash, not ROW_NUMBER: the same version gets the same key on every refresh
  xxhash64(v.title_id, v.valid_from)                        AS title_key,
  v.title_id,
  a.title_romaji,
  a.country,
  a.genres,
  a.description,
  a.chapters,
  v.status,
  v.valid_from,
  COALESCE(date_sub(v.next_valid_from, 1), DATE'9999-12-31') AS valid_to,
  v.next_valid_from IS NULL                                  AS is_current
FROM versioned AS v
JOIN latest_attributes AS a
  ON a.title_id = v.title_id;