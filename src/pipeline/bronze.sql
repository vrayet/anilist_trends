-- Bronze: every landing file read exactly once, kept in the raw API shape.
-- Grain: one row per API page. Each file holds 4 pages of 50 titles.
CREATE OR REFRESH STREAMING TABLE raw_pages
COMMENT "AniList API pages as received; one row per page, appended once per landing file."
AS SELECT
  *,                                      -- the page exactly as AniList sent it (a `data` struct)
  _metadata.file_path AS source_file,     -- lineage: which landing file this row came from
  current_timestamp() AS ingested_at      -- when Bronze picked the file up
FROM STREAM read_files(
  -- landing_path comes from the pipeline config, so dev and prod read their own Volume.
  -- The glob skips stray files: Silver rebuilds from all of Bronze, so one bad row would fail every update.
  '${landing_path}/snapshot_date=*/country=*/run=*.json',
  format => 'json',
  multiLine => true    -- each file is one JSON array; each element (one page) becomes one row
);