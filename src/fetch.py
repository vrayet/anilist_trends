"""Fetch AniList trending manga per country; write raw API responses to the landing Volume."""

import argparse
import datetime as dt
import json
import time
from pathlib import Path

import requests

API_URL = "https://graphql.anilist.co"
COUNTRIES = ["JP", "KR", "CN"]
DEFAULT_LANDING_DIR = Path("/Volumes/anilist/dev_landing/raw")
PAGES = 4
QUERY = """ 
query ($country: CountryCode, $page: Int) {
    Page(page: $page, perPage: 50) {
        pageInfo {hasNextPage}
        media(type: MANGA, countryOfOrigin: $country, sort: [TRENDING_DESC, ID]) {
            id
            title { romaji english }
            popularity
            description
            genres
            averageScore
            trending
            status
            chapters
            coverImage {
                medium
                color
            }
        }
    }
} 
"""


def fetch_page(country: str, page: int) -> dict:
    resp = requests.post(
        API_URL,
        json={"query": QUERY, "variables": {"country": country, "page": page}},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()

    if "errors" in body:
        raise RuntimeError(
            f"AniList errors for {country}, page {page}: {body['errors']}"
        )
    return body


def fetch_country(country: str) -> list[dict]:
    pages = []
    for page in range(1, PAGES + 1):
        if page > 1:
            time.sleep(2)
        body = fetch_page(country, page)
        pages.append(body)
        if not body["data"]["Page"]["pageInfo"]["hasNextPage"]:
            break
    return pages


def write_raw(
    pages: list[dict], landing_dir: Path, snapshot_date: str, country: str, run_ts: str
) -> Path:
    folder = landing_dir / f"snapshot_date={snapshot_date}" / f"country={country}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"run={run_ts}.json"
    # "x" refuses to overwrite: raw files can't be refetched, so a clash must fail loudly.
    with open(path, "x") as f:
        json.dump(pages, f)
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    now = dt.datetime.now(dt.UTC)
    today = now.date()
    parser.add_argument(
        "--snapshot-date", type=dt.date.fromisoformat, default=today.isoformat()
    )
    parser.add_argument("--landing-dir", type=Path, default=DEFAULT_LANDING_DIR)
    args = parser.parse_args(argv)
    # No backfill: AniList only returns today's ranking. Yesterday is allowed for a run
    # triggered just before midnight UTC that starts just after.
    if args.snapshot_date not in (today, today - dt.timedelta(days=1)):
        parser.error(
            f"--snapshot-date must be today or yesterday (UTC), got {args.snapshot_date}"
        )
    run_ts = now.strftime("%Y%m%dT%H%M%SZ")

    # Fetch every country before writing any file: a failure leaves the day absent, never partial.
    fetched = {country: fetch_country(country) for country in COUNTRIES}
    for country, pages in fetched.items():
        path = write_raw(
            pages, args.landing_dir, args.snapshot_date.isoformat(), country, run_ts
        )
        titles = sum(len(p["data"]["Page"]["media"]) for p in pages)
        print(f"{country}: {titles} titles -> {path}")


if __name__ == "__main__":
    main()
