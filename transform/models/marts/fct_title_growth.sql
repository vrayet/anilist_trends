WITH with_prev AS (
    SELECT
        title_id,
        snapshot_date,
        popularity,
        LAG(popularity)    OVER (PARTITION BY title_id ORDER BY snapshot_date) AS prev_popularity,
        LAG(snapshot_date) OVER (PARTITION BY title_id ORDER BY snapshot_date) AS prev_snapshot_date
    FROM {{ref('fct_title_daily')}}
),
with_change AS (
    SELECT
        *,
        popularity - prev_popularity       AS popularity_change,
        snapshot_date - prev_snapshot_date AS days_between
    FROM with_prev
)
SELECT
    title_id, snapshot_date, popularity, popularity_change, days_between,
    ROUND(popularity_change::numeric / days_between, 2) AS popularity_per_day
FROM with_change 
WHERE prev_popularity IS NOT NULL