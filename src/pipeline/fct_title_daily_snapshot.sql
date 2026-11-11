-- fct_title_daily_snapshot: periodic snapshot, one row per title per snapshot day.
-- Grain: title_id + snapshot_date (= one Silver row).
-- Keys: date_key -> dim_date; title_key -> the dim_title version valid on that day.
-- Facts: popularity, trending = semi-additive (sum across titles within a day, never across days);
--        average_score = non-additive (average only).
CREATE OR REFRESH MATERIALIZED VIEW ${gold_schema}.fct_title_daily_snapshot (
  -- LEFT JOIN + these: a missing dimension row fails the pipeline instead of silently dropping facts
  CONSTRAINT title_key_found EXPECT (title_key IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT date_key_found  EXPECT (date_key  IS NOT NULL) ON VIOLATION FAIL UPDATE
)
COMMENT "Daily periodic snapshot of each title in its country's top 200."
AS
SELECT
  dd.date_key,
  dt.title_key,
  s.title_id,          -- durable key: follow one title across its versions without a join
  s.popularity,
  s.trending,
  s.average_score
FROM ${silver_schema}.title_daily AS s
LEFT JOIN ${gold_schema}.dim_title AS dt
  ON  dt.title_id = s.title_id
  AND s.snapshot_date BETWEEN dt.valid_from AND dt.valid_to   -- point-in-time: the version true that day
LEFT JOIN ${gold_schema}.dim_date AS dd
  ON dd.full_date = s.snapshot_date;