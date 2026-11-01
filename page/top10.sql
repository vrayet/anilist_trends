with
  ranked as (
    select
      COALESCE(d.title_english, d.title_romaji) as display_title,
      d.country,
      d.cover_image_url,
      f.trending,
      f.popularity,
      ROW_NUMBER() over (
        partition by
          d.country
        order by
          f.trending desc,  f.popularity DESC, f.title_id
      ) as rank
    from
      analytics.fct_title_daily f
      join analytics.dim_title d on d.title_id = f.title_id
    where
      f.snapshot_date = (
        select
          max(snapshot_date)
        from
          analytics.fct_title_daily
      )
  )
select
  *
from
  ranked
where
  rank <= 10
order by
  country,
  rank