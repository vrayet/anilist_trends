-- One row per title per day: the daily measurements.
select
    title_id,
    snapshot_date,
    popularity,
    trending,
    average_score,
    chapters
from {{ ref('stg_titles') }}