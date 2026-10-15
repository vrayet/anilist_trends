import requests
import json
 
QUERY = """
query {
    Page(page: 1, perPage: 10) {
        media(type: MANGA, countryOfOrigin: JP, sort: TRENDING_DESC) {
            id
            title { romaji english }
            popularity
            averageScore
            trending
            status
            genres
            chapters
        }
    }
}
"""

resp = requests.post(
    "https://graphql.anilist.co",
    json={"query": QUERY},
    timeout=30,
)
resp.raise_for_status()
data = resp.json()



for manga in data['data']['Page']['media']:
    print(f"ID: {manga['id']}")
    print(f"Title (Romaji): {manga['title']['romaji']}")
    print(f"Title (English): {manga['title']['english']}")
    print(f"Popularity: {manga['popularity']}")
    print(f"Average Score: {manga['averageScore']}")
    print(f"Trending: {manga['trending']}")
    print(f"Status: {manga['status']}")
    print(f"Genres: {', '.join(manga['genres'])}")
    print(f"Chapters: {manga['chapters']}")
    print("-" * 40)