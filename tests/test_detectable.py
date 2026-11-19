# All games, ids and hashes below are made up.
import asyncio
import json

import pytest

from rpc_buddy.detectable import DetectableCache, build_index

APPS = [
    {
        "id": "900000000000000001",
        "name": "Example Quest",
        "icon_hash": "icon1",
        "cover_image_hash": "cover1",
        "third_party_skus": [{"distributor": "steam", "id": "1000001"}],
    },
    {
        "id": "900000000000000002",
        "name": "Sample Racer",
        "icon_hash": "icon2",
        "cover_image_hash": None,
        "third_party_skus": [
            {"distributor": "xbox", "id": "XBOX0000002"},
            {"distributor": "steam", "id": "1000002"},
        ],
    },
    {"id": "900000000000000003", "name": "No Store", "third_party_skus": None},
]


def test_build_index_groups_by_distributor():
    index = build_index(APPS)
    assert set(index) == {"steam", "xbox"}
    assert set(index["steam"]) == {"1000001", "1000002"}
    assert index["steam"]["1000002"][:2] == ["900000000000000002", "Sample Racer"]
    assert index["xbox"]["XBOX0000002"][0] == "900000000000000002"


def test_lookup_fetches_once_and_caches_on_disk(tmp_path):
    calls = []

    def fetch():
        calls.append(1)
        return APPS

    cache = DetectableCache(tmp_path, fetch=fetch)
    game = asyncio.run(cache.lookup("steam", "1000001"))
    assert game.name == "Example Quest"
    assert game.image_url.endswith("/900000000000000001/cover1.png")
    # No cover: falls back to the icon.
    assert asyncio.run(cache.lookup("steam", "1000002")).image_url.endswith("/icon2.png")
    assert len(calls) == 1

    # A new instance uses the file on disk instead of downloading again.
    cache2 = DetectableCache(tmp_path, fetch=lambda: pytest.fail("should not fetch"))
    assert asyncio.run(cache2.lookup("steam", "1000001")).app_id == "900000000000000001"
    assert json.loads((tmp_path / "detectable-index.json").read_text())["version"] == 2


def test_unknown_game_returns_none(tmp_path):
    cache = DetectableCache(tmp_path, fetch=lambda: APPS)
    assert asyncio.run(cache.lookup("steam", "999")) is None


def test_fetch_failure_without_cache_raises(tmp_path):
    def fetch():
        raise OSError("offline")

    cache = DetectableCache(tmp_path, fetch=fetch)
    with pytest.raises(OSError):
        asyncio.run(cache.lookup("steam", "1000001"))


def test_lookup_other_distributor(tmp_path):
    cache = DetectableCache(tmp_path, fetch=lambda: APPS)
    assert asyncio.run(cache.lookup("xbox", "XBOX0000002")).name == "Sample Racer"
    assert asyncio.run(cache.lookup("epic", "1000001")) is None
