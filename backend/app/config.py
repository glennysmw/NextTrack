"""Application settings and environment configuration."""
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Central configuration. Business code reads constants from here, not literals."""

    APP_NAME = "NextTrack"
    VERSION = "0.1.0"

    # History bounds (a recommend request carries the listening history)
    MIN_HISTORY = 1
    MAX_HISTORY = 20

    # Candidate retrieval
    CANDIDATE_POOL_SIZE = 50
    MAX_YOUTUBE_ATTEMPTS = 5
    # How long a genre's candidate pool is held. MusicBrainz's tag search is not
    # stable between calls, so this window is what makes repeated identical requests
    # reproducible; it also removes three rate-limited searches from a warm request.
    CANDIDATE_CACHE_TTL_SECONDS = 3600.0

    # MusicBrainz
    MUSICBRAINZ_USER_AGENT = ("NextTrack", "0.1", "https://example.com/contact")
    MUSICBRAINZ_RATE_LIMIT_SECONDS = 1.0

    # AcousticBrainz
    ACOUSTICBRAINZ_BASE_URL = "https://acousticbrainz.org/api/v1"

    # ListenBrainz — aggregate (population-level) artist co-listening similarity.
    # Open endpoint, no API key; see app/data/listenbrainz.py for why this replaced
    # the originally-planned Last.fm integration.
    LISTENBRAINZ_SIMILAR_ARTISTS_URL = (
        "https://labs.api.listenbrainz.org/similar-artists/json"
    )
    LISTENBRAINZ_ARTIST_ALGORITHM = (
        "session_based_days_7500_session_300_contribution_5_"
        "threshold_10_limit_100_filter_True_skip_30"
    )
    # Queen — a high-coverage artist, used only to probe reachability on /health.
    LISTENBRAINZ_PING_ARTIST_MBID = "0383dadf-2a4e-4d10-a46a-e9e041da8eb3"

    # Cascade hybrid weights
    # Collaborative share of the blended relevance score (0 = content only).
    COLLAB_WEIGHT = 0.3
    # MMR relevance/diversity trade-off (1.0 = pure relevance, no diversity stage).
    MMR_LAMBDA = 0.7
    # How many re-ranked candidates the engine produces before playback resolution.
    RERANK_LIST_SIZE = 10

    # Playback is resolved via YouTube Music's internal API (ytmusicapi): no API key
    # and no per-day quota, so no YouTube Data API configuration is needed here.

    # Tempo normalisation range (BPM)
    TEMPO_MIN = 40
    TEMPO_MAX = 200

    # Loudness normalisation range (dB)
    LOUDNESS_MIN_DB = -60.0
    LOUDNESS_MAX_DB = 0.0

    # External call timeout (seconds)
    HTTP_TIMEOUT = 8.0
    # A bulk AcousticBrainz request carries up to 25 recordings and legitimately takes
    # far longer than a single lookup; the per-call timeout would otherwise abort work
    # that was about to succeed, costing 25 tracks their acoustic data at a time.
    BULK_HTTP_TIMEOUT = 30.0
    HEALTH_PING_TIMEOUT = 4.0

    # Comma-separated origins via env for production; defaults to local dev servers.
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
        ).split(",")
        if origin.strip()
    ]
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


settings = Settings()
