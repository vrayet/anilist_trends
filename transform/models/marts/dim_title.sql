with ranked as (
    select
        *,
        row_number() over (
            partition by title_id            -- restart numbering for each title
            order by snapshot_date desc      -- newest snapshot gets 1
        ) as rn
    from {{ ref('stg_titles') }}
)
select title_id, snapshot_date, popularity, trending, average_score, chapters
from ranked
where rn = 1