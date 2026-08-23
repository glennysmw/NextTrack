"""Measure end-to-end /recommend latency against the live upstream services.

The offline evaluation runs against a snapshot, so its timings say nothing about what
a user waits for. This benchmark answers that separately, against a *freshly started*
backend so the cache states are honest, and reports three scenarios because they are
dominated by different costs:

``first_request``      the very first request after startup — nothing cached anywhere,
                       so latency is dominated by MusicBrainz's 1 req/sec rate limit
                       across three genre searches plus per-candidate resolution.
``new_history_warm``   a different listening history on a process whose genre pools and
                       track features are partly warm — the realistic steady state.
``repeat_identical``   the same request again: everything cached, and the result must
                       also be identical, which is the reproducibility check.

The distinction matters because the candidate-pool cache added during the final
engineering pass changes these three very differently, and reporting a single average
would hide that.

Requires a freshly started backend and live network access. Usage:
    python scripts/latency_benchmark.py [--url http://localhost:8000] [--runs 6]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.seeds import SEED_TRACKS  # noqa: E402

BACKEND = pathlib.Path(__file__).resolve().parents[1]
SESSIONS_PATH = BACKEND / "data" / "eval_sessions.json"


def histories(limit: int) -> list[list[str]]:
    """Distinct listening histories to measure, preferring the harvested sessions."""
    if SESSIONS_PATH.exists():
        sessions = json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))
        if sessions:
            return [s["history"][:3] for s in sessions[:limit]]
    # Fall back to the verified cold-start seeds, one history per seed track.
    return [[mbid] for mbid, _title, _artist in SEED_TRACKS[:limit]]


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def _summarise(durations: list[float]) -> dict:
    if not durations:
        return {"samples": 0}
    return {
        "samples": len(durations),
        "mean_seconds": round(statistics.fmean(durations), 3),
        "median_seconds": round(statistics.median(durations), 3),
        "p95_seconds": round(_percentile(durations, 0.95), 3),
        "min_seconds": round(min(durations), 3),
        "max_seconds": round(max(durations), 3),
    }


def _recommend(client: httpx.Client, url: str, history: list[str]):
    started = time.perf_counter()
    resp = client.post(
        f"{url}/api/v1/recommend", json={"track_history": history}, timeout=180
    )
    elapsed = time.perf_counter() - started
    return elapsed, (resp.json() if resp.status_code == 200 else None), resp.status_code


def main(url: str, runs: int, out: pathlib.Path) -> int:
    samples = histories(runs)
    if not samples:
        print("no histories available to benchmark")
        return 1

    first: list[float] = []
    warm_new: list[float] = []
    repeat: list[float] = []
    identical = 0
    compared = 0
    unrankable = 0

    with httpx.Client() as client:
        try:
            health = client.get(f"{url}/api/v1/health", timeout=60).json()
        except Exception as exc:  # noqa: BLE001
            print(f"backend not reachable at {url}: {exc}")
            return 1
        if health["cache"]["feature_size"] or health["cache"]["candidate_pools"]:
            print(
                "WARNING: the backend cache is already warm; restart it for an honest "
                "first_request measurement."
            )
        print(f"upstream sources: {health['sources']}")

        for index, history in enumerate(samples):
            elapsed, body, status = _recommend(client, url, history)
            if body is None:
                unrankable += 1
                print(f"  [{index}] {status} — history not rankable, skipped")
                continue
            (first if index == 0 else warm_new).append(elapsed)

            repeat_elapsed, repeat_body, _ = _recommend(client, url, history)
            if repeat_body is not None:
                repeat.append(repeat_elapsed)
                compared += 1
                identical += int(repeat_body["track_id"] == body["track_id"])
            print(
                f"  [{index}] {elapsed:6.2f}s then {repeat_elapsed:5.2f}s — "
                f"{body['title']} / {body['artist']}"
            )

        final_health = client.get(f"{url}/api/v1/health", timeout=60).json()

    results = {
        "url": url,
        "histories_attempted": len(samples),
        "histories_unrankable": unrankable,
        "determinism": {
            "repeat_pairs_compared": compared,
            "repeat_pairs_identical": identical,
            "all_identical": compared > 0 and compared == identical,
        },
        "cache_after_run": final_health["cache"],
        "sources": final_health["sources"],
        "scenarios": {
            "first_request": _summarise(first),
            "new_history_warm": _summarise(warm_new),
            "repeat_identical": _summarise(repeat),
        },
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "latency_benchmark.json").write_text(
        json.dumps(results, indent=1), encoding="utf-8"
    )
    print("\n" + json.dumps(results["scenarios"], indent=1))
    print(f"determinism: {results['determinism']}")
    print(f"wrote {out / 'latency_benchmark.json'}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--runs", type=int, default=6)
    parser.add_argument(
        "--out", type=pathlib.Path, default=BACKEND.parent / "docs" / "final-evidence"
    )
    args = parser.parse_args()
    sys.exit(main(args.url, args.runs, args.out))
