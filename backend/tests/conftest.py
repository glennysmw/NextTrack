"""Shared fixtures. All external APIs are mocked — real network calls are forbidden.

That last clause is *enforced*, not merely intended: the ``_no_network`` autouse
fixture below guards both the socket layer and httpx, so any test that reaches an
unmocked external client fails loudly instead of silently making a live request (and
silently passing or failing on someone else's uptime). ``test_network_guard.py``
verifies the guard itself.
"""
import json
import pathlib
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.data import cache, listenbrainz, musicbrainz
from app.engine import features
from app.main import app

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


MB_DATA = _load("musicbrainz_recording.json")
AB_DATA = _load("acousticbrainz_features.json")
YT_DATA = _load("youtube_search.json")
YT_VIDEO_ID = YT_DATA["items"][0]["id"]["videoId"]

# Convenience MBIDs used across tests.
HISTORY_MBID = "5b11f4ce-a62d-471e-81fc-a69a8278c7da"
COME_AS_YOU_ARE = "8e2f1a3b-5c6d-7e8f-9a0b-1c2d3e4f5a6b"
LITHIUM = "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
IN_BLOOM = "2b3c4d5e-6f7a-8b9c-0d1e-2f3a4b5c6d7e"
ALIVE = "3c4d5e6f-7a8b-9c0d-1e2f-3a4b5c6d7e8f"
BLACK_HOLE_SUN = "4d5e6f7a-8b9c-0d1e-2f3a-4b5c6d7e8f90"
NIRVANA_ARTIST = MB_DATA["artists"]["nirvana"]
PEARL_JAM_ARTIST = MB_DATA["artists"]["pearl_jam"]


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0.0.0.0", "testserver"}
_real_connect = socket.socket.connect
_real_async_send = httpx.AsyncClient.send
_real_sync_send = httpx.Client.send


def _reject(host: object) -> None:
    raise AssertionError(
        f"Test attempted a live network connection to {host!r}. "
        "Mock the external client instead."
    )


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail any test that attempts a real *external* connection.

    Two guards, because one is not enough. The socket-level guard catches the
    synchronous clients (``musicbrainzngs`` reaches the network through urllib), but
    it does **not** catch async ``httpx``: on Windows the Proactor event loop connects
    through overlapped I/O rather than ``socket.socket.connect``, so an unmocked async
    client sails straight past it. That gap was real — the AcousticBrainz bulk client
    made live requests from the suite until it was found. The httpx-level guard closes
    it by inspecting the request URL before either transport is reached.

    Loopback and ``testserver`` are allowed: asyncio and pytest open local socket
    pairs, and FastAPI's TestClient addresses the app in-process as ``testserver``.
    """

    def _guarded_connect(self, address):  # noqa: ANN001 - mirrors socket.connect
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in _LOOPBACK_HOSTS:
            _reject(host)
        return _real_connect(self, address)

    async def _guarded_async_send(self, request, **kwargs):
        if request.url.host not in _LOOPBACK_HOSTS:
            _reject(request.url.host)
        return await _real_async_send(self, request, **kwargs)

    def _guarded_sync_send(self, request, **kwargs):
        if request.url.host not in _LOOPBACK_HOSTS:
            _reject(request.url.host)
        return _real_sync_send(self, request, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(httpx.AsyncClient, "send", _guarded_async_send)
    monkeypatch.setattr(httpx.Client, "send", _guarded_sync_send)


@pytest.fixture(autouse=True)
def _reset_state():
    """Cache, vocabulary, and artist cache are module-level singletons; reset each test."""
    cache.clear()
    features.reset_vocabulary()
    musicbrainz.clear_artist_cache()
    listenbrainz.clear_cache()
    routes._top_cache.clear()
    yield
    cache.clear()
    features.reset_vocabulary()
    musicbrainz.clear_artist_cache()
    listenbrainz.clear_cache()
    routes._top_cache.clear()


@pytest.fixture
def seed_ids() -> SimpleNamespace:
    """Expose the well-known MBIDs the mocked data layer knows about."""
    return SimpleNamespace(
        history=HISTORY_MBID,
        come_as_you_are=COME_AS_YOU_ARE,
        lithium=LITHIUM,
        in_bloom=IN_BLOOM,
        alive=ALIVE,
        black_hole_sun=BLACK_HOLE_SUN,
        nirvana_artist=NIRVANA_ARTIST,
        pearl_jam_artist=PEARL_JAM_ARTIST,
        youtube=YT_VIDEO_ID,
    )


@pytest.fixture
def mock_sources(mocker) -> SimpleNamespace:
    """Patch every external client with deterministic, in-memory mock data."""
    recordings = MB_DATA["recordings"]
    tags = MB_DATA["tags"]

    def get_recording(mbid: str):
        rec = recordings.get(mbid)
        return dict(rec) if rec else None

    def search_by_tag(tag: str, limit: int):
        return [dict(recordings[m]) for m in tags.get(tag.lower(), [])]

    def search_recordings(query: str, limit: int, artist: str | None = None):
        return [dict(r) for r in MB_DATA["search"]]

    def get_features(mbid: str):
        data = AB_DATA.get(mbid)
        return dict(data) if data else None

    def get_features_bulk(mbids: list[str]):
        return {mbid: get_features(mbid) for mbid in mbids}

    def search_video_id(query: str):
        return YT_VIDEO_ID

    def search_songs(query: str, limit: int = 10):
        return [
            {
                "title": "Test Song",
                "artist": "Test Artist",
                "album": "Test Album",
                "thumbnail": "https://img.example/test.jpg",
                "video_id": YT_VIDEO_ID,
            }
        ]

    def get_similar_artists(artist_mbid: str):
        return dict(MB_DATA["similar_artists"].get(artist_mbid, {}))

    mocks = SimpleNamespace(
        get_similar_artists=mocker.patch(
            "app.data.listenbrainz.get_similar_artists",
            new=AsyncMock(side_effect=get_similar_artists),
        ),
        get_recording=mocker.patch(
            "app.data.musicbrainz.get_recording", new=AsyncMock(side_effect=get_recording)
        ),
        search_by_tag=mocker.patch(
            "app.data.musicbrainz.search_by_tag", new=AsyncMock(side_effect=search_by_tag)
        ),
        search_recordings=mocker.patch(
            "app.data.musicbrainz.search_recordings",
            new=AsyncMock(side_effect=search_recordings),
        ),
        get_features=mocker.patch(
            "app.data.acousticbrainz.get_features", new=AsyncMock(side_effect=get_features)
        ),
        get_features_bulk=mocker.patch(
            "app.data.acousticbrainz.get_features_bulk",
            new=AsyncMock(side_effect=get_features_bulk),
        ),
        search_video_id=mocker.patch(
            "app.data.youtube.search_video_id", new=AsyncMock(side_effect=search_video_id)
        ),
        search_songs=mocker.patch(
            "app.data.youtube.search_songs", new=AsyncMock(side_effect=search_songs)
        ),
    )

    mocker.patch("app.data.musicbrainz.ping", new=AsyncMock(return_value="ok"))
    mocker.patch("app.data.acousticbrainz.ping", new=AsyncMock(return_value="degraded"))
    mocker.patch("app.data.youtube.ping", new=AsyncMock(return_value="ok"))
    mocker.patch("app.data.listenbrainz.ping", new=AsyncMock(return_value="ok"))
    return mocks


@pytest.fixture
def client() -> TestClient:
    """A FastAPI TestClient with the application lifespan active."""
    with TestClient(app) as test_client:
        yield test_client
