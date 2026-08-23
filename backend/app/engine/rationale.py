"""Human-readable rationale generation for a recommendation.

A rationale is a single sentence built from the strongest matching dimensions
between the winning candidate and the listening history.
"""
from collections import Counter

# Prepended verbatim when the winning candidate relied on fallback acoustics.
LIMITED_ACOUSTIC_NOTE = (
    "Note: limited acoustic data for this track; "
    "recommendation primarily based on metadata. "
)

_FALLBACK_SENTENCE = (
    "Recommended based on overall feature similarity to your listening history."
)

# Thresholds governing when each signal is considered "active".
_MIN_SHARED_GENRES = 2
_TEMPO_MATCH_BPM = 10.0
_ENERGY_MATCH_DELTA = 0.15
_MAX_SHARED_GENRES_SHOWN = 3
# Collaborative affinity is normalised to [0, 1]; below this it is weak enough that
# naming it in the explanation would overstate the evidence.
_MIN_COLLAB_SCORE = 0.15


def _display_key(pitch: str, mode: str) -> str:
    """Render a key for humans, e.g. 'F# minor'."""
    return f"{pitch} {str(mode).lower()}".strip()


def summarise_history(history: list[dict]) -> dict:
    """Aggregate the history feature dicts into the summary the rationale needs."""
    tempos = [float(h.get("tempo", 0.0)) for h in history]
    energies = [float(h.get("energy", 0.0)) for h in history]

    genre_counts: Counter[str] = Counter()
    for h in history:
        for g in {x.strip().lower() for x in h.get("genres", []) if x and x.strip()}:
            genre_counts[g] += 1

    key_counts: Counter[tuple[str, str]] = Counter(
        (str(h.get("key", "C")), str(h.get("mode", "major")).lower()) for h in history
    )
    # most_common() yields (item, count) pairs, so the (pitch, mode) key has to be
    # taken out of element [0]. Unpacking the pair directly silently bound `mode` to
    # the *count*, which made the "compatible key" signal unreachable and rendered
    # the key as "('F#', 'minor') 2".
    common_pitch, common_mode = (
        key_counts.most_common(1)[0][0] if key_counts else ("C", "major")
    )

    return {
        "avg_tempo": sum(tempos) / len(tempos) if tempos else 0.0,
        "avg_energy": sum(energies) / len(energies) if energies else 0.0,
        "common_pitch": common_pitch,
        "common_mode": common_mode,
        "common_key_display": _display_key(common_pitch, common_mode),
        "genre_counts": genre_counts,
    }


def _join_signals(signals: list[str]) -> str:
    """Join up to three signal phrases with Oxford-comma style punctuation."""
    if len(signals) == 1:
        body = signals[0]
    elif len(signals) == 2:
        body = f"{signals[0]} and {signals[1]}"
    else:
        body = f"{signals[0]}, {signals[1]}, and {signals[2]}"
    return f"Recommended based on {body}."


def generate_rationale(
    candidate: dict,
    history: list[dict],
    used_fallback: bool = False,
    collab_score: float = 0.0,
) -> str:
    """Build the rationale sentence for `candidate` given the listening `history`.

    `collab_score` is the candidate's normalised ListenBrainz co-listening affinity;
    when it clears the threshold it is named first, because it is the only signal in
    the sentence that comes from other listeners rather than from the audio metadata,
    and a user reading the explanation should be able to tell those apart.
    """
    summary = summarise_history(history)
    prefix = LIMITED_ACOUSTIC_NOTE if used_fallback else ""

    signals: list[str] = []

    if collab_score >= _MIN_COLLAB_SCORE:
        signals.append("listeners of these artists also listening to this one")

    cand_genres = {g.strip().lower() for g in candidate.get("genres", []) if g and g.strip()}
    shared = [g for g, _ in summary["genre_counts"].most_common() if g in cand_genres]
    if len(shared) >= _MIN_SHARED_GENRES:
        top = ", ".join(shared[:_MAX_SHARED_GENRES_SHOWN])
        signals.append(f"shared genre tags ({top})")

    cand_tempo = float(candidate.get("tempo", 0.0))
    if abs(cand_tempo - summary["avg_tempo"]) <= _TEMPO_MATCH_BPM:
        signals.append(
            f"similar tempo ({round(cand_tempo)} BPM vs "
            f"history average {round(summary['avg_tempo'])} BPM)"
        )

    if abs(float(candidate.get("energy", 0.0)) - summary["avg_energy"]) < _ENERGY_MATCH_DELTA:
        signals.append("matching energy level")

    cand_pitch = candidate.get("key", "C")
    cand_mode = str(candidate.get("mode", "major")).lower()
    if cand_pitch == summary["common_pitch"] and cand_mode == summary["common_mode"]:
        signals.append(f"compatible key ({_display_key(cand_pitch, cand_mode)})")

    if not signals:
        return prefix + _FALLBACK_SENTENCE

    return prefix + _join_signals(signals[:3])
