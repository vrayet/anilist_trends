-- Staging: one row per title per day, cleaned up. No joins, no business logic.
select
    id                as title_id,       -- clearer name for joining later
    snapshot_date,
    country,
    title_romaji,
    title_english,
    status,
    popularity,
    average_score,
    trending,
    chapters,
    cover_image_url,
    cover_image_color
from {{ source('raw', 'titles') }}       -- dbt fills in raw.titles here