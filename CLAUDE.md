# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Early-stage Python project for pulling trending manga/anime data from the AniList GraphQL API. The installable package (`src/anilist_trends/`) is still the `uv init` stub; the real working code so far is `explore.py`, a standalone exploration script. No tests, linter, or formatter are configured yet.

## Commands

Managed with `uv` (build backend `uv_build`), Python 3.14 (pinned in `.python-version`).

```sh
uv sync                    # install deps into .venv
uv run python explore.py   # run the AniList exploration script (hits the live API)
uv run anilist-trends      # package entry point -> anilist_trends:main
uv add <pkg>               # add a dependency (updates pyproject.toml + uv.lock)
```

## Architecture

- `src/anilist_trends/__init__.py` — package root; `main()` is the console-script entry point declared in `pyproject.toml` under `[project.scripts]`.
- `explore.py` — top-level script (not part of the package) that POSTs a GraphQL query to `https://graphql.anilist.co` with `requests` and prints the response shape and fields. Use it as the reference for the query format and the response structure (`data.Page.media[]`, with `title.romaji` / `title.english`, `popularity`, `averageScore`, `trending`, `status`, `genres`, `chapters`).

## AniList API notes

- Single GraphQL endpoint, no auth needed for public queries; send `{"query": ..., "variables": ...}` as JSON.
- AniList rate-limits requests (around 90/min, sometimes lowered); expect HTTP 429 with a `Retry-After` header when paginating.
- `title.english` (and other fields such as `chapters` or `averageScore`) can be `null`.
