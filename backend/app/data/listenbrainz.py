"""ListenBrainz client — the aggregate collaborative signal.

The preliminary design named Last.fm as the source of collaborative evidence.
ListenBrainz is used instead, for three reasons that matter to this project
specifically:

1. **No API key.** Last.fm requires per-developer key registration; ListenBrainz's
   labs endpoints are open, which keeps NextTrack's "clone and run, no credentials"
   property intact (the same reason ``ytmusicapi`` replaced the YouTube Data API).
2. **MBID-native.** ListenBrainz similarity is keyed on MusicBrainz identifiers, so
   it joins directly onto the identifiers the rest of the pipeline already carries.
   Last.fm is keyed on (artist, track) name strings and would have required a second,
   lossy name-matching layer.
3. **Aggregate, not personal.** The endpoint returns *artist-level co-listening
   similarity computed over the whole ListenBrainz population*. NextTrack sends one
   artist MBID and receives a ranked list; no user, session, or listening history is
   transmitted, so borrowing collaborative evidence does not weaken the statelessness
   or privacy guarantee.

Coverage is partial (long-tail artists return nothing), so every failure mode —
unknown artist, HTTP error, outage — degrades to "no collaborative evidence" rather
than raising. The recommender then falls back to the content-based score alone.
"""
import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# artist MBID -> {similar artist MBID: raw co-listening score}. Objective, per-artist
# facts identical for every user, so caching them stores nothing about a user.
_similar_cache: dict[str, dict[str, float]] = {}


def clear_cache() -> None:
    """Reset the per-artist similarity cache (used by tests)."""
    _similar_cache.clear()


def cache_size() -> int:
    """Number of artists with cached similarity data."""
    return len(_similar_cache)


def _parse(payload: object) -> dict[str, float]:
    """Map a labs-API response into {artist_mbid: score}, ignoring malformed rows."""
    if not isinstance(payload, list):
        return {}
    similar: dict[str, float] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        mbid = row.get("artist_mbid")
        score = row.get("score")
        if not mbid or score is None:
            continue
        try:
            similar[str(mbid)] = float(score)
        except (TypeError, ValueError):
            continue
    return similar


async def get_similar_artists(artist_mbid: str) -> dict[str, float]:
    """Return {similar artist MBID: co-listening score} for an artist.

    An empty dict means "no collaborative evidence available" — an unknown artist, a
    long-tail artist below the algorithm's listener threshold, or an outage. All three
    are handled identically by the caller, which is the point: the collaborative stage
    is an enhancement, never a dependency.
    """
    if not artist_mbid:
        return {}
    cached = _similar_cache.get(artist_mbid)
    if cached is not None:
        return cached

    payload = [
        {
            "artist_mbids": [artist_mbid],
            "algorithm": settings.LISTENBRAINZ_ARTIST_ALGORITHM,
        }
    ]
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            resp = await client.post(settings.LISTENBRAINZ_SIMILAR_ARTISTS_URL, json=payload)
    except Exception as exc:  # noqa: BLE001 - any transport failure means "no evidence"
        logger.warning("ListenBrainz unreachable for artist %s: %s", artist_mbid, exc)
        return {}

    if resp.status_code != 200:
        logger.debug(
            "ListenBrainz returned %s for artist %s", resp.status_code, artist_mbid
        )
        return {}

    try:
        similar = _parse(resp.json())
    except ValueError as exc:
        logger.warning("Malformed ListenBrainz payload for %s: %s", artist_mbid, exc)
        return {}

    _similar_cache[artist_mbid] = similar
    return similar


async def get_similar_artists_many(artist_mbids: list[str]) -> dict[str, dict[str, float]]:
    """Fetch similarity for several artists concurrently, de-duplicating the input."""
    unique = list(dict.fromkeys(m for m in artist_mbids if m))
    results = await asyncio.gather(*(get_similar_artists(m) for m in unique))
    return dict(zip(unique, results, strict=True))


async def ping() -> str:
    """Probe ListenBrainz reachability for /health: ok | degraded | down."""
    payload = [
        {
            "artist_mbids": [settings.LISTENBRAINZ_PING_ARTIST_MBID],
            "algorithm": settings.LISTENBRAINZ_ARTIST_ALGORITHM,
        }
    ]
    try:
        async with httpx.AsyncClient(timeout=settings.HEALTH_PING_TIMEOUT) as client:
            resp = await client.post(settings.LISTENBRAINZ_SIMILAR_ARTISTS_URL, json=payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ListenBrainz ping failed: %s", exc)
        return "down"
    return "ok" if resp.status_code == 200 else "degraded"
