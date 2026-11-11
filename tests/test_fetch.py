"""Offline tests for fetch.py: no network, no Databricks."""

import json

import pytest
import requests

import fetch
from fetch import fetch_page, write_raw

# A tiny stand-in for one API page: same shape as the real thing, one title.
SAMPLE_PAGES = [{"data": {"Page": {"media": [{"id": 1}]}}}]


def test_write_raw_creates_partitioned_file(tmp_path):
    # tmp_path is a fresh empty folder pytest creates for this test only,
    # so the test can never write into the real Volume.
    path = write_raw(SAMPLE_PAGES, tmp_path, "2026-11-04", "JP", "20261104T000000Z")

    # The exact layout Bronze will read: key=value folders, one file per run.
    expected = (
        tmp_path
        / "snapshot_date=2026-11-04"
        / "country=JP"
        / "run=20261104T000000Z.json"
    )
    assert path == expected

    # What we read back must be exactly what we wrote, with nothing reshaped.
    assert json.loads(path.read_text()) == SAMPLE_PAGES


def test_write_raw_refuses_to_overwrite(tmp_path):
    args = (SAMPLE_PAGES, tmp_path, "2026-11-04", "JP", "20261104T000000Z")
    write_raw(*args)  # first write lands normally

    # The same date, country and run timestamp again: mode "x" must refuse.
    with pytest.raises(FileExistsError):
        write_raw(*args)


class FakeErrorResponse:
    """Mimics a rate-limited AniList reply: HTTP 200, but the body says error."""

    def raise_for_status(self):
        pass  # HTTP status is fine, so the first check passes

    def json(self):
        return {"errors": [{"message": "Too Many Requests"}]}


def test_fetch_page_raises_on_graphql_errors(monkeypatch):
    # monkeypatch swaps requests.post for this test only, then puts it back.
    # So no real request leaves your laptop.
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: FakeErrorResponse())

    with pytest.raises(RuntimeError, match="AniList errors"):
        fetch_page("JP", 1)


def test_main_writes_nothing_if_one_country_fails(tmp_path, monkeypatch):
    # JP succeeds, KR fails: the rule is "fetch all, then write", so no file may exist.
    def fake_fetch_country(country):
        if country == "KR":
            raise RuntimeError("KR down")
        return SAMPLE_PAGES

    monkeypatch.setattr(fetch, "fetch_country", fake_fetch_country)

    with pytest.raises(RuntimeError, match="KR down"):
        fetch.main(["--landing-dir", str(tmp_path)])
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bad_date", ["2026-11-31", "2020-01-01"])
def test_main_rejects_invalid_or_past_snapshot_date(tmp_path, monkeypatch, bad_date):
    # An impossible date or a backfill must stop before anything is fetched.
    monkeypatch.setattr(fetch, "fetch_country", lambda c: pytest.fail("fetched"))

    with pytest.raises(SystemExit):
        fetch.main(["--snapshot-date", bad_date, "--landing-dir", str(tmp_path)])
