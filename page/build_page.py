"""Render site/index.html from page/top10.sql.

Boilerplate: the SQL in top10.sql is the logic; this file only runs it and writes HTML.
Run from the repo root:  uv run python page/build_page.py
"""

import html
import os
from collections import defaultdict
from pathlib import Path

import psycopg2

HERE = Path(__file__).parent
OUT_DIR = HERE.parent / "site"
SECTIONS = [
    ("JP", "Manga · Japan"),
    ("KR", "Manhwa · Korea"),
    ("CN", "Manhua · China"),
]


def fetch():
    """Run top10.sql and return (rows as dicts, snapshot date)."""
    sql = (HERE / "top10.sql").read_text().strip().rstrip(";")
    conn = psycopg2.connect(os.environ["DESTINATION__POSTGRES__CREDENTIALS"])
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [c.name for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.execute("SELECT max(snapshot_date) FROM analytics.fct_title_daily")
            as_of = cur.fetchone()[0]
    finally:
        conn.close()
    return rows, as_of


def card(r):
    title = html.escape(r["display_title"] or "")
    cover = html.escape(r["cover_image_url"] or "")
    return f"""
      <li class="card">
        <span class="rank">{r["rank"]}</span>
        <img src="{cover}" alt="" loading="lazy" width="50" height="70">
        <div class="meta">
          <p class="title" title="{title}">{title}</p>
          <p class="nums">trending {r["trending"]} · {r["popularity"]:,} readers</p>
        </div>
      </li>"""


def render(rows, as_of):
    by_country = defaultdict(list)
    for r in rows:
        by_country[r["country"]].append(r)

    sections = ""
    for code, label in SECTIONS:
        cards = "".join(card(r) for r in by_country.get(code, []))
        sections += f"""
    <section>
      <h2>{label}</h2>
      <ol>{cards}
      </ol>
    </section>"""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AniList Trends</title>
  <style>
    :root {{ --bg:#fff; --fg:#111; --muted:#666; --line:#e5e5e5; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg:#111; --fg:#eee; --muted:#999; --line:#2a2a2a; }} }}
    body {{ margin:0; padding:16px; background:var(--bg); color:var(--fg); font-family:system-ui,sans-serif; }}
    main {{ max-width:1100px; margin:0 auto; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:24px; }}
    ol {{ list-style:none; padding:0; margin:0; }}
    .card {{ display:flex; align-items:center; gap:12px; padding:8px 0; border-bottom:1px solid var(--line); }}
    .rank {{ flex:0 0 1.5em; text-align:right; color:var(--muted); font-variant-numeric:tabular-nums; }}
    img {{ flex:0 0 50px; border-radius:4px; object-fit:cover; }}
    .meta {{ flex:1; min-width:0; }}
    .title {{ margin:0; font-weight:600; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
    .nums {{ margin:2px 0 0; font-size:.85em; color:var(--muted); }}
    footer {{ margin-top:32px; font-size:.85em; color:var(--muted); }}
  </style>
</head>
<body>
<main>
  <h1>Trending today</h1>
  <p>Top 10 per country on AniList · data as of {as_of} (UTC)</p>
  <div class="grid">{sections}
  </div>
  <footer>Updated daily by a dlt → Postgres → dbt pipeline. Data from AniList.</footer>
</main>
</body>
</html>
"""


def main():
    rows, as_of = fetch()
    if len(rows) != 30:
        raise SystemExit(f"Expected 30 rows from top10.sql, got {len(rows)}. Not publishing.")
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "index.html").write_text(render(rows, as_of), encoding="utf-8")
    print(f"Wrote {OUT_DIR / 'index.html'} ({len(rows)} titles, as of {as_of})")


if __name__ == "__main__":
    main()