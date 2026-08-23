"""Regression tests for the genre candidate-pool cache.

Background: MusicBrainz's tag search is *not stable*. Two consecutive
``search_recordings(tag="grunge")`` calls returned fifty results each with **zero**
overlap (measured against the live API during the final engineering pass), because
thousands of recordings tie on relevance and the tie order is arbitrary. That made
two identical /recommend requests return different tracks — directly contradicting the
reproducibility a stateless API is supposed to offer.

The pool cache is the fix, so these tests guard the property that motivated it, not
just the mechanics of the cache.
"""
import time

import pytest

from app.config import settings
from app.data import cache
from app.engine import recommender
from app.models.request import RecommendParams


def test_pool_is_cached_and_reused():
    cache.set_candidates("grunge", [{"mbid": "a"}])
    assert cache.get_candidates("grunge") == [{"mbid": "a"}]


def test_missing_tag_reports_a_miss():
    assert cache.get_candidates("never-searched") is None


def test_pool_expires_after_its_ttl(monkeypatch):
    monkeypatch.setattr(settings, "CANDIDATE_CACHE_TTL_SECONDS", 0.0)
    cache.set_candidates("grunge", [{"mbid": "a"}])
    time.sleep(0.01)
    assert cache.get_candidates("grunge") is None


def test_stats_report_the_pool_count():
    cache.set_candidates("grunge", [{"mbid": "a"}])
    cache.set_candidates("rock", [{"mbid": "b"}])
    assert cache.stats()["candidate_pools"] == 2


def test_clear_drops_pools():
    cache.set_candidates("grunge", [{"mbid": "a"}])
    cache.clear()
    assert cache.stats()["candidate_pools"] == 0


async def test_retrieval_hits_musicbrainz_once_per_tag(mock_sources, seed_ids):
    """A warm request must not re-run the three rate-limited searches."""
    params = RecommendParams()
    await recommender.recommend([seed_ids.history], params)
    first_call_count = mock_sources.search_by_tag.call_count
    assert first_call_count > 0

    await recommender.recommend([seed_ids.history], params)
    assert mock_sources.search_by_tag.call_count == first_call_count


async def test_unstable_upstream_search_cannot_change_the_recommendation(
    mock_sources, seed_ids
):
    """The property that matters: an unstable tag search must not leak into results.

    The mock is rigged to reverse its result order on every call, standing in for
    MusicBrainz returning a differently-ordered (or entirely different) result set.
    Without the pool cache the second recommendation could differ; with it, the pool
    is fixed for the TTL and both requests agree.
    """
    original = mock_sources.search_by_tag.side_effect
    flip = {"n": 0}

    def unstable(tag: str, limit: int):
        flip["n"] += 1
        results = original(tag, limit)
        return results if flip["n"] % 2 else list(reversed(results))

    mock_sources.search_by_tag.side_effect = unstable

    params = RecommendParams()
    first = await recommender.recommend([seed_ids.history], params)
    second = await recommender.recommend([seed_ids.history], params)
    assert first["track_id"] == second["track_id"]
    assert first["score"] == second["score"]


@pytest.mark.parametrize("run", range(3))
async def test_repeated_requests_are_stable_across_runs(mock_sources, seed_ids, run):
    """Determinism is a per-request property, so assert it more than once."""
    params = RecommendParams()
    results = [
        (await recommender.recommend([seed_ids.history], params))["track_id"]
        for _ in range(2)
    ]
    assert results[0] == results[1]
