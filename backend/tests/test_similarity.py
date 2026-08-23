"""Tests for cosine similarity and centroid computation."""
import numpy as np
import pytest

from app.engine.similarity import compute_centroid, cosine_score


def test_identical_vectors_similarity_1():
    v = np.array([1.0, 2.0, 3.0])
    assert cosine_score(v, v.copy()) == pytest.approx(1.0)


def test_orthogonal_vectors_similarity_0():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert cosine_score(a, b) == pytest.approx(0.0)


def test_centroid_of_single_vector_equals_vector():
    v = np.array([1.0, 2.0, 3.0])
    assert np.allclose(compute_centroid([v]), v)


def test_centroid_of_multiple_vectors_is_mean():
    a = np.array([0.0, 0.0, 4.0])
    b = np.array([2.0, 4.0, 0.0])
    assert np.allclose(compute_centroid([a, b]), np.array([1.0, 2.0, 2.0]))
