"""Playback resolution via YouTube Music's internal API (``ytmusicapi``).

Why not the official YouTube Data API v3? Its ``search.list`` endpoint costs 100
quota units per call against a default budget of 10,000 units/day — roughly 100
searches per day. NextTrack resolves a video per search hit *and* per recommendation
candidate, so that budget is exhausted almost immediately and every subsequent call
returns HTTP 429 ("YouTube unavailable"). ``ytmusicapi`` talks to YouTube Music's
internal API instead: no API key, no quota, and its "songs" results are the official
artist catalogue (label-provided audio), so the artist's official version ranks above
covers, parodies, karaoke, and live cuts — exactly the behaviour we want.

``ytmusicapi`` is synchronous (it uses ``requests``), so every public function
offloads to a worker thread to keep the async call-graph non-blocking, mirroring the
MusicBrainz client. A hung socket is bounded by the global default timeout that
``musicbrainz.configure()`` installs at startup.
"""
import asyncio
import logging
from typing import Literal

from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)

# Filters are tried in order: official catalogue songs first, then music videos for
# tracks that only exist as videos (e.g. some classical/instrumental pieces).
_SEARCH_FILTERS: tuple[Literal["songs"], Literal["videos"]] = ("songs", "videos")
_RESULTS_PER_FILTER = 5

# A single unauthenticated client is reused across requests. Public search needs no
# auth; building it performs no network I/O. Lazily constructed and guarded so an
# init failure degrades to a normal "unavailable" path rather than crashing startup.
_client: YTMusic | None = None


def _get_client() -> YTMusic:
    """Return the shared YTMusic client, constructing it on first use."""
    global _client
    if _client is None:
        _client = YTMusic()
    return _client


def _first_video_id(results: list[dict]) -> str | None:
    """Return the first result's videoId, skipping entries that lack one."""
    for item in results:
        video_id = item.get("videoId")
        if video_id:
            return video_id
    return None


def _search_sync(query: str) -> str | None:
    """Resolve the official song's videoId, falling back to a music video."""
    client = _get_client()
    for filt in _SEARCH_FILTERS:
        video_id = _first_video_id(
            client.search(query, filter=filt, limit=_RESULTS_PER_FILTER)
        )
        if video_id:
            return video_id
    return None


async def search_video_id(query: str) -> str | None:
    """Return the official YouTube video id for a query, or None if nothing matches."""
    try:
        return await asyncio.to_thread(_search_sync, query)
    except Exception as exc:
        logger.error("YouTube Music search failed for %r: %s", query, exc)
        raise ConnectionError("YouTube unavailable") from exc


def _best_thumbnail(item: dict) -> str | None:
    """Return the largest thumbnail URL for a result.

    Used as-is: YouTube Music song thumbnails reject an arbitrary size override
    (their "=wN-hN-l90-rj" suffix only works at the offered sizes), and the largest
    offered size already exceeds the UI's display size.
    """
    thumbs = item.get("thumbnails") or []
    if not thumbs:
        return None
    return thumbs[-1].get("url")  # ytmusicapi orders smallest -> largest


def _parse_song(item: dict) -> dict | None:
    """Normalise a ytmusicapi 'song' result into NextTrack's discover shape."""
    video_id = item.get("videoId")
    if not video_id:
        return None
    artists = [a.get("name", "") for a in (item.get("artists") or []) if a.get("name")]
    album = item.get("album")
    return {
        "title": item.get("title", "Unknown"),
        "artist": ", ".join(artists) if artists else "Unknown",
        "album": album.get("name") if isinstance(album, dict) else None,
        "thumbnail": _best_thumbnail(item),
        "video_id": video_id,
    }


def _search_songs_sync(query: str, limit: int) -> list[dict]:
    # ytmusicapi treats `limit` as a floor (it returns a full page), so cap it here.
    songs = _get_client().search(query, filter="songs", limit=limit)
    parsed = (_parse_song(s) for s in songs)
    return [p for p in parsed if p is not None][:limit]


async def search_songs(query: str, limit: int = 10) -> list[dict]:
    """Search YouTube Music for official songs (title, artist, album art, video id).

    This is the user-facing search: YouTube Music ranks the official artist track
    first, so the result list is accurate and playable, unlike a MusicBrainz
    free-text search which scores covers/parodies just as highly.
    """
    try:
        return await asyncio.to_thread(_search_songs_sync, query, limit)
    except Exception as exc:
        logger.error("YouTube Music song search failed for %r: %s", query, exc)
        raise ConnectionError("YouTube unavailable") from exc


async def ping() -> str:
    """Probe YouTube Music reachability for /health: ok | down."""
    try:
        await asyncio.to_thread(
            lambda: _get_client().search("test", filter="songs", limit=1)
        )
        return "ok"
    except Exception as exc:
        logger.warning("YouTube Music ping failed: %s", exc)
        return "down"
