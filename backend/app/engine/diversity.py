"""Stage 3 of the cascade hybrid: Maximal Marginal Relevance diversity re-ranking.

Carbonell and Goldstein (1998) defined MMR for retrieval as a greedy trade-off
between a document's relevance to the query and its redundancy against what has
already been selected:

    MMR(c) = λ·rel(c, Q) − (1 − λ)·max_{s ∈ S} sim(c, s)

NextTrack adapts this to next-track recommendation with one substantive change: the
"already selected" set S is *seeded with the listening history*, not left empty.
That matters because a next-track recommender emits one item, so a classical MMR
whose S starts empty would reduce to plain relevance ranking on the first pick and
change nothing at all. Seeding S with the history makes the redundancy term measure
what it should measure here — how close the candidate is to music the listener has
just heard — which is exactly the over-specialisation Lops et al. (2011) predict for
pure content-based filtering and which this project observed in practice.

λ = 1 recovers the pure relevance ranking, so the stage is exactly ablatable: the
offline evaluation runs the same code path with λ = 1 for its "no diversity" arm.
"""
import numpy as np

from app.engine.similarity import cosine_score


def mmr_rank(
    candidates: list[tuple[float, dict, np.ndarray]],
    history_vectors: list[np.ndarray],
    lambda_: float,
    k: int,
) -> list[tuple[float, dict]]:
    """Greedily re-rank ``candidates`` by MMR, returning the top ``k`` as (score, track).

    ``candidates`` are (relevance, track, vector) triples; ``relevance`` is the blended
    content/collaborative score from the earlier stages. The returned score is the
    original relevance, not the MMR objective value — the objective governs *order*,
    while the score the API reports should stay interpretable as "how well this matches
    your session". Ties are broken deterministically by the candidate's MBID so that
    two identical requests always produce an identical ordering, which the statelessness
    guarantee requires.
    """
    if not candidates:
        return []
    if lambda_ >= 1.0:
        ordered = sorted(candidates, key=lambda c: (-c[0], c[1].get("mbid", "")))
        return [(rel, track) for rel, track, _ in ordered[:k]]

    remaining = list(candidates)
    selected_vectors = list(history_vectors)
    chosen: list[tuple[float, dict]] = []

    while remaining and len(chosen) < k:
        best_index = 0
        best_objective = -float("inf")
        best_key = ""
        for index, (relevance, track, vector) in enumerate(remaining):
            redundancy = max(
                (cosine_score(vector, other) for other in selected_vectors), default=0.0
            )
            objective = lambda_ * relevance - (1.0 - lambda_) * redundancy
            key = track.get("mbid", "")
            if objective > best_objective or (objective == best_objective and key < best_key):
                best_objective = objective
                best_index = index
                best_key = key
        relevance, track, vector = remaining.pop(best_index)
        selected_vectors.append(vector)
        chosen.append((relevance, track))

    return chosen


def intra_list_diversity(vectors: list[np.ndarray]) -> float:
    """Mean pairwise dissimilarity (1 − cosine) of a recommended list.

    The standard beyond-accuracy diversity metric (Kaminskas and Bridge, 2016). A
    list of fewer than two items has no pairwise structure, so it returns 0.0.
    """
    if len(vectors) < 2:
        return 0.0
    total = 0.0
    pairs = 0
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            total += 1.0 - cosine_score(vectors[i], vectors[j])
            pairs += 1
    return total / pairs if pairs else 0.0
