"""Offline evaluation and ablation study. Run after ``build_eval_dataset.py``.

Two experiments, because the first one makes the second one necessary.

Experiment A — retrieval reachability
-------------------------------------
Can the engine's genre-gated MusicBrainz candidate retrieval surface the track a real
listener actually played next *at all*? This is measured three ways, from strictest to
most generous: the exact recording identifier, the same song by the same artist
(normalised title and artist, so a different release of the same recording counts), and
merely the same artist appearing anywhere in the pool.

This is reported first because the answer determines what else is measurable. It is a
negative result, and it is the most important finding in the evaluation.

Experiment B — ranking quality under a controlled candidate set
---------------------------------------------------------------
Because Experiment A shows the target is essentially never retrieved, end-to-end
accuracy is zero for every arm and the ablation cannot distinguish anything. Ranking is
therefore measured separately, using the sampled-negatives protocol standard in
sequential recommendation (Kang and McAuley, 2018; Sun et al., 2019): the held-out track
is **injected** into a candidate set alongside negatives sampled from the pool the
engine really retrieved for that session, and every arm ranks that same set.

This measures ranking ability *given* that the target is reachable. It must not be read
as end-to-end accuracy — Experiment A already reports that, and it is zero. The
injection is stated wherever these numbers appear.

Experiment B runs in two conditions, because the first one has a confound worth
controlling rather than merely disclosing. Held-out tracks are resolved through
``get_recording``, which enriches them with their artist's ranked tags; tag-search
candidates carry only the tags the search response returned. The result is asymmetric:
session tracks average 7.1 genre tags, retrieved candidates 2.6. An engine ranking on a
genre TF-IDF block could therefore score well by detecting *richer metadata* rather than
genuine similarity.

  unmatched  negatives sampled freely from the retrieved pool
  matched    negatives restricted to pool tracks carrying at least MATCHED_MIN_GENRES
             tags, so the target cannot be identified by tag richness alone

The gap between the two conditions is the size of the artefact.

The engine arms call the production ranking code (``recommender._rank``) with the data
clients redirected at the harvested corpus. An evaluation that re-implements the scoring
logic measures the re-implementation; only the network is stubbed.

Significance
------------
Every arm is scored on the same sessions, so per-session results are paired and
differences are tested with a Wilcoxon signed-rank test (Wilcoxon, 1945) — the same
non-parametric paired test the project's planned user study specified. It is used rather
than a paired t-test because per-session nDCG is bounded, heavily tied at zero, and not
normal. With a sample this size an apparent gap of a few points may be indistinguishable
from noise, and saying so is more useful than ranking arms on a difference that will not
replicate.

Metrics (Shani and Gunawardana, 2011; Kaminskas and Bridge, 2016)
----------------------------------------------------------------
HitRate@K     did the held-out track appear in the top K
nDCG@K        rank-discounted gain, sensitive to *where* in the list it landed
MRR           mean reciprocal rank of the held-out track
ILD@K         intra-list diversity — mean pairwise (1 - cosine) of the list
Novelty@K     mean -log2(popularity) — how far from the head of the catalogue
Coverage      share of the candidate sets ever recommended across all sessions

Usage:  python scripts/offline_eval.py [--k 10] [--negatives 99] [--out DIR]
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import math
import pathlib
import random
import re
import statistics
import sys
import time
import unicodedata
from collections import Counter
from unittest.mock import AsyncMock, patch

from scipy.stats import wilcoxon

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.engine import features as feat  # noqa: E402
from app.engine import recommender  # noqa: E402
from app.engine.diversity import intra_list_diversity  # noqa: E402
from app.engine.recommender import PipelineConfig  # noqa: E402
from app.models.request import RecommendParams  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("offline_eval")

BACKEND = pathlib.Path(__file__).resolve().parents[1]
CORPUS_PATH = BACKEND / "data" / "eval_corpus.json"
SESSIONS_PATH = BACKEND / "data" / "eval_sessions.json"

# Fixed seed: the random baseline must be reproducible for the reported figures.
RANDOM_SEED = 20260924

ARMS: dict[str, PipelineConfig | str] = {
    "random_catalogue": "random_catalogue",
    "random_pool": "random_pool",
    "popularity": "popularity",
    "content_only": PipelineConfig(use_collaborative=False, use_diversity=False),
    "content_collab": PipelineConfig(use_collaborative=True, use_diversity=False),
    "content_mmr": PipelineConfig(use_collaborative=False, use_diversity=True),
    "full_cascade": PipelineConfig(use_collaborative=True, use_diversity=True),
}

# Negatives sampled per session for Experiment B. 99 + the injected target gives the
# 100-item candidate set used throughout the sequential-recommendation literature.
DEFAULT_NEGATIVES = 99

# Minimum genre tags a negative must carry in the matched condition. Set at three
# because 90% of held-out targets (126/140) clear that bar, so it removes tag richness
# as a discriminating cue without shrinking the pool to nothing.
MATCHED_MIN_GENRES = 3

# A session contributes to a condition only if its pool offers at least this many
# usable negatives; ranking against a handful of distractors measures nothing.
MIN_NEGATIVES = 20

ARM_LABELS = {
    "random_catalogue": "Random (whole catalogue)",
    "random_pool": "Random (within retrieved pool)",
    "popularity": "Most popular",
    "content_only": "NextTrack: content only",
    "content_collab": "NextTrack: content + collaborative",
    "content_mmr": "NextTrack: content + MMR",
    "full_cascade": "NextTrack: full cascade",
}


# --------------------------------------------------------------------------- corpus


class Corpus:
    """The harvested snapshot, exposed in the shape the data clients return."""

    def __init__(self, payload: dict) -> None:
        self.tracks: dict[str, dict] = payload["tracks"]
        self.similar_artists: dict[str, dict[str, float]] = payload["similar_artists"]
        # Real MusicBrainz tag-search responses, in MusicBrainz's own order, recorded
        # by augment_catalogue.py. Replaying these makes the candidate pool identical
        # to what the live engine would retrieve.
        self.tag_search: dict[str, list[str]] = payload.get("tag_search", {})
        self.by_genre: dict[str, list[str]] = {}
        for mbid, track in sorted(self.tracks.items()):
            for genre in track.get("genres", []):
                self.by_genre.setdefault(genre.strip().lower(), []).append(mbid)

    def metadata(self, mbid: str) -> dict | None:
        track = self.tracks.get(mbid)
        if track is None:
            return None
        return {k: v for k, v in track.items() if k != "acoustic"}

    def acoustic(self, mbid: str) -> dict | None:
        track = self.tracks.get(mbid)
        return dict(track["acoustic"]) if track and track.get("acoustic") else None

    def search_by_tag(self, tag: str, limit: int) -> list[dict]:
        key = tag.strip().lower()
        # Prefer the recorded live response; fall back to a corpus-wide genre lookup
        # only for a tag the augmentation pass never saw.
        mbids = self.tag_search.get(key) or self.by_genre.get(key, [])
        return [m for m in (self.metadata(x) for x in mbids[:limit]) if m is not None]


def install_corpus(corpus: Corpus):
    """Patch every network client to read from the snapshot instead."""
    return (
        patch(
            "app.data.musicbrainz.get_recording",
            new=AsyncMock(side_effect=lambda m: corpus.metadata(m)),
        ),
        patch(
            "app.data.musicbrainz.search_by_tag",
            new=AsyncMock(side_effect=lambda t, limit: corpus.search_by_tag(t, limit)),
        ),
        patch(
            "app.data.acousticbrainz.get_features",
            new=AsyncMock(side_effect=lambda m: corpus.acoustic(m)),
        ),
        # The recommender resolves candidate acoustics in bulk, so patching only the
        # single-track client leaves the evaluation making live network requests —
        # which it did, silently, until this was noticed in the run log.
        patch(
            "app.data.acousticbrainz.get_features_bulk",
            new=AsyncMock(side_effect=lambda ms: {m: corpus.acoustic(m) for m in ms}),
        ),
        patch(
            "app.data.listenbrainz.get_similar_artists",
            new=AsyncMock(side_effect=lambda a: dict(corpus.similar_artists.get(a, {}))),
        ),
    )


def song_key(track: dict) -> tuple[str, str]:
    """A release-independent identity for a recording: normalised (artist, title).

    MusicBrainz issues a distinct recording identifier per release, remaster and
    compilation appearance, so exact-identifier matching understates reachability.
    Bracketed suffixes ("(Remastered 2011)", "[Live]") and punctuation are stripped so
    that the same song under a different release counts as the same song.
    """

    def norm(value: str) -> str:
        folded = unicodedata.normalize("NFKD", value or "").lower()
        folded = re.sub(r"\(.*?\)|\[.*?\]", "", folded)
        return re.sub(r"[^a-z0-9]+", "", folded)

    return norm(track.get("artist", "")), norm(track.get("title", ""))


# -------------------------------------------------------------------------- metrics


def ndcg_at_k(ranked_ids: list[str], target: str, k: int) -> float:
    """nDCG with a single relevant item: 1/log2(rank+1), or 0 if outside the top K."""
    for index, mbid in enumerate(ranked_ids[:k]):
        if mbid == target:
            return 1.0 / math.log2(index + 2)
    return 0.0


def reciprocal_rank(ranked_ids: list[str], target: str) -> float:
    for index, mbid in enumerate(ranked_ids):
        if mbid == target:
            return 1.0 / (index + 1)
    return 0.0


def novelty(ranked_ids: list[str], popularity: Counter, total: int, k: int) -> float:
    """Mean self-information of the recommended items (Celma and Herrera, 2008).

    A track played in every session carries no novelty; one played in a handful
    carries a lot. Unseen tracks are floored at one occurrence so the log is finite.
    """
    values = []
    for mbid in ranked_ids[:k]:
        count = max(popularity.get(mbid, 0), 1)
        values.append(-math.log2(count / total))
    return statistics.fmean(values) if values else 0.0


# ----------------------------------------------------------------------------- arms


def rank_random_catalogue(catalogue: list[str], history: set[str], rng, k: int) -> list[str]:
    pool = [m for m in catalogue if m not in history]
    rng.shuffle(pool)
    return pool[:k]


def rank_popularity(
    candidates: list[str], popularity: Counter, k: int
) -> list[str]:
    return sorted(candidates, key=lambda m: (-popularity.get(m, 0), m))[:k]


# ------------------------------------------------------------------------ evaluation


async def _prepare_candidates(corpus: Corpus, mbids: list[str]) -> list[dict]:
    """Resolve a candidate set through the production resolution path."""
    raw = []
    for mbid in mbids:
        track = corpus.tracks.get(mbid)
        if track is None:
            continue
        candidate = {key: value for key, value in track.items() if key != "acoustic"}
        candidate["mbid"] = mbid
        raw.append(candidate)
    return await recommender._resolve_candidates(raw) if raw else []


async def _rank_arm(
    arm: str,
    config,
    history_tracks: list[dict],
    candidates: list[dict],
    affinity: dict[str, float],
    catalogue: list[str],
    popularity: Counter,
    rng: random.Random,
    k: int,
) -> list[str]:
    """Rank one arm over a prepared candidate set, returning the top-k identifiers."""
    if arm == "random_catalogue":
        pool = [m for m in catalogue if m not in {t["mbid"] for t in history_tracks}]
        rng.shuffle(pool)
        return pool[:k]
    if arm == "random_pool":
        shuffled = [t["mbid"] for t in candidates]
        rng.shuffle(shuffled)
        return shuffled[:k]
    if arm == "popularity":
        return sorted(
            (t["mbid"] for t in candidates),
            key=lambda m: (-popularity.get(m, 0), m),
        )[:k]
    # Engine arms use the production ranking function directly.
    ranked = recommender._rank(history_tracks, candidates, affinity, config)
    return [track["mbid"] for _, track in ranked][:k]


async def evaluate(k: int, negatives: int) -> dict:
    corpus = Corpus(json.loads(CORPUS_PATH.read_text(encoding="utf-8")))
    sessions = json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))
    catalogue = sorted(corpus.tracks)
    logger.info("%d sessions, %d catalogue tracks", len(sessions), len(catalogue))

    # Popularity is computed from the evaluation corpus itself — the same aggregate
    # signal a real popularity baseline would have, with no access to the held-out item.
    popularity: Counter[str] = Counter()
    for session in sessions:
        popularity.update(session["history"])
    total_plays = max(sum(popularity.values()), 1)

    params = RecommendParams(tempo_range=(settings.TEMPO_MIN, settings.TEMPO_MAX))
    per_session: list[dict] = []
    reachability: list[dict] = []
    recommended_items: dict[str, set[str]] = {arm: set() for arm in ARMS}
    latencies: list[float] = []

    patches = install_corpus(corpus)
    for p in patches:
        p.start()
    try:
        for index, session in enumerate(sessions, 1):
            history, target = session["history"], session["target"]
            rng = random.Random(RANDOM_SEED + index)
            target_track = corpus.tracks.get(target)
            if target_track is None:
                continue

            # --- Experiment A: what does the real retrieval stage actually return? ---
            started = time.perf_counter()
            try:
                pool = await _candidate_pool(history, params)
            except recommender.RecommendationError as exc:
                logger.debug("session %d unrankable: %s", index, exc.reason)
                per_session.append({"session": index, "failed": exc.reason})
                continue
            latencies.append(time.perf_counter() - started)

            if not pool:
                per_session.append({"session": index, "failed": "no_candidates_found"})
                continue

            pool_ids = [t["mbid"] for t in pool]
            target_key = song_key(target_track)
            pool_keys = {song_key(t) for t in pool}
            pool_artists = {song_key(t)[0] for t in pool}
            reach = {
                "session": index,
                "pool_size": len(pool_ids),
                "exact_mbid": target in pool_ids,
                "same_song": target_key in pool_keys,
                "same_artist": target_key[0] in pool_artists,
            }
            reachability.append(reach)

            # --- Experiment B: rank the target against sampled negatives -------------
            # The target is injected deliberately; Experiment A already reports that
            # retrieval does not surface it. Negatives come from the pool the engine
            # really retrieved, so the distractors are the ones it would truly face.
            history_ids = set(history)
            available = [m for m in pool_ids if m != target and m not in history_ids]
            well_tagged = [
                m
                for m in available
                if len(corpus.tracks.get(m, {}).get("genres", [])) >= MATCHED_MIN_GENRES
            ]

            resolved = await asyncio.gather(
                *(recommender._resolve_track_features(m) for m in history)
            )
            history_tracks = [t for t in resolved if t is not None]
            if not history_tracks:
                per_session.append({"session": index, "failed": "no_history_resolved"})
                continue

            affinity = await recommender._collaborative_affinity(
                history_tracks, ARMS["full_cascade"]
            )

            row: dict = {
                "session": index,
                "history_len": len(history),
                "pool_size": len(pool_ids),
                "well_tagged_negatives_available": len(well_tagged),
                **{f"reach_{key}": reach[key] for key in ("exact_mbid", "same_song", "same_artist")},
            }

            for condition, source in (("unmatched", available), ("matched", well_tagged)):
                if len(source) < MIN_NEGATIVES:
                    row[f"{condition}_skipped"] = True
                    continue
                chosen = list(source)
                rng.shuffle(chosen)
                candidates = await _prepare_candidates(
                    corpus, [target, *chosen[:negatives]]
                )
                if not candidates:
                    row[f"{condition}_skipped"] = True
                    continue
                row[f"{condition}_candidate_set_size"] = len(candidates)

                for arm, config in ARMS.items():
                    ranked_ids = await _rank_arm(
                        arm, config, history_tracks, candidates, affinity,
                        catalogue, popularity, rng, k,
                    )
                    if condition == "unmatched":
                        recommended_items[arm].update(ranked_ids)
                    vectors = _vectors_for(corpus, ranked_ids)
                    row[f"{condition}:{arm}"] = {
                        "hit@1": float(bool(ranked_ids[:1] == [target])),
                        f"hit@{k}": float(target in ranked_ids),
                        f"ndcg@{k}": ndcg_at_k(ranked_ids, target, k),
                        "mrr": reciprocal_rank(ranked_ids, target),
                        f"ild@{k}": intra_list_diversity(vectors),
                        f"novelty@{k}": novelty(ranked_ids, popularity, total_plays, k),
                    }
            per_session.append(row)
            if index % 10 == 0:
                logger.info("evaluated %d/%d sessions", index, len(sessions))
    finally:
        for p in patches:
            p.stop()

    scored = [r for r in per_session if "failed" not in r]

    def _summarise(condition: str) -> tuple[dict, list[dict]]:
        rows = [r for r in scored if f"{condition}:full_cascade" in r]
        summary: dict = {}
        for arm in ARMS:
            key = f"{condition}:{arm}"
            metric_names = list(rows[0][key]) if rows else []
            summary[arm] = {
                "label": ARM_LABELS[arm],
                **{
                    name: round(statistics.fmean([r[key][name] for r in rows]), 4)
                    if rows
                    else 0.0
                    for name in metric_names
                },
            }
            if condition == "unmatched":
                summary[arm]["coverage"] = round(
                    len(recommended_items[arm]) / max(len(catalogue), 1), 4
                )
            else:
                summary[arm]["coverage"] = 0.0
        return summary, rows

    summary, unmatched_rows = _summarise("unmatched")
    matched_summary, matched_rows = _summarise("matched")

    def _rate(key: str) -> float:
        return (
            round(statistics.fmean([float(r[key]) for r in reachability]), 4)
            if reachability
            else 0.0
        )

    return {
        "config": {
            "k": k,
            "negatives_sampled": negatives,
            "sessions_total": len(sessions),
            "sessions_scored": len(scored),
            "catalogue_size": len(catalogue),
            "candidate_pool_size": settings.CANDIDATE_POOL_SIZE,
            "collab_weight": settings.COLLAB_WEIGHT,
            "mmr_lambda": settings.MMR_LAMBDA,
            "random_seed": RANDOM_SEED,
            "note": (
                "Ranking metrics come from Experiment B, in which the held-out track "
                "is injected into the candidate set. They measure ranking given "
                "reachability, NOT end-to-end accuracy — see retrieval_reachability."
            ),
        },
        "retrieval_reachability": {
            "sessions_measured": len(reachability),
            "exact_mbid": _rate("exact_mbid"),
            "same_song": _rate("same_song"),
            "same_artist": _rate("same_artist"),
            "mean_pool_size": round(
                statistics.fmean([r["pool_size"] for r in reachability]), 1
            )
            if reachability
            else 0.0,
        },
        "latency_seconds": {
            "mean": round(statistics.fmean(latencies), 4) if latencies else 0.0,
            "median": round(statistics.median(latencies), 4) if latencies else 0.0,
            "p95": round(sorted(latencies)[int(len(latencies) * 0.95)], 4)
            if len(latencies) > 1
            else 0.0,
        },
        "failures": Counter(r["failed"] for r in per_session if "failed" in r),
        "arms": summary,
        "arms_matched": matched_summary,
        "sessions_unmatched": len(unmatched_rows),
        "sessions_matched": len(matched_rows),
        "significance": _significance(unmatched_rows, k, "unmatched"),
        "significance_matched": _significance(matched_rows, k, "matched"),
        "per_session": per_session,
    }


# Pairs worth testing: the engine against each baseline (does the cascade beat the
# obvious alternatives?) and each ablation against the full pipeline (does each stage
# earn its place?). Testing every pair would invite a multiple-comparisons problem for
# no gain.
_COMPARISONS = [
    ("full_cascade", "random_pool"),
    ("full_cascade", "random_catalogue"),
    ("full_cascade", "popularity"),
    ("full_cascade", "content_only"),
    ("content_collab", "content_only"),
    ("content_mmr", "content_only"),
]


def _significance(scored: list[dict], k: int, condition: str) -> dict:
    """Wilcoxon signed-rank tests on paired per-session nDCG, arm against arm."""
    metric = f"ndcg@{k}"
    results = {}
    for arm_a, arm_b in _COMPARISONS:
        a = [row[f"{condition}:{arm_a}"][metric] for row in scored]
        b = [row[f"{condition}:{arm_b}"][metric] for row in scored]
        differences = [x - y for x, y in zip(a, b, strict=True)]
        non_zero = [d for d in differences if d != 0]

        entry = {
            "metric": metric,
            "mean_difference": round(statistics.fmean(differences), 4) if differences else 0.0,
            "sessions_differing": len(non_zero),
            "sessions_a_better": sum(1 for d in non_zero if d > 0),
        }
        # Wilcoxon is undefined when every pair ties: the two arms produced identical
        # per-session scores, which is a result in itself rather than a test failure.
        if len(non_zero) < 6:
            entry["p_value"] = None
            entry["note"] = (
                "too few differing sessions for a meaningful signed-rank test"
            )
        else:
            statistic, p_value = wilcoxon(a, b, zero_method="wilcox")
            entry["statistic"] = float(statistic)
            entry["p_value"] = round(float(p_value), 5)
            entry["significant_at_0.05"] = bool(p_value < 0.05)
        results[f"{arm_a} vs {arm_b}"] = entry
    return results


async def _candidate_pool(history: list[str], params) -> list[dict]:
    """Re-derive the retrieved candidate pool for a session (before any ranking)."""
    resolved = await asyncio.gather(
        *(recommender._resolve_track_features(m) for m in history)
    )
    tracks = [t for t in resolved if t is not None]
    genres = recommender._top_genres(tracks, recommender._TOP_GENRE_TAGS)
    raw = await recommender._retrieve_candidates(genres)
    history_ids = set(history)
    candidates = await asyncio.gather(
        *(
            recommender._resolve_track_features(rec["mbid"], metadata=rec)
            for mbid, rec in raw.items()
            if mbid not in history_ids
        )
    )
    tempo_min, tempo_max = params.tempo_range
    return [c for c in candidates if c and tempo_min <= c["tempo"] <= tempo_max]


def _vectors_for(corpus: Corpus, mbids: list[str]):
    """Build comparable vectors for a recommended list, on its own local vocabulary."""
    tracks = []
    for mbid in mbids:
        track = corpus.tracks.get(mbid)
        if track is None:
            continue
        acoustic = track.get("acoustic") or feat.DEFAULT_ACOUSTIC
        tracks.append({**acoustic, "genres": track.get("genres", [])})
    feat.reset_vocabulary()
    for track in tracks:
        feat.observe_track(track["genres"])
    return [feat.build_feature_vector(t) for t in tracks]


# ------------------------------------------------------------------------------ io


def write_outputs(results: dict, out_dir: pathlib.Path, k: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "offline_eval_results.json").write_text(
        json.dumps(results, indent=1, default=str), encoding="utf-8"
    )

    metric_keys = [
        "hit@1", f"hit@{k}", f"ndcg@{k}", "mrr", f"ild@{k}", f"novelty@{k}", "coverage"
    ]
    with (out_dir / "offline_eval_summary.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["condition", "arm", "label", *metric_keys])
        for condition, key in (("unmatched", "arms"), ("matched", "arms_matched")):
            for arm, row in results[key].items():
                writer.writerow(
                    [condition, arm, row["label"], *[row[name] for name in metric_keys]]
                )

    with (out_dir / "offline_eval_reachability.csv").open(
        "w", newline="", encoding="utf-8"
    ) as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        for name, value in results["retrieval_reachability"].items():
            writer.writerow([name, value])

    with (out_dir / "offline_eval_per_session.csv").open(
        "w", newline="", encoding="utf-8"
    ) as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "session", "condition", "arm", "history_len", "pool_size",
                "reach_exact_mbid", "reach_same_song", "reach_same_artist",
                *metric_keys[:-1],
            ]
        )
        for row in results["per_session"]:
            if "failed" in row:
                continue
            for condition in ("unmatched", "matched"):
                for arm in results["arms"]:
                    cell = row.get(f"{condition}:{arm}")
                    if cell is None:
                        continue
                    writer.writerow(
                        [
                            row["session"], condition, arm, row["history_len"],
                            row["pool_size"], row["reach_exact_mbid"],
                            row["reach_same_song"], row["reach_same_artist"],
                            *[cell[name] for name in metric_keys[:-1]],
                        ]
                    )
    logger.info("wrote results to %s", out_dir)


def print_table(results: dict, k: int) -> None:
    reach = results["retrieval_reachability"]
    print("\n" + "=" * 82)
    print("EXPERIMENT A - retrieval reachability (end-to-end reality)")
    print("=" * 82)
    print(f"  sessions measured                     {reach['sessions_measured']}")
    print(f"  mean retrieved pool size              {reach['mean_pool_size']}")
    print(f"  held-out track in pool, exact MBID    {reach['exact_mbid']:.4f}")
    print(f"  held-out song in pool (artist+title)  {reach['same_song']:.4f}")
    print(f"  held-out ARTIST anywhere in pool      {reach['same_artist']:.4f}")

    keys = ["hit@1", f"hit@{k}", f"ndcg@{k}", "mrr", f"ild@{k}", "coverage"]
    width = max(len(key) for key in keys) + 4
    cfg = results["config"]

    for title, arms_key, count_key, sig_key in (
        (
            f"EXPERIMENT B1 - target + {cfg['negatives_sampled']} negatives sampled freely",
            "arms", "sessions_unmatched", "significance",
        ),
        (
            f"EXPERIMENT B2 - CONTROL: negatives restricted to >= "
            f"{MATCHED_MIN_GENRES} genre tags",
            "arms_matched", "sessions_matched", "significance_matched",
        ),
    ):
        print("\n" + "=" * 82)
        print(title)
        print(f"  (target INJECTED; not end-to-end accuracy. n = {results[count_key]} sessions)")
        print("=" * 82)
        header = f"{'arm':<36}" + "".join(f"{key:>{width}}" for key in keys)
        print(header)
        print("-" * len(header))
        for row in results[arms_key].values():
            print(f"{row['label']:<36}" + "".join(f"{row[key]:>{width}.4f}" for key in keys))

        print(f"\n  {'Wilcoxon signed-rank (paired nDCG)':<44}{'mean diff':>12}{'p':>11}")
        print("  " + "-" * 67)
        for pair, srow in results[sig_key].items():
            p = srow["p_value"]
            p_text = "        n/a" if p is None else f"{p:>11.5f}"
            print(f"  {pair:<44}{srow['mean_difference']:>12.4f}{p_text}")

    print(f"\nlatency (s), snapshot-backed: {results['latency_seconds']}")
    print(f"sessions scored: {cfg['sessions_scored']}/{cfg['sessions_total']}")
    if results["failures"]:
        print(f"unrankable sessions: {dict(results['failures'])}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--negatives", type=int, default=DEFAULT_NEGATIVES)
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=BACKEND.parent / "docs" / "final-evidence",
    )
    args = parser.parse_args()

    outcome = asyncio.run(evaluate(args.k, args.negatives))
    print_table(outcome, args.k)
    write_outputs(outcome, args.out, args.k)
