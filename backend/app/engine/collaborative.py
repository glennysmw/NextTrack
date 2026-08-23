"""Stage 2 of the cascade hybrid: aggregate collaborative re-ranking.

Burke (2002) describes a cascade hybrid as one technique producing candidates and a
second refining their order. Stage 1 (``similarity``) scores candidates on content;
this module supplies the second, independent line of evidence — how often the
candidate's artist is co-listened with the history's artists across the ListenBrainz
population.

The signal is deliberately *artist-level*, not track-level. ListenBrainz publishes
both, but recording-level similarity is sparse enough on this project's catalogue to
return nothing for most seeds (verified empirically during development), whereas
artist-level similarity resolves for essentially any charting artist. Artist
co-listening also captures precisely the relationship content features cannot: two
tracks whose acoustic descriptors and genre tags diverge but whose audiences overlap.

Scores are combined, not gated. A candidate with no collaborative evidence keeps its
content score unchanged rather than being penalised, so partial ListenBrainz coverage
degrades the *strength* of the stage, never the availability of a recommendation.
"""
import logging

logger = logging.getLogger(__name__)


def build_affinity(similar_by_artist: dict[str, dict[str, float]]) -> dict[str, float]:
    """Collapse per-history-artist similarity lists into one affinity map.

    ``similar_by_artist`` maps each *history* artist MBID to its ListenBrainz
    similar-artist scores. Scores from different reference artists are not directly
    comparable (they are raw co-occurrence counts whose magnitude depends on the
    reference artist's popularity), so each list is normalised to [0, 1] against its
    own maximum before the lists are merged. An artist similar to several history
    artists takes the strongest of its normalised scores, which keeps the map bounded
    in [0, 1] and avoids a popular artist accumulating an unbounded sum.
    """
    affinity: dict[str, float] = {}
    for similar in similar_by_artist.values():
        if not similar:
            continue
        peak = max(similar.values())
        if peak <= 0:
            continue
        for mbid, score in similar.items():
            normalised = score / peak
            if normalised > affinity.get(mbid, 0.0):
                affinity[mbid] = normalised
    return affinity


def collaborative_score(candidate: dict, affinity: dict[str, float]) -> float:
    """Return the candidate's collaborative affinity in [0, 1] (0 = no evidence)."""
    artist_mbid = candidate.get("artist_mbid")
    if not artist_mbid:
        return 0.0
    return affinity.get(artist_mbid, 0.0)


def blend(content_score: float, collab_score: float, weight: float) -> float:
    """Blend content and collaborative scores into a single relevance value.

    ``weight`` is the collaborative share of the blend. It is applied only when
    collaborative evidence actually exists: with ``collab_score == 0`` the formula
    would otherwise scale every unmatched candidate down by ``(1 - weight)``,
    which is a uniform rescaling that changes nothing about *relative* order but
    does deflate the confidence score the API reports to the user. Returning the
    content score unchanged in that case keeps the reported score meaningful.
    """
    if collab_score <= 0.0:
        return content_score
    return (1.0 - weight) * content_score + weight * collab_score
