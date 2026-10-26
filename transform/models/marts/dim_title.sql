with ranked as (
    select
        *,
        row_number() over (
            partition by title_id            -- restart numbering for each title
            order by snapshot_date desc      -- newest snapshot gets 1
        ) as rn
    from {{ ref('stg_titles') }}
)
select title_id, title_romaji, title_english, country, status, cover_image_url, cover_image_color AS cover_color
from ranked
where rn = 1