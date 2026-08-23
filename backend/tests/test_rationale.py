"""Tests for human-readable rationale generation."""
from app.engine.rationale import (
    LIMITED_ACOUSTIC_NOTE,
    generate_rationale,
    summarise_history,
)

HISTORY = [
    {
        "tempo": 117,
        "key": "F#",
        "mode": "minor",
        "energy": 0.70,
        "genres": ["grunge", "alternative rock"],
    }
]


def test_rationale_includes_genre_overlap_when_high():
    candidate = {
        "tempo": 119,
        "key": "F#",
        "mode": "minor",
        "energy": 0.69,
        "genres": ["grunge", "alternative rock"],
    }
    rationale = generate_rationale(candidate, HISTORY, used_fallback=False)
    assert "shared genre tags" in rationale
    assert "grunge" in rationale


def test_rationale_includes_tempo_match_when_close():
    candidate = {
        "tempo": 120,
        "key": "C",
        "mode": "major",
        "energy": 0.10,
        "genres": ["pop"],
    }
    rationale = generate_rationale(candidate, HISTORY, used_fallback=False)
    assert "similar tempo" in rationale


def test_rationale_prepends_limited_acoustic_data_note():
    candidate = {
        "tempo": 119,
        "key": "F#",
        "mode": "minor",
        "energy": 0.69,
        "genres": ["grunge", "alternative rock"],
    }
    rationale = generate_rationale(candidate, HISTORY, used_fallback=True)
    assert rationale.startswith(LIMITED_ACOUSTIC_NOTE)


def test_rationale_fallback_when_no_signals_active():
    candidate = {
        "tempo": 40,
        "key": "C",
        "mode": "major",
        "energy": 0.0,
        "genres": ["techno"],
    }
    rationale = generate_rationale(candidate, HISTORY, used_fallback=False)
    assert rationale == (
        "Recommended based on overall feature similarity to your listening history."
    )


# --- Regression: the session's most common key was mis-unpacked -------------------
# summarise_history built a Counter keyed on (pitch, mode) tuples, then unpacked
# most_common(1)[0] as if it were that tuple. It is actually a (item, count) pair, so
# `common_mode` was bound to an integer count and `common_pitch` to the whole tuple.
# Effect: the "compatible key" signal could never match a candidate, and the rendered
# key read "('F#', 'minor') 2". Caught by static type checking, not by the tests.


def test_summarise_history_extracts_pitch_and_mode_not_the_count():
    history = [
        {"tempo": 120, "energy": 0.5, "genres": ["rock"], "key": "F#", "mode": "minor"},
        {"tempo": 118, "energy": 0.5, "genres": ["rock"], "key": "F#", "mode": "minor"},
    ]
    summary = summarise_history(history)
    assert summary["common_pitch"] == "F#"
    assert summary["common_mode"] == "minor"
    assert summary["common_key_display"] == "F# minor"


def test_summarise_history_picks_the_majority_key():
    history = [
        {"tempo": 120, "energy": 0.5, "genres": [], "key": "C", "mode": "major"},
        {"tempo": 120, "energy": 0.5, "genres": [], "key": "C", "mode": "major"},
        {"tempo": 120, "energy": 0.5, "genres": [], "key": "A", "mode": "minor"},
    ]
    summary = summarise_history(history)
    assert (summary["common_pitch"], summary["common_mode"]) == ("C", "major")


def test_compatible_key_signal_can_now_fire():
    history = [
        {"tempo": 120, "energy": 0.5, "genres": ["rock"], "key": "F#", "mode": "minor"},
    ]
    candidate = {
        "tempo": 200,          # outside the tempo window
        "energy": 0.99,        # outside the energy window
        "genres": ["jazz"],    # no shared genres
        "key": "F#",
        "mode": "minor",
    }
    assert "compatible key (F# minor)" in generate_rationale(candidate, history)
