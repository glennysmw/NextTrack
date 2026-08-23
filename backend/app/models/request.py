"""Inbound request models (Pydantic v2)."""
import re

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings

# Canonical MusicBrainz Identifier shape (UUID v4-ish, 8-4-4-4-12 hex).
_MBID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def is_valid_mbid(value: str) -> bool:
    """Return True if `value` is a syntactically valid MusicBrainz Identifier.

    Surrounding whitespace is tolerated — but only because `normalise_mbid` removes it
    before the value is used. Validating a *stripped* string and then passing the
    *unstripped* one downstream was a real defect: a padded identifier passed this
    check, then reached musicbrainzngs, which retried eight times before failing with
    "URL can't contain control characters" and surfaced as a 503 "MusicBrainz
    unavailable" — a slow, misleading server error for what is a client input problem.
    """
    return bool(_MBID_RE.match(value.strip())) if isinstance(value, str) else False


def normalise_mbid(value: str) -> str:
    """Return the canonical form of an already-validated identifier."""
    return value.strip().lower()


class SearchRequest(BaseModel):
    """Search for a recording.

    When `artist` is supplied (e.g. a seed-track click, which knows the artist), the
    backend issues a *fielded* MusicBrainz query that pins results to the official
    recording instead of the cover/parody noise a free-text query returns.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="Free-text query, or the recording title when artist is set")
    artist: str | None = Field(default=None, description="Optional artist to scope the search to")
    limit: int = Field(default=10, ge=1, le=50)


class ResolveRequest(BaseModel):
    """Resolve a played track (title + artist) to its MusicBrainz id."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1)
    artist: str = Field(..., min_length=1)


class RecommendParams(BaseModel):
    """Tunable parameters that constrain a recommendation."""

    model_config = ConfigDict(extra="forbid")

    tempo_range: tuple[int, int] = Field(
        default=(settings.TEMPO_MIN, settings.TEMPO_MAX)
    )
    exclude_artists: list[str] = Field(default_factory=list)
    exclude_tracks: list[str] = Field(default_factory=list)


class RecommendRequest(BaseModel):
    """A self-contained recommendation request carrying the full session history."""

    model_config = ConfigDict(extra="forbid")

    track_history: list[str] = Field(..., description="Ordered list of MBIDs")
    params: RecommendParams = Field(default_factory=RecommendParams)
