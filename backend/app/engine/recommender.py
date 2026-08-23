"""Core recommendation orchestration — a three-stage cascade hybrid.

Stage 1 (content, ``features`` + ``similarity``): build a feature vector per track,
average the history into a session centroid, score candidates by cosine similarity.
Stage 2 (collaborative, ``collaborative``): blend in ListenBrainz aggregate
artist co-listening affinity.
Stage 3 (diversity, ``diversity``): greedy MMR re-ranking against the listening
history, which suppresses near-duplicates of what was just played.

Every external call is async; MusicBrainz/YouTube outages surface as ConnectionError
(-> 503), while AcousticBrainz gaps degrade gracefully to fallback acoustics (the
common case, since the service is largely decommissioned) and ListenBrainz gaps
degrade to content-only scoring.

`PipelineConfig` makes each stage independently switchable. Production uses the
defaults from ``settings``; the offline evaluation harness varies it to run the
ablation study across engine configurations.
"""
import asyncio
import logging
from collections import Counter
from dataclasses import dataclass

import numpy as np

from app.config import settings
from app.data import acousticbrainz, cache, listenbrainz, musicbrainz, youtube
from app.engine import collaborative
from app.engine import features as feat
from app.engine.diversity import mmr_rank
from app.engine.rationale import generate_rationale
from app.engine.similarity import compute_centroid, cosine_score

logger = logging.getLogger(__name__)

_TOP_GENRE_TAGS = 3
_RESPONSE_GENRE_LIMIT = 5


@dataclass(frozen=True)
class PipelineConfig:
    """Which cascade stages run, and how strongly.

    ``use_collaborative=False`` or ``collab_weight=0`` disables stage 2;
    ``use_diversity=False`` or ``mmr_lambda=1.0`` disables stage 3. Both defaults come
    from settings, so the API always runs the full pipeline and only the evaluation
    harness constructs reduced configurations.
    """

    use_collaborative: bool = True
    use_diversity: bool = True
    collab_weight: float = settings.COLLAB_WEIGHT
    mmr_lambda: float = settings.MMR_LAMBDA
    list_size: int = settings.RERANK_LIST_SIZE

    @property
    def effective_collab_weight(self) -> float:
        return self.collab_weight if self.use_collaborative else 0.0

    @property
    def effective_lambda(self) -> float:
        return self.mmr_lambda if self.use_diversity else 1.0


DEFAULT_PIPELINE = PipelineConfig()


class RecommendationError(Exception):
    """A recommendation could not be produced.

    Carries a machine-readable `reason` (surfaced to the client) and the HTTP
    `status_code` the API layer should return.
    """

    def __init__(self, reason: str, message: str, status_code: int = 404) -> None:
        self.reason = reason
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def _safe_acoustic(mbid: str) -> dict | None:
    """Fetch acoustic features, treating any outage as a (common) fallback miss."""
    try:
        return await acousticbrainz.get_features(mbid)
    except ConnectionError:
        logger.warning("AcousticBrainz unavailable for %s; using fallback", mbid)
        return None


async def _resolve_track_features(mbid: str, metadata: dict | None = None) -> dict | None:
    """Resolve a track's full feature payload, fetching and caching on a miss.

    When `metadata` is supplied (e.g. from a candidate tag search) the MusicBrainz
    lookup is skipped and only AcousticBrainz is fetched — this keeps recommendation
    latency reasonable given MusicBrainz's 1 req/sec rate limit.
    """
    cached = cache.get_features(mbid)
    if cached is not None:
        return cached

    if metadata is None:
        metadata, acoustic = await asyncio.gather(
            musicbrainz.get_recording(mbid), _safe_acoustic(mbid)
        )
    else:
        acoustic = await _safe_acoustic(mbid)

    if metadata is None:
        logger.warning("Unresolvable MBID skipped: %s", mbid)
        return None

    return _build_payload(mbid, metadata, acoustic)


def _build_payload(mbid: str, metadata: dict, acoustic: dict | None) -> dict:
    """Assemble (and cache) one track's feature payload from its two data sources.

    A missing acoustic record is the normal case, not an error: AcousticBrainz was
    largely decommissioned in 2022. Fixed defaults stand in, and `used_fallback`
    carries that fact all the way out to the API response and the rationale, so a
    degraded match is visible rather than silent.
    """
    used_fallback = acoustic is None
    acoustic = acoustic or dict(feat.DEFAULT_ACOUSTIC)
    payload = {
        "mbid": mbid,
        "title": metadata["title"],
        "artist": metadata["artist"],
        "artist_mbid": metadata.get("artist_mbid"),
        "album": metadata.get("album"),
        "duration_seconds": metadata.get("duration_seconds"),
        "genres": metadata.get("genres", []),
        "tempo": float(acoustic["tempo"]),
        "key": feat.canonical_key(acoustic["key"]),
        "mode": str(acoustic["mode"]).lower(),
        "energy": float(acoustic["energy"]),
        "loudness": float(acoustic["loudness"]),
        "used_fallback": used_fallback,
    }
    cache.set_features(mbid, payload)
    return payload


async def _resolve_candidates(candidate_recs: list[dict]) -> list[dict]:
    """Resolve a whole candidate pool, fetching their acoustics in bulk.

    Candidates already carry their MusicBrainz metadata from the tag search, so the
    only outstanding lookup is AcousticBrainz. Fetching those one per candidate meant
    roughly a hundred concurrent requests to a single host and was the dominant cost
    of a cold recommendation; the bulk endpoints reduce it to four.
    """
    cached = {
        rec["mbid"]: payload
        for rec in candidate_recs
        if (payload := cache.get_features(rec["mbid"])) is not None
    }
    outstanding = [rec for rec in candidate_recs if rec["mbid"] not in cached]

    acoustics: dict[str, dict | None] = {}
    if outstanding:
        try:
            acoustics = await acousticbrainz.get_features_bulk(
                [rec["mbid"] for rec in outstanding]
            )
        except ConnectionError:
            logger.warning("AcousticBrainz bulk fetch failed; using fallback acoustics")

    resolved = []
    for rec in candidate_recs:
        payload = cached.get(rec["mbid"])
        if payload is None:
            payload = _build_payload(rec["mbid"], rec, acoustics.get(rec["mbid"]))
        resolved.append(payload)
    return resolved


def _top_genres(history: list[dict], n: int) -> list[str]:
    """Return the most common genre tags across the resolved history.

    Each genre counts at most once per track. Ties are broken by first appearance
    (i.e. artist-tag ranking order) rather than set iteration order, so identical
    histories always produce the same candidate search — essential for a stateless,
    reproducible API.
    """
    counts: Counter[str] = Counter()
    for track in history:
        seen: set[str] = set()
        for raw in track["genres"]:
            genre = raw.strip().lower()
            if genre and genre not in seen:
                seen.add(genre)
                counts[genre] += 1
    return [g for g, _ in counts.most_common(n)]


async def _retrieve_candidates(top_genres: list[str]) -> dict[str, dict]:
    """Search MusicBrainz by each top genre tag and merge unique candidate metadata.

    Each candidate is annotated with the tag(s) it matched, guaranteeing at least
    those genres are present even when the search response omits the tag list.

    Pools are cached per tag (see ``cache.get_candidates``) because MusicBrainz's tag
    search returns a different result set on every call; without the cache two
    identical /recommend requests could return different tracks.
    """
    candidates: dict[str, dict] = {}
    for tag in top_genres:
        pool = cache.get_candidates(tag)
        if pool is None:
            pool = await musicbrainz.search_by_tag(tag, settings.CANDIDATE_POOL_SIZE)
            # Sort by MBID before caching: the upstream order is arbitrary, and a
            # stable order here is what makes the merged candidate list — and so the
            # final ranking — identical for identical requests.
            pool = sorted(
                (rec for rec in pool if rec.get("mbid")), key=lambda rec: rec["mbid"]
            )
            cache.set_candidates(tag, pool)
        for rec in pool:
            mbid = rec["mbid"]
            entry = candidates.setdefault(mbid, {**rec, "genres": list(rec.get("genres", []))})
            if tag not in entry["genres"]:
                entry["genres"].append(tag)
    return candidates


async def _resolve_youtube(track: dict) -> str | None:
    """Resolve (and cache) the YouTube video id for a track."""
    cached = cache.get_youtube(track["mbid"])
    if cached is not None:
        return cached
    video_id = await youtube.search_video_id(f"{track['artist']} - {track['title']}")
    if video_id:
        cache.set_youtube(track["mbid"], video_id)
    return video_id


async def _collaborative_affinity(
    history: list[dict], config: PipelineConfig
) -> dict[str, float]:
    """Fetch and merge ListenBrainz affinity for the history's artists.

    Returns an empty map — meaning "content scoring only" — when the stage is
    disabled, when no history track carries an artist MBID, or when ListenBrainz
    has nothing for any of them.
    """
    if not config.use_collaborative or config.collab_weight <= 0.0:
        return {}
    artist_mbids = [t["artist_mbid"] for t in history if t.get("artist_mbid")]
    if not artist_mbids:
        return {}
    similar_by_artist = await listenbrainz.get_similar_artists_many(artist_mbids)
    return collaborative.build_affinity(similar_by_artist)


def _rank(
    history: list[dict],
    candidates: list[dict],
    affinity: dict[str, float],
    config: PipelineConfig,
) -> list[tuple[float, dict]]:
    """Run stages 1-3 synchronously and return the re-ranked candidate list.

    This whole function must stay await-free. The genre vocabulary it resets and
    consumes is module-level mutable state, so an await anywhere between the reset
    and the last ``build_feature_vector`` call would let a concurrent request observe
    into — or clear — this request's vocabulary, breaking the stateless-and-
    reproducible guarantee the project's premise depends on.
    """
    # Stage 1: shared vocabulary -> vectors -> centroid -> cosine relevance.
    feat.reset_vocabulary()
    for track in history + candidates:
        feat.observe_track(track["genres"])
    history_vectors = [feat.build_feature_vector(t) for t in history]
    centroid = compute_centroid(history_vectors)

    history_genres = {
        g.strip().lower() for t in history for g in t["genres"] if g and g.strip()
    }

    scored: list[tuple[float, dict, np.ndarray]] = []
    for cand in candidates:
        vector = feat.build_feature_vector(cand)
        content = cosine_score(centroid, vector)
        # Genre overlap with the history is a deterministic tiebreak on the content
        # score, kept from the single-stage engine; scaled small enough that it can
        # only separate candidates the cosine score cannot.
        overlap = len({g.lower() for g in cand["genres"]} & history_genres)
        content += min(overlap, 9) * 1e-6

        # Stage 2: blend in aggregate collaborative affinity where evidence exists.
        collab = collaborative.collaborative_score(cand, affinity)
        relevance = collaborative.blend(content, collab, config.effective_collab_weight)
        cand["collab_score"] = round(collab, 4)
        scored.append((relevance, cand, vector))

    # Stage 3: MMR re-ranking against the history (λ = 1 short-circuits to plain sort).
    return mmr_rank(scored, history_vectors, config.effective_lambda, config.list_size)


async def recommend_ranked(
    track_history: list[str],
    params,
    config: PipelineConfig = DEFAULT_PIPELINE,
) -> tuple[list[tuple[float, dict]], list[dict]]:
    """Produce the re-ranked candidate list and the resolved history behind it.

    Playback resolution is deliberately *not* performed here: the offline evaluation
    harness needs the ranked list without spending a YouTube lookup per candidate,
    and ``recommend()`` layers playback on top of this.
    """
    # 1. Resolve history features in parallel; skip unresolvable MBIDs.
    resolved = await asyncio.gather(*(_resolve_track_features(m) for m in track_history))
    history = [t for t in resolved if t is not None]
    if not history:
        raise RecommendationError(
            "no_history_resolved",
            "None of the supplied track IDs could be resolved to a known recording.",
        )

    # 2. Candidate retrieval from the dominant genres, minus exclusions.
    top_genres = _top_genres(history, _TOP_GENRE_TAGS)
    if not top_genres:
        raise RecommendationError(
            "no_genres_for_history",
            "No genre information is available for the listening history, so no "
            "candidates can be searched.",
        )

    raw_candidates = await _retrieve_candidates(top_genres)
    history_ids = set(track_history)
    exclude_tracks = set(params.exclude_tracks)
    exclude_artists = {a.strip().lower() for a in params.exclude_artists}
    candidate_recs = [
        rec
        for mbid, rec in raw_candidates.items()
        if mbid not in history_ids
        and mbid not in exclude_tracks
        and rec["artist"].strip().lower() not in exclude_artists
    ][: settings.CANDIDATE_POOL_SIZE]
    if not candidate_recs:
        raise RecommendationError(
            "no_candidates_found",
            "No candidate tracks were found for the history's genres after applying "
            "exclusions.",
        )

    candidates = await _resolve_candidates(candidate_recs)

    # 3. Hard tempo filter.
    tempo_min, tempo_max = params.tempo_range
    candidates = [c for c in candidates if tempo_min <= c["tempo"] <= tempo_max]
    if not candidates:
        raise RecommendationError(
            "no_candidates_after_filters",
            f"No candidates fell within the requested tempo range "
            f"({tempo_min:g}–{tempo_max:g} BPM).",
        )

    # 4. Aggregate collaborative evidence (awaited *before* the await-free ranking).
    affinity = await _collaborative_affinity(history, config)

    return _rank(history, candidates, affinity, config), history


async def recommend(
    track_history: list[str],
    params,
    config: PipelineConfig = DEFAULT_PIPELINE,
) -> dict:
    """Recommend the next track for a listening history. See module docstring."""
    ranked, history = await recommend_ranked(track_history, params, config)

    # Resolve playback for the best candidate, falling through on YouTube misses.
    for score, cand in ranked[: settings.MAX_YOUTUBE_ATTEMPTS]:
        video_id = await _resolve_youtube(cand)
        if video_id:
            return _build_response(cand, video_id, score, history)

    raise RecommendationError(
        "no_youtube_match",
        "Candidates were found but none could be matched to a playable YouTube video.",
    )


def _build_response(winner: dict, video_id: str, score: float, history: list[dict]) -> dict:
    """Assemble the recommendation payload for the winning candidate."""
    rationale = generate_rationale(
        winner, history, winner["used_fallback"], winner.get("collab_score", 0.0)
    )
    return {
        "track_id": winner["mbid"],
        "title": winner["title"],
        "artist": winner["artist"],
        "youtube_video_id": video_id,
        "score": round(min(1.0, max(0.0, score)), 3),
        "rationale": rationale,
        "features": {
            "tempo": round(winner["tempo"]),
            "key": f"{winner['key']} {winner['mode']}",
            "energy": round(winner["energy"], 2),
            "genres": winner["genres"][:_RESPONSE_GENRE_LIMIT],
        },
        "limited_acoustic_data": winner["used_fallback"],
    }
