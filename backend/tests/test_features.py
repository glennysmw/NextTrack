"""Tests for feature-vector construction."""
from app.engine import features
from app.engine.features import DEFAULT_ACOUSTIC, FIXED_DIMS, PITCH_CLASSES


def test_feature_vector_dimensions_correct():
    features.reset_vocabulary()
    features.observe_track(["grunge", "alternative rock"])
    features.observe_track(["pop"])

    raw = {
        "tempo": 120,
        "key": "C",
        "mode": "major",
        "energy": 0.5,
        "loudness": 0.5,
        "genres": ["grunge"],
    }
    vec = features.build_feature_vector(raw)

    assert features.vocabulary_size() == 3
    assert len(vec) == FIXED_DIMS + features.vocabulary_size()


def test_tempo_normalised_to_unit_range():
    assert features.normalise_tempo(120) == (120 - 40) / (200 - 40)
    assert 0.0 <= features.normalise_tempo(95) <= 1.0


def test_tempo_outside_range_clamped():
    assert features.normalise_tempo(10) == 0.0
    assert features.normalise_tempo(500) == 1.0


def test_one_hot_key_exactly_one_set():
    features.reset_vocabulary()
    raw = {"tempo": 120, "key": "F#", "mode": "minor", "energy": 0.5, "loudness": 0.5, "genres": []}
    vec = features.build_feature_vector(raw)

    key_block = vec[1:13]
    assert key_block.sum() == 1.0
    assert int((key_block == 1.0).sum()) == 1
    assert key_block[PITCH_CLASSES.index("F#")] == 1.0


def test_fallback_features_when_acousticbrainz_missing():
    features.reset_vocabulary()
    vec = features.build_feature_vector({**DEFAULT_ACOUSTIC, "genres": []})

    assert vec[0] == 0.5  # tempo 120 BPM -> mid of 40..200
    assert vec[13] == 1.0  # mode major
    assert vec[14] == 0.5  # energy default
    assert vec[15] == 0.5  # loudness default
    assert vec[1:13][PITCH_CLASSES.index("C")] == 1.0  # default key C
