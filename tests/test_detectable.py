# All games, ids and hashes below are made up.
import asyncio
import subprocess
import sys

import pytest

from rpc_buddy.detectable import (
    DetectableCache,
    build_index,
    query_game,
    read_fetched_at,
    refresh_database,
    refresh_in_subprocess,
    write_database,
)

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


def fake_refresh(calls: list):
    """Stands in for the child process: writes the database in-process."""

    async def refresh(path):
        calls.append(path)
        refresh_database(path, fetch=lambda: APPS)

    return refresh


def test_build_index_groups_by_distributor():
    index = build_index(APPS)
    assert set(index) == {"steam", "xbox"}
    assert set(index["steam"]) == {"1000001", "1000002"}
    assert index["steam"]["1000002"][:2] == ("900000000000000002", "Sample Racer")
    assert index["xbox"]["XBOX0000002"][0] == "900000000000000002"


def test_database_roundtrip(tmp_path):
    path = tmp_path / "db.sqlite3"
    write_database(path, build_index(APPS), 1234.5)
    assert read_fetched_at(path) == 1234.5
    game = query_game(path, "steam", "1000001")
    assert game.name == "Example Quest"
    assert game.image_url.endswith("/900000000000000001/cover1.png")
    assert query_game(path, "steam", "1000002").image_url.endswith("/icon2.png")  # no cover
    assert query_game(path, "epic", "1000001") is None
    assert read_fetched_at(tmp_path / "missing.sqlite3") is None


def test_lookup_refreshes_once_and_uses_the_database(tmp_path):
    calls = []
    cache = DetectableCache(tmp_path, refresh=fake_refresh(calls))
    assert asyncio.run(cache.lookup("steam", "1000001")).name == "Example Quest"
    assert asyncio.run(cache.lookup("xbox", "XBOX0000002")).name == "Sample Racer"
    assert len(calls) == 1

    async def must_not_refresh(path):
        pytest.fail("should use the existing database")

    cache2 = DetectableCache(tmp_path, refresh=must_not_refresh)
    assert asyncio.run(cache2.lookup("steam", "1000001")).app_id == "900000000000000001"


def test_unknown_game_returns_none(tmp_path):
    cache = DetectableCache(tmp_path, refresh=fake_refresh([]))
    assert asyncio.run(cache.lookup("steam", "999")) is None


def test_refresh_failure_without_database_raises(tmp_path):
    async def failing(path):
        raise RuntimeError("offline")

    cache = DetectableCache(tmp_path, refresh=failing)
    with pytest.raises(RuntimeError):
        asyncio.run(cache.lookup("steam", "1000001"))


def test_refresh_failure_keeps_old_database(tmp_path):
    write_database(tmp_path / "detectable.sqlite3", build_index(APPS), 0.0)  # very old

    async def failing(path):
        raise RuntimeError("offline")

    cache = DetectableCache(tmp_path, refresh=failing)
    assert asyncio.run(cache.lookup("steam", "1000001")).name == "Example Quest"


def test_old_json_cache_is_removed(tmp_path):
    (tmp_path / "detectable-index.json").write_text("{}")
    DetectableCache(tmp_path, refresh=fake_refresh([]))
    assert not (tmp_path / "detectable-index.json").exists()


def test_child_process_reports_errors(tmp_path):
    # Wrong usage: no network needed, checks the entry point of the child.
    result = subprocess.run(
        [sys.executable, "-m", "rpc_buddy.detectable"], capture_output=True, text=True
    )
    assert result.returncode == 2 and "usage" in result.stderr

    async def run():
        # A directory as database path makes the child fail before downloading.
        await refresh_in_subprocess(tmp_path)

    with pytest.raises(RuntimeError):
        asyncio.run(run())
