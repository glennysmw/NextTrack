"""AcousticBrainz client.

AcousticBrainz was largely decommissioned in 2022, so most tracks return 404.
A missing track is the *normal* case, signalled by returning None; the recommender
then substitutes default acoustic features and flags the track as fallback.
"""
import asyncio
import logging

import httpx

from app.config import settings
from app.engine import features as feat

logger = logging.getLogger(__name__)

# A well-covered recording (The Killers - Mr. Brightside) used to probe health.
_PING_MBID = "cdd611f4-f270-405b-910b-fddf60dff322"

# The bulk endpoints accept a semicolon-separated id list. Batching matters a great
# deal here: a recommendation resolves ~50 candidates, which as individual calls is
# ~100 concurrent requests to a single decommissioned-but-still-serving host and was
# measured as the dominant cost of a cold request. In batches it is four.
_BULK_BATCH_SIZE = 25
_BULK_ATTEMPTS = 2
_BULK_RETRY_DELAY_SECONDS = 1.0

# The bulk payload nests each recording's submissions under numeric string keys and
# carries an unrelated "mbid_mapping" entry alongside the results.
_FIRST_SUBMISSION = "0"
_NON_RESULT_KEYS = {"mbid_mapping"}


def _as_float(value: object, default: float) -> float:
    """Coerce an untyped JSON value to float, falling back on anything unusable."""
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return default


def _energy(high: dict | None) -> float:
    """Estimate perceived energy in [0, 1] from the high-level mood classifiers.

    AcousticBrainz publishes no direct "energy" descriptor, so one has to be derived.
    The original implementation used the danceability classifier's `danceable`
    probability, carrying a "verify field name" note. Verified against live data, the
    field name was right and the *choice of field* was wrong: danceability measures
    whether a track invites dancing, which is close to orthogonal to energy for
    guitar music. The Killers' "Mr. Brightside" scores 0.02 danceable — while scoring
    0.98 aggressive, 0.86 party and 0.03 relaxed. Ranking it as a near-zero-energy
    track is simply incorrect, and it was also displayed to the user as "ENERGY 0.00".

    The replacement averages three mood classifiers that do bear on energy and that
    agree with each other on that example: aggressive, party, and the complement of
    relaxed. Averaging rather than picking one keeps a single mis-classification from
    dominating. Whatever subset of the three is present is used; if none is,
    danceability is still better than nothing, and the fixed default is the last
    resort.
    """
    if not high:
        return feat.DEFAULT_ENERGY
    highlevel = high.get("highlevel", {})

    def probability(classifier: str, label: str) -> float | None:
        """Return a classifier's probability for one label, or None if unusable."""
        raw = highlevel.get(classifier, {}).get("all", {}).get(label)
        if raw is None:
            return None
        value = _as_float(raw, -1.0)
        return value if 0.0 <= value <= 1.0 else None

    components: list[float] = []
    for classifier, label in (("mood_aggressive", "aggressive"), ("mood_party", "party")):
        value = probability(classifier, label)
        if value is not None:
            components.append(value)

    relaxed = probability("mood_relaxed", "relaxed")
    if relaxed is not None:
        components.append(1.0 - relaxed)

    if components:
        return sum(components) / len(components)

    danceable = probability("danceability", "danceable")
    return danceable if danceable is not None else feat.DEFAULT_ENERGY


def _parse(low: dict, high: dict | None) -> dict:
    """Map raw low-/high-level payloads into NextTrack's acoustic feature shape."""
    rhythm = low.get("rhythm", {})
    tonal = low.get("tonal", {})
    lowlevel = low.get("lowlevel", {})

    # average_loudness is already normalised to ~[0,1] by AcousticBrainz.
    loudness = lowlevel.get("average_loudness")
    if loudness is None:
        loudness = feat.DEFAULT_LOUDNESS

    return {
        "tempo": _as_float(rhythm.get("bpm"), feat.DEFAULT_TEMPO),
        "key": tonal.get("key_key", feat.DEFAULT_KEY),
        "mode": tonal.get("key_scale", feat.DEFAULT_MODE),
        "energy": _energy(high),
        "loudness": _as_float(loudness, feat.DEFAULT_LOUDNESS),
    }


async def get_features(mbid: str) -> dict | None:
    """Fetch acoustic features for an MBID, or None when AcousticBrainz has none."""
    low_url = f"{settings.ACOUSTICBRAINZ_BASE_URL}/{mbid}/low-level"
    high_url = f"{settings.ACOUSTICBRAINZ_BASE_URL}/{mbid}/high-level"
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            low_resp, high_resp = await asyncio.gather(
                client.get(low_url), client.get(high_url), return_exceptions=True
            )
    except Exception as exc:
        logger.error("AcousticBrainz request error for %s: %s", mbid, exc)
        raise ConnectionError("AcousticBrainz unavailable") from exc

    if not isinstance(low_resp, httpx.Response) or low_resp.status_code != 200:
        logger.debug("No AcousticBrainz low-level data for %s", mbid)
        return None

    high = None
    if isinstance(high_resp, httpx.Response) and high_resp.status_code == 200:
        high = high_resp.json()

    try:
        return _parse(low_resp.json(), high)
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("Failed to parse AcousticBrainz data for %s: %s", mbid, exc)
        return None


def _unwrap_bulk(payload: object) -> dict[str, dict]:
    """Flatten a bulk response into {mbid: first submission}, ignoring metadata keys."""
    if not isinstance(payload, dict):
        return {}
    out: dict[str, dict] = {}
    for mbid, submissions in payload.items():
        if mbid in _NON_RESULT_KEYS or not isinstance(submissions, dict):
            continue
        record = submissions.get(_FIRST_SUBMISSION)
        if isinstance(record, dict):
            out[mbid] = record
    return out


async def _fetch_bulk(
    client: httpx.AsyncClient, level: str, batch: list[str]
) -> dict[str, dict]:
    """Fetch one batch from a bulk endpoint, retrying a transient failure once.

    A batch carries up to 25 recordings, so losing one to a timeout silently costs 25
    tracks their acoustic detail — and, when refreshing a stored corpus, silently
    *deletes* it. Observed in practice: three batches timed out during a corpus refresh
    and took roughly seventy-five tracks' data with them. One retry with a short backoff
    recovers the common case; a batch that still fails returns no data, which callers
    already treat as "AcousticBrainz has nothing".
    """
    url = f"{settings.ACOUSTICBRAINZ_BASE_URL}/{level}"
    params = {"recording_ids": ";".join(batch)}
    for attempt in range(_BULK_ATTEMPTS):
        try:
            resp = await client.get(url, params=params)
        except Exception as exc:  # noqa: BLE001 - a miss and an outage are handled alike
            logger.warning(
                "AcousticBrainz %s batch failed (%d/%d): %s",
                level, attempt + 1, _BULK_ATTEMPTS, type(exc).__name__,
            )
            await asyncio.sleep(_BULK_RETRY_DELAY_SECONDS)
            continue
        if resp.status_code != 200:
            logger.debug("AcousticBrainz %s batch returned %s", level, resp.status_code)
            return {}
        try:
            return _unwrap_bulk(resp.json())
        except ValueError as exc:
            logger.warning("Malformed AcousticBrainz %s batch: %s", level, exc)
            return {}
    return {}


async def get_features_bulk(mbids: list[str]) -> dict[str, dict | None]:
    """Fetch acoustic features for many recordings using the bulk endpoints.

    Returns an entry for every requested MBID; ``None`` means AcousticBrainz has no
    data for it, which is the common case since the service was largely decommissioned
    in 2022. Unlike ``get_features`` this never raises: the caller is resolving a
    candidate pool, and one unavailable batch should cost those candidates their
    acoustic detail, not cost the user a recommendation.
    """
    unique = list(dict.fromkeys(m for m in mbids if m))
    if not unique:
        return {}

    batches = [
        unique[start : start + _BULK_BATCH_SIZE]
        for start in range(0, len(unique), _BULK_BATCH_SIZE)
    ]
    async with httpx.AsyncClient(timeout=settings.BULK_HTTP_TIMEOUT) as client:
        responses = await asyncio.gather(
            *(_fetch_bulk(client, level, batch) for batch in batches for level in ("low-level", "high-level"))
        )

    low: dict[str, dict] = {}
    high: dict[str, dict] = {}
    for index, result in enumerate(responses):
        (low if index % 2 == 0 else high).update(result)

    return {
        mbid: (_parse(low[mbid], high.get(mbid)) if mbid in low else None)
        for mbid in unique
    }


async def ping() -> str:
    """Probe AcousticBrainz reachability for /health: ok | degraded | down."""
    url = f"{settings.ACOUSTICBRAINZ_BASE_URL}/{_PING_MBID}/low-level"
    try:
        async with httpx.AsyncClient(timeout=settings.HEALTH_PING_TIMEOUT) as client:
            resp = await client.get(url)
        return "ok" if resp.status_code == 200 else "degraded"
    except Exception as exc:
        logger.warning("AcousticBrainz ping failed: %s", exc)
        return "down"
