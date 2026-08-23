"""Outbound response models (Pydantic v2)."""
from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    """A single playable track from search or Today's Top 5.

    `track_id` carries the YouTube video id here; the MusicBrainz id needed for
    recommendations is resolved lazily (POST /resolve) when the track is played.
    """

    track_id: str
    title: str
    artist: str
    album: str | None = None
    thumbnail: str | None = None
    youtube_video_id: str
    duration_seconds: int | None = None


class SearchResponse(BaseModel):
    """Search / Top-tracks endpoint payload."""

    results: list[SearchResultItem]


class ResolveResponse(BaseModel):
    """Maps a played track to its MusicBrainz id (null when none is found)."""

    track_id: str | None = None


class RecommendationFeatures(BaseModel):
    """Human-facing feature summary for the recommended track."""

    tempo: float
    key: str
    energy: float
    genres: list[str]


class RecommendResponse(BaseModel):
    """A single recommended next track plus its rationale."""

    track_id: str
    title: str
    artist: str
    youtube_video_id: str
    score: float = Field(..., ge=0.0, le=1.0)
    rationale: str
    features: RecommendationFeatures
    limited_acoustic_data: bool


class CacheStats(BaseModel):
    """In-memory cache counters surfaced on /health."""

    feature_size: int
    youtube_size: int
    candidate_pools: int
    hits: int
    misses: int


class SourcesStatus(BaseModel):
    """Reachability of each upstream data source."""

    musicbrainz: str
    acousticbrainz: str
    youtube: str
    listenbrainz: str


class HealthResponse(BaseModel):
    """Health endpoint payload."""

    status: str
    version: str
    cache: CacheStats
    sources: SourcesStatus
