"""Offline evaluation and ablation study. Run after ``build_eval_dataset.py``.

Protocol
--------
For each held-out session the engine receives the session's history and must rank a
candidate pool; the session's actual next track is the single relevant item. Every arm
— the three baselines and the four engine configurations — ranks the *same* pool for
the same session, so differences between arms are attributable to ranking, not to
retrieval luck.

The engine arms call ``recommender.recommend_ranked`` itself, with the data clients
redirected at the harvested corpus. This is deliberate: an evaluation that
re-implements the scoring logic measures the re-implementation, not the system. The
only thing stubbed is the network.

Significance
------------
Because every arm is scored on the *same* sessions, the per-session results are paired,
and a difference in means between two arms can be tested directly with a Wilcoxon
signed-rank test (Wilcoxon, 1945) — the same non-parametric paired test the project's
planned user study specified, applied here to offline results. It is used rather than a
paired t-test because per-session nDCG is bounded, heavily tied at zero, and plainly
not normal. Reporting it matters: with a sample this size, an apparent gap of a few
points between two engine configurations may be indistinguishable from noise, and
saying so is more useful than ranking arms on a difference that will not replicate.

Metrics (Shani and Gunawardana, 2011; Kaminskas and Bridge, 2016)
----------------------------------------------------------------
HitRate@K / Precision@K   did the held-out track appear in the top K
nDCG@K                    rank-discounted gain, sensitive to *where* in the list it landed
MRR                       mean reciprocal rank of the held-out track
ILD@K                     intra-list diversity — mean pairwise (1 − cosine) of the list
Novelty@K                 mean −log2(popularity) — how far from the head of the catalogue
Coverage                  share of the catalogue ever recommended across all sessions
Retrieval recall          share of sessions whose held-out track reached the pool at all

Usage:  python scripts/offline_eval.py [--k 10] [--out ../docs/final-evidence]
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
import statistics
import sys
import time
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
    """Patch the three network clients to read from the snapshot instead."""
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
        patch(
            "app.data.listenbrainz.get_similar_artists",
            new=AsyncMock(side_effect=lambda a: dict(corpus.similar_artists.get(a, {}))),
        ),
    )


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


async def evaluate(k: int) -> dict:
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
    recommended_items: dict[str, set[str]] = {arm: set() for arm in ARMS}
    latencies: list[float] = []

    patches = install_corpus(corpus)
    for p in patches:
        p.start()
    try:
        for index, session in enumerate(sessions, 1):
            history, target = session["history"], session["target"]
            rng = random.Random(RANDOM_SEED + index)

            # One engine run supplies the candidate pool every arm ranks, so the
            # baselines are scored on exactly the same retrieval as the engine.
            started = time.perf_counter()
            try:
                ranked_full, _ = await recommender.recommend_ranked(
                    history, params, ARMS["full_cascade"]
                )
            except recommender.RecommendationError as exc:
                logger.debug("session %d unrankable: %s", index, exc.reason)
                per_session.append({"session": index, "failed": exc.reason})
                continue
            latencies.append(time.perf_counter() - started)

            pool = await _candidate_pool(history, params)
            pool_ids = [t["mbid"] for t in pool]
            retrieved = target in pool_ids

            row: dict = {
                "session": index,
                "history_len": len(history),
                "pool_size": len(pool_ids),
                "retrieved": retrieved,
            }

            for arm, config in ARMS.items():
                if arm == "random_catalogue":
                    ranked_ids = rank_random_catalogue(catalogue, set(history), rng, k)
                elif arm == "random_pool":
                    shuffled = list(pool_ids)
                    rng.shuffle(shuffled)
                    ranked_ids = shuffled[:k]
                elif arm == "popularity":
                    ranked_ids = rank_popularity(pool_ids, popularity, k)
                elif arm == "full_cascade":
                    ranked_ids = [t["mbid"] for _, t in ranked_full][:k]
                else:
                    ranked, _ = await recommender.recommend_ranked(history, params, config)
                    ranked_ids = [t["mbid"] for _, t in ranked][:k]

                recommended_items[arm].update(ranked_ids)
                vectors = _vectors_for(corpus, ranked_ids)
                row[arm] = {
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
    # Sessions whose held-out track never entered the candidate pool are unwinnable
    # for *every* arm, so they depress all accuracy figures equally. Reporting the
    # conditional averages alongside separates a retrieval failure (the genre-gated
    # MusicBrainz search never surfaced the track) from a ranking failure (it was
    # there and the engine put it too low) — two very different problems.
    retrieved_only = [r for r in scored if r["retrieved"]]

    def _mean(rows: list[dict], arm: str, key: str) -> float:
        return round(statistics.fmean([r[arm][key] for r in rows]), 4) if rows else 0.0

    summary = {}
    for arm in ARMS:
        metric_names = list(scored[0][arm]) if scored else []
        summary[arm] = {
            "label": ARM_LABELS[arm],
            **{key: _mean(scored, arm, key) for key in metric_names},
            **{
                f"{key}|retrieved": _mean(retrieved_only, arm, key)
                for key in metric_names
                if key.startswith(("hit", "ndcg", "mrr"))
            },
            "coverage": round(len(recommended_items[arm]) / len(catalogue), 4),
        }

    comparisons = _significance(scored, k)

    return {
        "config": {
            "k": k,
            "sessions_total": len(sessions),
            "sessions_scored": len(scored),
            "sessions_retrieved": len(retrieved_only),
            "catalogue_size": len(catalogue),
            "candidate_pool_size": settings.CANDIDATE_POOL_SIZE,
            "collab_weight": settings.COLLAB_WEIGHT,
            "mmr_lambda": settings.MMR_LAMBDA,
            "random_seed": RANDOM_SEED,
        },
        "retrieval_recall": round(
            statistics.fmean([float(r["retrieved"]) for r in scored]), 4
        )
        if scored
        else 0.0,
        "latency_seconds": {
            "mean": round(statistics.fmean(latencies), 4) if latencies else 0.0,
            "median": round(statistics.median(latencies), 4) if latencies else 0.0,
            "p95": round(sorted(latencies)[int(len(latencies) * 0.95)], 4)
            if len(latencies) > 1
            else 0.0,
        },
        "failures": Counter(r["failed"] for r in per_session if "failed" in r),
        "arms": summary,
        "significance": comparisons,
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


def _significance(scored: list[dict], k: int) -> dict:
    """Wilcoxon signed-rank tests on paired per-session nDCG, arm against arm."""
    metric = f"ndcg@{k}"
    results = {}
    for arm_a, arm_b in _COMPARISONS:
        a = [row[arm_a][metric] for row in scored]
        b = [row[arm_b][metric] for row in scored]
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

    metric_keys = ["hit@1", f"hit@{k}", f"ndcg@{k}", "mrr", f"ild@{k}", f"novelty@{k}", "coverage"]
    with (out_dir / "offline_eval_summary.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["arm", "label", *metric_keys])
        for arm, row in results["arms"].items():
            writer.writerow([arm, row["label"], *[row[key] for key in metric_keys]])

    with (out_dir / "offline_eval_per_session.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["session", "arm", "history_len", "pool_size", "retrieved", *metric_keys[:-1]])
        for row in results["per_session"]:
            if "failed" in row:
                continue
            for arm in results["arms"]:
                writer.writerow(
                    [
                        row["session"], arm, row["history_len"], row["pool_size"], row["retrieved"],
                        *[row[arm][key] for key in metric_keys[:-1]],
                    ]
                )
    logger.info("wrote results to %s", out_dir)


def print_table(results: dict, k: int) -> None:
    for title, keys in (
        (
            "All scored sessions",
            ["hit@1", f"hit@{k}", f"ndcg@{k}", "mrr", f"ild@{k}", f"novelty@{k}", "coverage"],
        ),
        (
            "Sessions where the held-out track was retrieved",
            ["hit@1|retrieved", f"hit@{k}|retrieved", f"ndcg@{k}|retrieved", "mrr|retrieved"],
        ),
    ):
        header = f"{title:<34}" + "".join(f"{key:>17}" for key in keys)
        print("\n" + header)
        print("-" * len(header))
        for row in results["arms"].values():
            print(f"{row['label']:<34}" + "".join(f"{row[key]:>17.4f}" for key in keys))

    print(f"\n{'Wilcoxon signed-rank (paired per-session nDCG)':<46}{'mean diff':>12}{'p':>10}")
    print("-" * 68)
    for pair, row in results["significance"].items():
        p = row["p_value"]
        p_text = "  n/a" if p is None else f"{p:>10.5f}"
        print(f"{pair:<46}{row['mean_difference']:>12.4f}{p_text}")

    print(f"\nretrieval recall: {results['retrieval_recall']:.4f}")
    print(f"latency (s): {results['latency_seconds']}")
    cfg = results["config"]
    print(
        f"sessions scored: {cfg['sessions_scored']}/{cfg['sessions_total']} "
        f"(held-out track retrieved in {cfg['sessions_retrieved']})"
    )
    if results["failures"]:
        print(f"unrankable sessions: {dict(results['failures'])}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=BACKEND.parent / "docs" / "final-evidence",
    )
    args = parser.parse_args()

    outcome = asyncio.run(evaluate(args.k))
    print_table(outcome, args.k)
    write_outputs(outcome, args.out, args.k)
