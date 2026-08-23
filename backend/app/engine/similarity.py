"""Cosine-similarity ranking against a session centroid."""
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


def compute_centroid(vectors: list[np.ndarray]) -> np.ndarray:
    """Return the element-wise mean of a non-empty list of equal-length vectors."""
    if not vectors:
        raise ValueError("cannot compute centroid of an empty vector list")
    return np.mean(np.vstack(vectors), axis=0)


def cosine_score(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two vectors, in [0, 1] for non-negative feature space."""
    if not np.any(a) or not np.any(b):
        return 0.0
    sim = cosine_similarity(a.reshape(1, -1), b.reshape(1, -1))[0, 0]
    return float(min(1.0, max(0.0, sim)))


def rank_candidates(
    centroid: np.ndarray,
    candidates: list[tuple[str, np.ndarray]],
) -> list[tuple[str, float]]:
    """Score each (id, vector) candidate against the centroid, highest first."""
    scored = [(cid, cosine_score(centroid, vec)) for cid, vec in candidates]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored
