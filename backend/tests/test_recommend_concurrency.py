"""Regression tests for request isolation of the module-level genre vocabulary.

The genre vocabulary is a process-global singleton. `recommend()` must reset and
consume it inside a single await-free block so concurrent requests on the event
loop cannot pollute each other's feature vectors.
"""
import asyncio

from app.engine import features, recommender
from app.models.request import RecommendParams


def test_recommend_resets_vocabulary_within_atomic_block(client, mock_sources, seed_ids):
    """Leftover vocabulary from a prior/concurrent request must not leak in."""
    # Simulate state left behind by another in-flight request.
    features.observe_track(["polka", "disco", "reggaeton"])
    assert features.vocabulary_size() == 3

    resp = client.post("/api/v1/recommend", json={"track_history": [seed_ids.history]})
    assert resp.status_code == 200

    # The reset inside recommend() must have cleared the foreign genres; only this
    # request's genres remain in the vocabulary.
    assert "polka" not in features._genre_index
    assert "disco" not in features._genre_index
    assert "reggaeton" not in features._genre_index


async def test_concurrent_recommends_are_independent(mock_sources, seed_ids):
    """Two recommendations gathered concurrently both succeed with valid payloads."""
    params = RecommendParams()
    a, b = await asyncio.gather(
        recommender.recommend([seed_ids.history], params),
        recommender.recommend([seed_ids.come_as_you_are], params),
    )
    for result in (a, b):
        assert result["track_id"]
        assert 0.0 <= result["score"] <= 1.0
        assert result["youtube_video_id"] == seed_ids.youtube
