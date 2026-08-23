"""Tests for the ListenBrainz client's parsing and (critically) its failure paths.

The collaborative stage is an *enhancement*: every way it can fail must degrade to
"no evidence" rather than propagate an error, because a ListenBrainz outage must not
be able to take down recommendations that the content stage could still serve.
"""
import httpx
import pytest

from app.data import listenbrainz


class _Resp:
    def __init__(self, status_code: int, payload: object = None, bad_json: bool = False):
        self.status_code = status_code
        self._payload = payload
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


def _patch_post(mocker, result):
    """Patch httpx.AsyncClient.post to return `result`, or raise it if it is an error."""

    async def _post(self, url, **kwargs):
        if isinstance(result, Exception):
            raise result
        return result

    mocker.patch.object(httpx.AsyncClient, "post", _post)


async def test_parses_a_well_formed_payload(mocker):
    _patch_post(
        mocker,
        _Resp(200, [{"artist_mbid": "a", "score": 900}, {"artist_mbid": "b", "score": 12.5}]),
    )
    assert await listenbrainz.get_similar_artists("ref") == {"a": 900.0, "b": 12.5}


async def test_skips_malformed_rows_without_discarding_good_ones(mocker):
    _patch_post(
        mocker,
        _Resp(
            200,
            [
                {"artist_mbid": "a", "score": 5},
                {"score": 9},                       # no mbid
                {"artist_mbid": "c"},               # no score
                {"artist_mbid": "d", "score": "x"}, # unparseable score
                "not-a-dict",
            ],
        ),
    )
    assert await listenbrainz.get_similar_artists("ref") == {"a": 5.0}


@pytest.mark.parametrize(
    "result",
    [
        _Resp(500),
        _Resp(404),
        _Resp(200, bad_json=True),
        _Resp(200, {"unexpected": "shape"}),
        httpx.ConnectError("network down"),
        httpx.ReadTimeout("too slow"),
    ],
    ids=["http_500", "http_404", "bad_json", "wrong_shape", "connect_error", "timeout"],
)
async def test_every_failure_degrades_to_no_evidence(mocker, result):
    _patch_post(mocker, result)
    assert await listenbrainz.get_similar_artists("ref") == {}


async def test_empty_artist_mbid_short_circuits(mocker):
    called = mocker.patch.object(httpx.AsyncClient, "post")
    assert await listenbrainz.get_similar_artists("") == {}
    called.assert_not_called()


async def test_results_are_cached_per_artist(mocker):
    calls = {"n": 0}

    async def _post(self, url, **kwargs):
        calls["n"] += 1
        return _Resp(200, [{"artist_mbid": "a", "score": 1}])

    mocker.patch.object(httpx.AsyncClient, "post", _post)
    await listenbrainz.get_similar_artists("ref")
    await listenbrainz.get_similar_artists("ref")
    assert calls["n"] == 1
    assert listenbrainz.cache_size() == 1


async def test_failures_are_not_cached(mocker):
    """A transient outage must not poison the cache with an empty result."""
    _patch_post(mocker, _Resp(503))
    await listenbrainz.get_similar_artists("ref")
    assert listenbrainz.cache_size() == 0


async def test_many_deduplicates_repeated_artists(mocker):
    calls = {"n": 0}

    async def _post(self, url, **kwargs):
        calls["n"] += 1
        return _Resp(200, [{"artist_mbid": "x", "score": 1}])

    mocker.patch.object(httpx.AsyncClient, "post", _post)
    result = await listenbrainz.get_similar_artists_many(["a", "a", "b", "", "a"])
    assert set(result) == {"a", "b"}
    assert calls["n"] == 2


async def test_ping_reports_down_on_transport_failure(mocker):
    _patch_post(mocker, httpx.ConnectError("no route"))
    assert await listenbrainz.ping() == "down"


async def test_ping_reports_degraded_on_error_status(mocker):
    _patch_post(mocker, _Resp(502))
    assert await listenbrainz.ping() == "degraded"


async def test_ping_reports_ok(mocker):
    _patch_post(mocker, _Resp(200, []))
    assert await listenbrainz.ping() == "ok"
