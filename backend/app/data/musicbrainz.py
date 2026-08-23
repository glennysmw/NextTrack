"""MusicBrainz client.

`musicbrainzngs` is synchronous, so every public function offloads to a worker
thread to keep the async call-graph non-blocking.

Genre note: recording-level folksonomy tags are almost always empty in MusicBrainz.
The reliable genre signal lives on the *artist*, so `get_recording` enriches each
track with its primary artist's tags (cached per artist to respect the rate limit).
"""
import asyncio
import logging
import re
import socket
import time

import musicbrainzngs

from app.config import settings

logger = logging.getLogger(__name__)

_HEALTH_DEGRADED_SECONDS = 2.0
_MAX_ARTIST_GENRES = 5

# MusicBrainz tags mix genres with housekeeping/place/era labels. Filter the latter
# so candidate retrieval searches on real genres, not "seattle" or "90s".
_NON_GENRE_TAGS = {
    "american", "british", "english", "usa", "uk", "united states", "u.s.a.",
    "german", "french", "canadian", "australian", "japanese", "irish", "swedish",
    "norwegian", "finnish", "dutch", "italian", "spanish", "brazilian",
    "seattle", "london", "new york", "los angeles", "chicago",
    "special purpose artist", "special purpose", "fixme or cleanup", "unknown",
    "male vocalists", "female vocalists", "male vocalist", "female vocalist",
    "favorites", "favourites", "seen live", "want to see live",
}
_DECADE_RE = re.compile(r"^(19|20)?\d0s$")  # 90s, 1990s, 2000s, …


def _looks_like_genre(name: str) -> bool:
    """Heuristic: keep plausible genre tags, drop place/era/housekeeping noise."""
    normalised = name.strip().lower()
    if not normalised or normalised in _NON_GENRE_TAGS:
        return False
    return not _DECADE_RE.match(normalised)


# artist MBID -> ranked genre list. Bounded by the number of distinct artists seen.
_artist_genre_cache: dict[str, list[str]] = {}


def clear_artist_cache() -> None:
    """Reset the per-artist genre cache (used by tests)."""
    _artist_genre_cache.clear()


def configure() -> None:
    """Set the MusicBrainz user agent and rate limit. Call once at startup."""
    name, version, contact = settings.MUSICBRAINZ_USER_AGENT
    musicbrainzngs.set_useragent(name, version, contact)
    musicbrainzngs.set_rate_limit(
        limit_or_interval=settings.MUSICBRAINZ_RATE_LIMIT_SECONDS, new_requests=1
    )
    # musicbrainzngs (urllib) exposes no per-call timeout, so a hung connection would
    # block a worker thread forever. A global default bounds it; httpx clients set
    # their own explicit timeouts and are unaffected.
    socket.setdefaulttimeout(settings.HTTP_TIMEOUT)


def _primary_artist(recording: dict) -> dict | None:
    """Return the first credited artist object (with its MBID), if any."""
    for credit in recording.get("artist-credit", []):
        if isinstance(credit, dict) and "artist" in credit:
            return credit["artist"]
    return None


def _parse_artist(recording: dict) -> str:
    """Extract a flattened artist name from a recording's artist-credit."""
    credit = recording.get("artist-credit", [])
    names = [c["artist"]["name"] for c in credit if isinstance(c, dict) and "artist" in c]
    return " ".join(names) if names else recording.get("artist-credit-phrase", "Unknown")


def _genres_from_tags(tags: list[dict]) -> list[str]:
    """Lowercase, filter, and de-duplicate a MusicBrainz tag-list into genres."""
    seen: dict[str, None] = {}
    for tag in tags:
        name = tag.get("name", "")
        if name and _looks_like_genre(name):
            seen.setdefault(name.strip().lower(), None)
    return list(seen)


def _parse_recording(recording: dict) -> dict:
    """Normalise a raw musicbrainzngs recording into NextTrack's shape."""
    releases = recording.get("release-list", [])
    length = recording.get("length")
    artist = _primary_artist(recording)
    return {
        "mbid": recording.get("id", ""),
        "title": recording.get("title", "Unknown"),
        "artist": _parse_artist(recording),
        # The primary artist's own MBID keys the ListenBrainz collaborative lookup.
        "artist_mbid": artist.get("id") if artist else None,
        "album": releases[0]["title"] if releases else None,
        "duration_seconds": int(int(length) / 1000) if length else None,
        # Recording-level tags are usually empty; artist tags are merged in later.
        "genres": _genres_from_tags(recording.get("tag-list", [])),
    }


def _artist_genres_sync(artist_id: str) -> list[str]:
    """Fetch (and cache) the primary artist's ranked genre tags."""
    if artist_id in _artist_genre_cache:
        return _artist_genre_cache[artist_id]
    try:
        artist = musicbrainzngs.get_artist_by_id(artist_id, includes=["tags"])["artist"]
    except Exception as exc:  # noqa: BLE001 - artist tags are best-effort enrichment
        logger.warning("Artist tag lookup failed for %s: %s", artist_id, exc)
        return []
    ranked = sorted(
        artist.get("tag-list", []),
        key=lambda t: int(t.get("count", 0) or 0),
        reverse=True,
    )
    genres = _genres_from_tags(ranked)[:_MAX_ARTIST_GENRES]
    _artist_genre_cache[artist_id] = genres
    return genres


def _lucene_escape(value: str) -> str:
    """Escape characters that would break a quoted Lucene phrase."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_search_query(query: str, artist: str | None) -> str:
    """Build the Lucene query MusicBrainz searches on.

    A free-text query like "The Killers Mr. Brightside" scores covers and parodies
    as highly as the original. Pinning the artist and recording fields instead
    surfaces the official recording (score 100) and drops the noise.
    """
    if artist and artist.strip():
        return (
            f'recording:"{_lucene_escape(query.strip())}" '
            f'AND artist:"{_lucene_escape(artist.strip())}"'
        )
    return query


def _search_recordings_sync(query: str, limit: int, artist: str | None) -> list[dict]:
    result = musicbrainzngs.search_recordings(
        query=_build_search_query(query, artist), limit=limit
    )
    return [_parse_recording(r) for r in result.get("recording-list", [])]


def _search_by_tag_sync(tag: str, limit: int) -> list[dict]:
    result = musicbrainzngs.search_recordings(tag=tag, limit=limit)
    return [_parse_recording(r) for r in result.get("recording-list", [])]


def _get_recording_sync(mbid: str) -> dict | None:
    result = musicbrainzngs.get_recording_by_id(
        mbid, includes=["artists", "releases", "tags"]
    )
    recording = result.get("recording")
    if not recording:
        return None
    parsed = _parse_recording(recording)
    artist = _primary_artist(recording)
    if artist and artist.get("id"):
        # Merge artist genres after any recording tags, preserving order/dedup.
        merged = dict.fromkeys(parsed["genres"])
        for genre in _artist_genres_sync(artist["id"]):
            merged.setdefault(genre, None)
        parsed["genres"] = list(merged)
    return parsed


async def search_recordings(
    query: str, limit: int, artist: str | None = None
) -> list[dict]:
    """Recording search. Pass `artist` to scope to the official recording."""
    try:
        return await asyncio.to_thread(_search_recordings_sync, query, limit, artist)
    except Exception as exc:  # musicbrainzngs raises several WebServiceError subtypes
        logger.error("MusicBrainz search failed: %s", exc)
        raise ConnectionError("MusicBrainz unavailable") from exc


async def search_by_tag(tag: str, limit: int) -> list[dict]:
    """Retrieve recordings carrying a given folksonomy tag/genre."""
    try:
        return await asyncio.to_thread(_search_by_tag_sync, tag, limit)
    except Exception as exc:
        logger.error("MusicBrainz tag search failed for %r: %s", tag, exc)
        raise ConnectionError("MusicBrainz unavailable") from exc


async def get_recording(mbid: str) -> dict | None:
    """Fetch metadata (incl. tags) for a single recording, or None if not found."""
    try:
        return await asyncio.to_thread(_get_recording_sync, mbid)
    except musicbrainzngs.ResponseError:
        logger.warning("MusicBrainz has no recording for MBID %s", mbid)
        return None
    except Exception as exc:
        logger.error("MusicBrainz lookup failed for %s: %s", mbid, exc)
        raise ConnectionError("MusicBrainz unavailable") from exc


def _ping_sync() -> str:
    start = time.perf_counter()
    musicbrainzngs.search_recordings(query="test", limit=1)
    elapsed = time.perf_counter() - start
    return "degraded" if elapsed > _HEALTH_DEGRADED_SECONDS else "ok"


async def ping() -> str:
    """Probe MusicBrainz reachability for /health: ok | degraded | down."""
    try:
        return await asyncio.to_thread(_ping_sync)
    except Exception as exc:
        logger.warning("MusicBrainz ping failed: %s", exc)
        return "down"
