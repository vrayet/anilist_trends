-- dim_date: one row per calendar day, generated, not loaded from data.
-- Grain: one row per date. Key: date_key (yyyymmdd integer).
-- Range starts 1 Oct 2026 to cover v1 history (17 Oct onward). Extend the end date before 2028.
CREATE OR REFRESH MATERIALIZED VIEW ${gold_schema}.dim_date
COMMENT "Calendar dimension; days without facts show data gaps such as 19-23 Oct 2026."
AS
WITH days AS (
  -- sequence() builds an array of dates; explode() turns it into one row per date
  SELECT explode(sequence(DATE'2026-10-01', DATE'2027-12-31', INTERVAL 1 DAY)) AS full_date
)

SELECT
  CAST(date_format(full_date, 'yyyyMMdd') AS INT)  AS date_key,      -- 20261108: sortable, readable
  full_date,
  date_format(full_date, 'EEEE')                   AS day_name,      -- Sunday
  dayofweek(full_date) IN (1, 7)                   AS is_weekend,    -- dayofweek: 1 = Sunday, 7 = Saturday
  CAST(date_trunc('WEEK', full_date) AS DATE)      AS week_start,    -- Monday of that week; rpt_rising_week groups on it
  weekofyear(full_date)                            AS iso_week,
  month(full_date)                                 AS month_num,
  date_format(full_date, 'MMMM')                   AS month_name,    -- November
  year(full_date)                                  AS year
FROM days;