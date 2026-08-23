"""Capture real request/response transcripts from a running NextTrack instance.

Everything written here is a verbatim exchange with the live API against live upstream
services — nothing is hand-written, so the API examples quoted in the report cannot
drift away from what the system actually returns. Error cases are exercised too, since
the failure contract (a machine-readable ``reason`` alongside a human ``detail``) is
part of what the API promises.

Requires a running backend. Usage:
    python scripts/capture_api_examples.py [--url http://localhost:8000]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import httpx

BACKEND = pathlib.Path(__file__).resolve().parents[1]

# Two real, verified MBIDs from the cold-start seed pool.
SEED_TEEN_SPIRIT = "775bd63d-a8ec-4ac5-b6ac-56fa105eac62"
SEED_BRIGHTSIDE = "cdd611f4-f270-405b-910b-fddf60dff322"


def call(client: httpx.Client, url: str, method: str, path: str, body: dict | None = None):
    started = time.perf_counter()
    if method == "GET":
        resp = client.get(f"{url}{path}", timeout=120)
    else:
        resp = client.post(f"{url}{path}", json=body, timeout=120)
    elapsed = round(time.perf_counter() - started, 3)
    try:
        payload = resp.json()
    except ValueError:
        payload = {"_raw": resp.text[:500]}
    return {
        "request": {"method": method, "path": path, **({"body": body} if body else {})},
        "response": {"status": resp.status_code, "elapsed_seconds": elapsed, "body": payload},
    }


CASES: list[tuple[str, str, str, dict | None]] = [
    ("health", "GET", "/api/v1/health", None),
    ("search", "POST", "/api/v1/search", {"query": "smells like teen spirit", "limit": 3}),
    ("top", "GET", "/api/v1/top", None),
    ("resolve", "POST", "/api/v1/resolve", {"title": "Mr. Brightside", "artist": "The Killers"}),
    ("recommend", "POST", "/api/v1/recommend", {"track_history": [SEED_TEEN_SPIRIT]}),
    (
        "recommend_multi_track_history",
        "POST",
        "/api/v1/recommend",
        {"track_history": [SEED_TEEN_SPIRIT, SEED_BRIGHTSIDE]},
    ),
    (
        "recommend_with_constraints",
        "POST",
        "/api/v1/recommend",
        {
            "track_history": [SEED_TEEN_SPIRIT],
            "params": {"tempo_range": [90, 150], "exclude_artists": ["Nirvana"]},
        },
    ),
    # --- error contract -----------------------------------------------------------
    ("error_empty_history", "POST", "/api/v1/recommend", {"track_history": []}),
    ("error_malformed_mbid", "POST", "/api/v1/recommend", {"track_history": ["not-an-mbid"]}),
    (
        "error_unknown_mbid",
        "POST",
        "/api/v1/recommend",
        {"track_history": ["00000000-0000-0000-0000-000000000000"]},
    ),
    (
        "error_impossible_tempo_window",
        "POST",
        "/api/v1/recommend",
        {"track_history": [SEED_TEEN_SPIRIT], "params": {"tempo_range": [199, 200]}},
    ),
    (
        "error_unknown_parameter_rejected",
        "POST",
        "/api/v1/recommend",
        {"track_history": [SEED_TEEN_SPIRIT], "params": {"not_a_real_param": 1}},
    ),
    ("error_empty_search_query", "POST", "/api/v1/search", {"query": "   "}),
]


def main(url: str, out: pathlib.Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    captured: dict[str, dict] = {}
    with httpx.Client() as client:
        try:
            client.get(f"{url}/api/v1/health", timeout=60)
        except Exception as exc:  # noqa: BLE001
            print(f"backend not reachable at {url}: {exc}")
            return 1
        for name, method, path, body in CASES:
            captured[name] = call(client, url, method, path, body)
            status = captured[name]["response"]["status"]
            print(f"  {status}  {method:<5} {path:<20} ({name})")

    # Determinism check: the same request twice must produce the same track.
    with httpx.Client() as client:
        first = call(client, url, "POST", "/api/v1/recommend", {"track_history": [SEED_BRIGHTSIDE]})
        second = call(client, url, "POST", "/api/v1/recommend", {"track_history": [SEED_BRIGHTSIDE]})
    captured["determinism_check"] = {
        "note": "Identical inputs must produce identical output — a stateless API "
        "that drifts between calls is not reproducible.",
        "first_track_id": first["response"]["body"].get("track_id"),
        "second_track_id": second["response"]["body"].get("track_id"),
        "identical": first["response"]["body"].get("track_id")
        == second["response"]["body"].get("track_id"),
    }
    print(f"  determinism: {captured['determinism_check']['identical']}")

    (out / "api_examples.json").write_text(
        json.dumps(captured, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"wrote {out / 'api_examples.json'}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument(
        "--out", type=pathlib.Path, default=BACKEND.parent / "docs" / "final-evidence"
    )
    args = parser.parse_args()
    sys.exit(main(args.url, args.out))
