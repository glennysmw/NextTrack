"""Process-local in-memory cache for fetched features and YouTube lookups.

This is a deliberate, bounded performance optimisation, not session state: it
holds only objective, track-keyed facts (acoustic features, MBID -> video id)
that are identical for every user. The server still stores nothing *about a user*
between requests, so the statelessness/privacy guarantee is intact. Redis-backed
caching is deferred to Phase 2.
"""
import time

from app.config import settings

_features: dict[str, dict] = {}
_youtube: dict[str, str] = {}
# genre tag -> (expiry timestamp, candidate metadata list)
_candidates: dict[str, tuple[float, list[dict]]] = {}
_hits = 0
_misses = 0


def get_features(mbid: str) -> dict | None:
    """Return the cached feature payload for an MBID, or None on a miss."""
    global _hits, _misses
    value = _features.get(mbid)
    if value is None:
        _misses += 1
    else:
        _hits += 1
    return value


def set_features(mbid: str, features: dict) -> None:
    """Store a feature payload for an MBID."""
    _features[mbid] = features


def get_youtube(mbid: str) -> str | None:
    """Return the cached YouTube video id for an MBID, or None on a miss."""
    global _hits, _misses
    value = _youtube.get(mbid)
    if value is None:
        _misses += 1
    else:
        _hits += 1
    return value


def set_youtube(mbid: str, video_id: str) -> None:
    """Store a YouTube video id for an MBID."""
    _youtube[mbid] = video_id


def get_candidates(tag: str) -> list[dict] | None:
    """Return the cached candidate pool for a genre tag, or None on a miss/expiry.

    This cache does more than save round trips. MusicBrainz's tag search is *not
    stable*: repeated `search_recordings(tag=…)` calls return different result sets,
    because thousands of recordings tie on relevance and the tie order is arbitrary.
    Measured during development, two consecutive searches for "grunge" shared **zero**
    of their fifty results. Without a stable pool, two identical /recommend requests
    can legitimately return different tracks, which contradicts the reproducibility
    that a stateless API is supposed to offer. Holding the pool for a bounded window
    makes repeated requests reproducible and cuts the dominant latency cost (three
    rate-limited MusicBrainz searches per recommendation).

    It stores no user data: a genre's candidate list is a public, per-tag fact,
    identical for every caller.
    """
    global _hits, _misses
    entry = _candidates.get(tag)
    if entry is None:
        _misses += 1
        return None
    expires_at, candidates = entry
    if time.monotonic() >= expires_at:
        del _candidates[tag]
        _misses += 1
        return None
    _hits += 1
    return candidates


def set_candidates(tag: str, candidates: list[dict]) -> None:
    """Store a genre's candidate pool with the configured time-to-live."""
    _candidates[tag] = (time.monotonic() + settings.CANDIDATE_CACHE_TTL_SECONDS, candidates)


def stats() -> dict:
    """Return cache size and hit/miss counters for the /health endpoint."""
    return {
        "feature_size": len(_features),
        "youtube_size": len(_youtube),
        "candidate_pools": len(_candidates),
        "hits": _hits,
        "misses": _misses,
    }


def clear() -> None:
    """Reset the cache and counters (used by tests)."""
    global _hits, _misses
    _features.clear()
    _youtube.clear()
    _candidates.clear()
    _hits = 0
    _misses = 0
