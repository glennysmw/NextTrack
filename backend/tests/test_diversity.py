"""Unit tests for stage 3: MMR diversity re-ranking."""
import numpy as np
import pytest

from app.engine.diversity import intra_list_diversity, mmr_rank


def _track(mbid: str) -> dict:
    return {"mbid": mbid}


def test_lambda_one_is_pure_relevance_ranking():
    """λ = 1 must reproduce the plain relevance order — the ablation baseline."""
    v = np.array([1.0, 0.0])
    candidates = [(0.4, _track("c"), v), (0.9, _track("a"), v), (0.6, _track("b"), v)]
    ranked = mmr_rank(candidates, [v], lambda_=1.0, k=3)
    assert [t["mbid"] for _, t in ranked] == ["a", "b", "c"]
    assert [round(s, 3) for s, _ in ranked] == [0.9, 0.6, 0.4]


def test_diversity_demotes_a_near_duplicate_of_the_history():
    """The whole point of the stage: redundancy with what was just played costs rank."""
    history = np.array([1.0, 0.0, 0.0])
    clone = np.array([1.0, 0.0, 0.0])       # identical to the history track
    different = np.array([0.0, 1.0, 0.0])   # orthogonal to it

    # The clone is *more* relevant on content alone, so relevance ranking picks it.
    candidates = [(0.90, _track("clone"), clone), (0.70, _track("fresh"), different)]

    assert [t["mbid"] for _, t in mmr_rank(candidates, [history], 1.0, 2)][0] == "clone"
    # With diversity on, the redundancy penalty flips the order.
    assert [t["mbid"] for _, t in mmr_rank(candidates, [history], 0.5, 2)][0] == "fresh"


def test_reported_score_stays_the_relevance_not_the_mmr_objective():
    """Order comes from MMR; the number shown to the user stays interpretable."""
    history = np.array([1.0, 0.0])
    candidates = [(0.8, _track("a"), np.array([0.0, 1.0]))]
    ranked = mmr_rank(candidates, [history], 0.5, 1)
    assert ranked[0][0] == pytest.approx(0.8)


def test_selected_items_penalise_each_other_not_just_the_history():
    """Greedy selection must add each pick to S, so slot 2 avoids repeating slot 1."""
    history = np.array([0.0, 0.0, 1.0])
    a = np.array([1.0, 0.0, 0.0])
    a_clone = np.array([1.0, 0.0, 0.0])
    b = np.array([0.0, 1.0, 0.0])
    candidates = [
        (0.90, _track("a"), a),
        (0.85, _track("a_clone"), a_clone),
        (0.50, _track("b"), b),
    ]
    ranked = [t["mbid"] for _, t in mmr_rank(candidates, [history], 0.5, 3)]
    assert ranked[0] == "a"
    # a_clone is more relevant than b but identical to the pick already made.
    assert ranked[1] == "b"


def test_ranking_is_deterministic_under_ties():
    """A stateless API must return the same order for the same input, every time."""
    v = np.array([1.0, 1.0])
    candidates = [(0.5, _track("z"), v), (0.5, _track("a"), v), (0.5, _track("m"), v)]
    first = [t["mbid"] for _, t in mmr_rank(candidates, [v], 0.7, 3)]
    second = [t["mbid"] for _, t in mmr_rank(list(reversed(candidates)), [v], 0.7, 3)]
    assert first == second


def test_empty_candidate_list_returns_empty():
    assert mmr_rank([], [np.array([1.0])], 0.7, 5) == []


def test_k_truncates_the_returned_list():
    v = np.array([1.0, 0.0])
    candidates = [(0.5, _track(str(i)), v) for i in range(10)]
    assert len(mmr_rank(candidates, [v], 0.7, 3)) == 3


def test_intra_list_diversity_bounds():
    identical = [np.array([1.0, 0.0]), np.array([1.0, 0.0])]
    orthogonal = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
    assert intra_list_diversity(identical) == pytest.approx(0.0)
    assert intra_list_diversity(orthogonal) == pytest.approx(1.0)
    assert intra_list_diversity([np.array([1.0])]) == 0.0
    assert intra_list_diversity([]) == 0.0
