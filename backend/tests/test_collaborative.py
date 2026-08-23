"""Unit tests for stage 2: aggregate collaborative scoring and blending."""
import pytest

from app.engine import collaborative


def test_affinity_normalises_each_reference_artist_independently():
    """Raw co-listening counts differ in magnitude per reference artist."""
    affinity = collaborative.build_affinity(
        {
            "popular-artist": {"a": 10000.0, "b": 5000.0},
            "niche-artist": {"c": 20.0, "b": 10.0},
        }
    )
    # Each list is scaled against its own maximum, so the niche artist's top match
    # is not drowned out by the popular artist's larger raw counts.
    assert affinity["a"] == pytest.approx(1.0)
    assert affinity["c"] == pytest.approx(1.0)
    # 'b' appears in both lists; the strongest normalised score wins (0.5 vs 0.5).
    assert affinity["b"] == pytest.approx(0.5)


def test_affinity_takes_the_max_not_the_sum():
    """A widely-similar artist must not accumulate an unbounded score."""
    affinity = collaborative.build_affinity(
        {"x": {"shared": 100.0}, "y": {"shared": 100.0}, "z": {"shared": 100.0}}
    )
    assert affinity["shared"] == pytest.approx(1.0)


def test_affinity_ignores_empty_and_zero_lists():
    affinity = collaborative.build_affinity({"a": {}, "b": {"x": 0.0}, "c": {"y": 4.0}})
    assert affinity == {"y": 1.0}


def test_collaborative_score_zero_without_artist_mbid():
    assert collaborative.collaborative_score({"artist_mbid": None}, {"a": 1.0}) == 0.0
    assert collaborative.collaborative_score({}, {"a": 1.0}) == 0.0


def test_collaborative_score_reads_the_affinity_map():
    candidate = {"artist_mbid": "a"}
    assert collaborative.collaborative_score(candidate, {"a": 0.75}) == 0.75
    assert collaborative.collaborative_score(candidate, {"b": 0.75}) == 0.0


def test_blend_leaves_content_score_untouched_without_evidence():
    """No collaborative evidence must not deflate the reported confidence score."""
    assert collaborative.blend(0.8, 0.0, 0.3) == pytest.approx(0.8)


def test_blend_mixes_both_signals_when_evidence_exists():
    assert collaborative.blend(0.8, 1.0, 0.3) == pytest.approx(0.7 * 0.8 + 0.3 * 1.0)


def test_blend_with_zero_weight_is_content_only():
    assert collaborative.blend(0.42, 0.99, 0.0) == pytest.approx(0.42)
