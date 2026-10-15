import dlt
from dlt.sources.helpers import requests

QUERY = """
query ($country: CountryCode, $page: Int) {
    Page(page: $page, perPage: 10) {
        media(type: MANGA, countryOfOrigin: $country, sort: TRENDING_DESC) {
            id
            title { romaji english }
            popularity
            averageScore
            trending
            status
            chapters
        }
    }
}
"""

@dlt.resource(name="titles", write_disposition="append")
def trending_titles():
    for country in ["JP", "KR", "CN"]:
        resp= requests.post(
            "https://graphql.anilist.co",
            json={"query": QUERY, "variables": {"country": country, "page": 1}},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for manga in data['data']['Page']['media']:
            yield{
                "id": manga['id'],
                "title_romaji": manga['title']['romaji'],
                "title_english": manga['title']['english'],
                "popularity": manga['popularity'],
                "average_score": manga['averageScore'],
                "trending": manga['trending'],
                "status": manga['status'],
                "chapters": manga['chapters'],
                "country": country,
            }





if __name__ == "__main__":
    pipeline = dlt.pipeline(
        pipeline_name="anilist", destination="duckdb", dataset_name="raw"
    )
    print(pipeline.run(trending_titles()))
