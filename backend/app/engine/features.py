"""Feature-vector construction.

A track's feature vector is the concatenation of fixed acoustic dimensions and a
sparse genre TF-IDF block. The genre vocabulary is accumulated at module level
across the tracks observed in a session (history + candidates); vectors are only
comparable when built against the same vocabulary, so the recommender observes
every track first and then builds all vectors.
"""
import math
from collections.abc import Iterable

import numpy as np

from app.config import settings

# Pitch classes for the 12-dimensional key one-hot block.
PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Enharmonic flats map onto their sharp equivalents.
_ENHARMONIC = {
    "Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#",
    "Cb": "B", "Fb": "E", "E#": "F", "B#": "C",
}

# Fixed block layout: tempo(1) + key(12) + mode(1) + energy(1) + loudness(1).
FIXED_DIMS = 16
_TEMPO_IDX = 0
_KEY_START = 1
_MODE_IDX = 13
_ENERGY_IDX = 14
_LOUDNESS_IDX = 15

# Acoustic defaults used when AcousticBrainz has no data for a track.
# loudness 0.5 corresponds to -30 dB on the -60..0 dB scale.
DEFAULT_TEMPO = 120.0
DEFAULT_KEY = "C"
DEFAULT_MODE = "major"
DEFAULT_ENERGY = 0.5
DEFAULT_LOUDNESS = 0.5

DEFAULT_ACOUSTIC: dict[str, float | str] = {
    "tempo": DEFAULT_TEMPO,
    "key": DEFAULT_KEY,
    "mode": DEFAULT_MODE,
    "energy": DEFAULT_ENERGY,
    "loudness": DEFAULT_LOUDNESS,
}

# Module-level genre vocabulary state (session-scoped accumulation).
_genre_index: dict[str, int] = {}
_genre_doc_freq: dict[str, int] = {}
_doc_count = 0


def reset_vocabulary() -> None:
    """Clear the accumulated genre vocabulary (used between requests/tests)."""
    global _doc_count
    _genre_index.clear()
    _genre_doc_freq.clear()
    _doc_count = 0


def observe_track(genres: Iterable[str]) -> None:
    """Register one track's genres, updating the vocabulary and document frequencies."""
    global _doc_count
    _doc_count += 1
    for genre in {g.strip().lower() for g in genres if g and g.strip()}:
        if genre not in _genre_index:
            _genre_index[genre] = len(_genre_index)
        _genre_doc_freq[genre] = _genre_doc_freq.get(genre, 0) + 1


def vocabulary_size() -> int:
    """Number of distinct genres seen so far."""
    return len(_genre_index)


def feature_dimension() -> int:
    """Total dimensionality of vectors built against the current vocabulary."""
    return FIXED_DIMS + vocabulary_size()


def _idf(genre: str) -> float:
    """Smoothed inverse document frequency (sklearn-style: log((1+N)/(1+df)) + 1)."""
    df = _genre_doc_freq.get(genre, 0)
    return math.log((1 + _doc_count) / (1 + df)) + 1.0


def normalise_tempo(bpm: float) -> float:
    """Map BPM to [0, 1] over the configured tempo range, clamped at the edges."""
    span = settings.TEMPO_MAX - settings.TEMPO_MIN
    value = (bpm - settings.TEMPO_MIN) / span
    return float(min(1.0, max(0.0, value)))


def normalise_loudness(db: float) -> float:
    """Map a dB value to [0, 1] over the -60..0 dB range, clamped at the edges."""
    span = settings.LOUDNESS_MAX_DB - settings.LOUDNESS_MIN_DB
    value = (db - settings.LOUDNESS_MIN_DB) / span
    return float(min(1.0, max(0.0, value)))


def canonical_key(key: str | None) -> str:
    """Normalise a key name to a canonical pitch class (sharps), defaulting to C."""
    if not key:
        return "C"
    k = key.strip().capitalize()
    k = _ENHARMONIC.get(k, k)
    return k if k in PITCH_CLASSES else "C"


def build_feature_vector(raw: dict) -> np.ndarray:
    """Build a feature vector for one track against the current genre vocabulary.

    `raw` keys: tempo (BPM), key (pitch class), mode ("major"/"minor"),
    energy [0,1], loudness [0,1], genres (list[str]).
    """
    vec = np.zeros(feature_dimension(), dtype=np.float64)

    vec[_TEMPO_IDX] = normalise_tempo(_as_float(raw.get("tempo"), DEFAULT_TEMPO))

    key = canonical_key(raw.get("key"))
    vec[_KEY_START + PITCH_CLASSES.index(key)] = 1.0

    mode = str(raw.get("mode", DEFAULT_MODE)).lower()
    vec[_MODE_IDX] = 1.0 if mode == "major" else 0.0

    vec[_ENERGY_IDX] = _clamp01(raw.get("energy", DEFAULT_ENERGY))
    vec[_LOUDNESS_IDX] = _clamp01(raw.get("loudness", DEFAULT_LOUDNESS))

    for genre in {g.strip().lower() for g in raw.get("genres", []) if g and g.strip()}:
        idx = _genre_index.get(genre)
        if idx is not None:
            vec[FIXED_DIMS + idx] = _idf(genre)

    return vec


def _as_float(value: object, default: float) -> float:
    """Coerce an untyped value to float, falling back on anything unusable."""
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp01(value: object) -> float:
    """Coerce a value into the unit interval, defaulting an unusable value to 0.5."""
    if not isinstance(value, (int, float, str)):
        return 0.5
    try:
        return float(min(1.0, max(0.0, float(value))))
    except (TypeError, ValueError):
        return 0.5
