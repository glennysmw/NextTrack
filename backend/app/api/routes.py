"""API routes for search, top tracks, resolve, recommend, and health."""
import asyncio
import datetime
import logging

from fastapi import APIRouter, HTTPException

from app import daily
from app.config import settings
from app.data import acousticbrainz, cache, listenbrainz, musicbrainz, youtube
from app.engine import recommender
from app.models.request import (
    RecommendRequest,
    ResolveRequest,
    SearchRequest,
    is_valid_mbid,
    normalise_mbid,
)
from app.models.response import (
    CacheStats,
    HealthResponse,
    RecommendResponse,
    ResolveResponse,
    SearchResponse,
    SearchResultItem,
    SourcesStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["nexttrack"])

# Today's Top 5, cached per UTC day so we resolve the picks via YouTube Music once.
_top_cache: dict[str, list[SearchResultItem]] = {}


def _to_item(song: dict) -> SearchResultItem:
    """Build a search/top result item from a YouTube Music song.

    `track_id` is the video id; the MusicBrainz id is resolved lazily on play.
    """
    return SearchResultItem(
        track_id=song["video_id"],
        title=song["title"],
        artist=song["artist"],
        album=song.get("album"),
        thumbnail=song.get("thumbnail"),
        youtube_video_id=song["video_id"],
    )


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    """Search YouTube Music for official songs (accurate by title and/or artist)."""
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must not be empty")
    if req.artist and req.artist.strip():
        query = f"{req.artist.strip()} {query}"

    try:
        songs = await youtube.search_songs(query, req.limit)
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return SearchResponse(results=[_to_item(s) for s in songs])


@router.get("/top", response_model=SearchResponse)
async def top() -> SearchResponse:
    """Return Today's Top 5 — a daily-rotating set, resolved to official tracks."""
    day = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    if day in _top_cache:
        return SearchResponse(results=_top_cache[day])

    async def resolve_pick(title: str, artist: str) -> SearchResultItem | None:
        songs = await youtube.search_songs(f"{artist} {title}", 1)
        return _to_item(songs[0]) if songs else None

    try:
        resolved = await asyncio.gather(
            *(resolve_pick(title, artist) for title, artist in daily.todays_picks(5))
        )
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    items = [item for item in resolved if item is not None]
    _top_cache.clear()  # only ever hold the current day
    _top_cache[day] = items
    return SearchResponse(results=items)


@router.post("/resolve", response_model=ResolveResponse)
async def resolve(req: ResolveRequest) -> ResolveResponse:
    """Resolve a played track (title + artist) to its MusicBrainz id for recommending.

    Uses a fielded MusicBrainz query, which pins the official recording instead of
    the cover/parody noise a free-text search returns. Returns null if none is found
    (playback still works; only the recommendation step needs the id).
    """
    try:
        recs = await musicbrainz.search_recordings(req.title, 1, req.artist)
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ResolveResponse(track_id=recs[0]["mbid"] if recs else None)


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest) -> dict:
    """Return the next recommended track for a listening history."""
    history = req.track_history
    if not history:
        raise HTTPException(status_code=400, detail="track_history must not be empty")
    if len(history) > settings.MAX_HISTORY:
        raise HTTPException(
            status_code=400,
            detail=f"track_history exceeds maximum of {settings.MAX_HISTORY}",
        )
    invalid = [m for m in history if not is_valid_mbid(m)]
    if invalid:
        raise HTTPException(status_code=400, detail=f"malformed MBID(s): {invalid}")
    # Use the same canonical form that was validated. Passing the raw value on while
    # validating a normalised one is how a padded identifier used to reach the
    # MusicBrainz client and surface as a spurious 503.
    history = [normalise_mbid(m) for m in history]

    # RecommendationError propagates to the app-level handler in main.py, which
    # emits {"detail": <message>, "reason": <code>} — `detail` stays a string for
    # backward compatibility, `reason` is the only added field.
    try:
        return await recommender.recommend(history, req.params)
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report version, cache statistics, and live reachability of each data source."""
    mb_status, ab_status, yt_status, lb_status = await asyncio.gather(
        musicbrainz.ping(), acousticbrainz.ping(), youtube.ping(), listenbrainz.ping()
    )
    return HealthResponse(
        status="ok",
        version=settings.VERSION,
        cache=CacheStats(**cache.stats()),
        sources=SourcesStatus(
            musicbrainz=mb_status,
            acousticbrainz=ab_status,
            youtube=yt_status,
            listenbrainz=lb_status,
        ),
    )
