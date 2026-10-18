import dlt
from dlt.sources.helpers import requests
from datetime import datetime, timezone
import time

QUERY = """
query ($country: CountryCode, $page: Int) {
    Page(page: $page, perPage: 50) {
        pageInfo {hasNextPage}
        media(type: MANGA, countryOfOrigin: $country, sort: [TRENDING_DESC, id]) {
            id
            title { romaji english }
            popularity
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

MAX_PAGES = 4

@dlt.resource(
    name="titles", write_disposition="merge", primary_key=["id", "snapshot_date"], merge_key="snapshot_date",)
def trending_titles():
    snapshot_date = datetime.now(timezone.utc).date()
    for country in ["JP", "KR", "CN"]:
        for page in range(1, MAX_PAGES + 1):
            resp = requests.post(
                "https://graphql.anilist.co",
                json={"query": QUERY, "variables": {"country": country, "page": page}},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for manga in data["data"]["Page"]["media"]:
                yield {
                    "id": manga["id"],
                    "title_romaji": manga["title"]["romaji"],
                    "title_english": manga["title"]["english"],
                    "popularity": manga["popularity"],
                    "average_score": manga["averageScore"],
                    "trending": manga["trending"],
                    "status": manga["status"],
                    "chapters": manga["chapters"],
                    "country": country,
                    "snapshot_date": snapshot_date,
                    "cover_image_url": manga["coverImage"]["medium"],
                    "cover_image_color": manga["coverImage"]["color"],
                }

            if not data["data"]["Page"]["pageInfo"]["hasNextPage"]:
                break
            time.sleep(2)  # Respectful delay to avoid hitting rate limits

if __name__ == "__main__":
    pipeline = dlt.pipeline(
        pipeline_name="anilist", destination="postgres", dataset_name="raw"
    )
    print(pipeline.run(trending_titles()))
