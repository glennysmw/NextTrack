"""Tests for the AcousticBrainz client, focusing on the bulk path and its failures.

Bulk fetching exists for a measured reason: resolving ~50 candidates one request at a
time meant roughly a hundred concurrent requests to a single host and dominated the
cost of a cold recommendation. Because the whole service is largely decommissioned,
the failure paths matter more than the happy path — a miss must be indistinguishable
from an outage to the caller, and neither may raise.
"""
import httpx
import pytest

from app.data import acousticbrainz
from app.engine import features as feat

MBID_A = "cdd611f4-f270-405b-910b-fddf60dff322"
MBID_B = "46fe768c-7b38-4147-9f02-815b9f0759e2"

LOW_PAYLOAD = {
    MBID_A: {"0": {"rhythm": {"bpm": 148.5}, "tonal": {"key_key": "Db", "key_scale": "minor"},
                   "lowlevel": {"average_loudness": 0.81}}},
    # The bulk response carries this unrelated key alongside the results.
    "mbid_mapping": {},
}
HIGH_PAYLOAD = {
    MBID_A: {
        "0": {
            "highlevel": {
                "mood_aggressive": {"all": {"aggressive": 0.9}},
                "mood_party": {"all": {"party": 0.8}},
                "mood_relaxed": {"all": {"relaxed": 0.1}},
                "danceability": {"all": {"danceable": 0.02}},
            }
        }
    },
}


class _Resp:
    def __init__(self, status_code: int, payload=None, bad_json: bool = False):
        self.status_code = status_code
        self._payload = payload
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


def _patch_get(mocker, handler):
    async def _get(self, url, **kwargs):
        return handler(url, kwargs)

    mocker.patch.object(httpx.AsyncClient, "get", _get)


def _both_levels(low=LOW_PAYLOAD, high=HIGH_PAYLOAD, status=200):
    def handler(url, kwargs):
        return _Resp(status, high if url.endswith("high-level") else low)

    return handler


async def test_bulk_parses_low_and_high_level_into_one_record(mocker):
    _patch_get(mocker, _both_levels())
    result = await acousticbrainz.get_features_bulk([MBID_A])
    record = result[MBID_A]
    assert record["tempo"] == pytest.approx(148.5)
    assert record["key"] == "Db"          # canonicalisation happens downstream
    assert record["mode"] == "minor"
    assert record["loudness"] == pytest.approx(0.81)
    # mean(aggressive 0.9, party 0.8, 1 - relaxed 0.1) = 0.8667
    assert record["energy"] == pytest.approx((0.9 + 0.8 + 0.9) / 3)


async def test_bulk_returns_none_for_a_recording_with_no_data(mocker):
    _patch_get(mocker, _both_levels())
    result = await acousticbrainz.get_features_bulk([MBID_A, MBID_B])
    assert result[MBID_B] is None


async def test_bulk_ignores_the_mbid_mapping_key(mocker):
    _patch_get(mocker, _both_levels())
    result = await acousticbrainz.get_features_bulk([MBID_A])
    assert "mbid_mapping" not in result


async def test_missing_high_level_falls_back_to_the_default_energy(mocker):
    def handler(url, kwargs):
        return _Resp(404) if url.endswith("high-level") else _Resp(200, LOW_PAYLOAD)

    _patch_get(mocker, handler)
    result = await acousticbrainz.get_features_bulk([MBID_A])
    assert result[MBID_A]["energy"] == pytest.approx(feat.DEFAULT_ENERGY)
    # …but the low-level data it *did* get is still used.
    assert result[MBID_A]["tempo"] == pytest.approx(148.5)


@pytest.mark.parametrize(
    "handler",
    [
        lambda _url, _kwargs: _Resp(503),
        lambda _url, _kwargs: _Resp(200, bad_json=True),
        lambda _url, _kwargs: _Resp(200, ["not", "a", "dict"]),
    ],
    ids=["http_error", "bad_json", "wrong_shape"],
)
async def test_bulk_never_raises_on_a_bad_response(mocker, handler):
    _patch_get(mocker, handler)
    assert await acousticbrainz.get_features_bulk([MBID_A]) == {MBID_A: None}


async def test_bulk_never_raises_on_a_transport_failure(mocker):
    async def _get(self, url, **kwargs):
        raise httpx.ConnectError("no route")

    mocker.patch.object(httpx.AsyncClient, "get", _get)
    assert await acousticbrainz.get_features_bulk([MBID_A]) == {MBID_A: None}


async def test_bulk_batches_large_id_lists(mocker):
    """60 ids must become 3 batches × 2 levels, not 120 requests."""
    calls: list[str] = []

    async def _get(self, url, **kwargs):
        calls.append(kwargs["params"]["recording_ids"])
        return _Resp(200, {})

    mocker.patch.object(httpx.AsyncClient, "get", _get)
    await acousticbrainz.get_features_bulk([f"id-{i}" for i in range(60)])
    assert len(calls) == 6
    assert max(len(c.split(";")) for c in calls) <= 25


async def test_bulk_deduplicates_and_drops_empty_ids(mocker):
    calls: list[str] = []

    async def _get(self, url, **kwargs):
        calls.append(kwargs["params"]["recording_ids"])
        return _Resp(200, {})

    mocker.patch.object(httpx.AsyncClient, "get", _get)
    result = await acousticbrainz.get_features_bulk([MBID_A, MBID_A, "", MBID_B])
    assert set(result) == {MBID_A, MBID_B}
    assert calls[0].split(";") == [MBID_A, MBID_B]


async def test_empty_input_makes_no_requests(mocker):
    called = mocker.patch.object(httpx.AsyncClient, "get")
    assert await acousticbrainz.get_features_bulk([]) == {}
    called.assert_not_called()


# --- Energy derivation ------------------------------------------------------------
# The original implementation used the danceability classifier as the energy proxy,
# with a "verify field name" note attached. Verified: the field name was correct and
# the choice of field was not. "Mr. Brightside" scores 0.02 danceable while scoring
# 0.98 aggressive, 0.86 party and 0.03 relaxed — so the feature the engine ranked on,
# and displayed to the user as ENERGY, was close to the opposite of energy for guitar
# music. These tests pin the replacement.


def _high(**classifiers) -> dict:
    return {"highlevel": {name: {"all": value} for name, value in classifiers.items()}}


def test_energy_averages_the_three_mood_classifiers():
    high = _high(
        mood_aggressive={"aggressive": 0.9},
        mood_party={"party": 0.6},
        mood_relaxed={"relaxed": 0.3},
    )
    assert acousticbrainz._energy(high) == pytest.approx((0.9 + 0.6 + 0.7) / 3)


def test_energy_uses_whichever_classifiers_are_present():
    high = _high(mood_aggressive={"aggressive": 0.8})
    assert acousticbrainz._energy(high) == pytest.approx(0.8)


def test_a_loud_aggressive_rock_track_is_not_scored_as_low_energy():
    """The regression itself: danceability said 0.02, the truth is high energy."""
    high = _high(
        danceability={"danceable": 0.024},
        mood_aggressive={"aggressive": 0.983},
        mood_party={"party": 0.863},
        mood_relaxed={"relaxed": 0.034},
    )
    assert acousticbrainz._energy(high) > 0.9


def test_energy_falls_back_to_danceability_when_no_moods_are_present():
    assert acousticbrainz._energy(_high(danceability={"danceable": 0.42})) == pytest.approx(0.42)


def test_energy_falls_back_to_the_default_with_no_high_level_data():
    assert acousticbrainz._energy(None) == pytest.approx(feat.DEFAULT_ENERGY)
    assert acousticbrainz._energy({}) == pytest.approx(feat.DEFAULT_ENERGY)
    assert acousticbrainz._energy(_high()) == pytest.approx(feat.DEFAULT_ENERGY)


@pytest.mark.parametrize("bad", [1.4, -0.2, "loud", None])
def test_energy_ignores_out_of_range_or_unparseable_values(bad):
    high = _high(mood_aggressive={"aggressive": bad}, mood_party={"party": 0.7})
    assert acousticbrainz._energy(high) == pytest.approx(0.7)
