"""Adversarial input sweep against a *running* API. Complements the test suite.

The pytest suite checks that documented behaviour works. This checks that undocumented
input does not produce something worse than a clean rejection: 32 hostile cases —
wrong types, wrong arity, oversized payloads, injection-shaped strings, reversed and
negative ranges, unicode, wrong methods, unknown routes.

The bar is deliberately low and specific: **nothing may return a 5xx that is not a
genuine upstream outage**, because a malformed client request reported as a server
fault is a contract violation. That bar caught one real defect (log entry D5c): a
whitespace-padded identifier passed validation, reached the MusicBrainz client
unstripped, retried eight times, and surfaced as a 503 blaming a service that was
working. It is kept as a script rather than folded into pytest because it needs a live
server and live upstreams, which the hermetic test suite deliberately forbids.

Usage (with the backend running):  python scripts/adversarial_sweep.py
"""
import sys

import httpx

URL = "http://localhost:8000"
BIG = "x" * 100_000
MBID = "cdd611f4-f270-405b-910b-fddf60dff322"

CASES = [
    # (name, method, path, json body or None, expected status set)
    ("empty body /recommend", "POST", "/api/v1/recommend", {}, {400, 422}),
    ("null history", "POST", "/api/v1/recommend", {"track_history": None}, {400, 422}),
    ("history not a list", "POST", "/api/v1/recommend", {"track_history": "abc"}, {400, 422}),
    ("history of ints", "POST", "/api/v1/recommend", {"track_history": [1, 2]}, {400, 422}),
    ("history of nulls", "POST", "/api/v1/recommend", {"track_history": [None]}, {400, 422}),
    ("nested list", "POST", "/api/v1/recommend", {"track_history": [[MBID]]}, {400, 422}),
    ("oversized string id", "POST", "/api/v1/recommend", {"track_history": [BIG]}, {400, 422}),
    ("21 ids (limit is 20)", "POST", "/api/v1/recommend", {"track_history": [MBID] * 21}, {400}),
    ("20 ids (at the limit)", "POST", "/api/v1/recommend", {"track_history": [MBID] * 20}, {200, 404}),
    ("uppercase MBID", "POST", "/api/v1/recommend", {"track_history": [MBID.upper()]}, {200, 404}),
    # Leniency is the intended behaviour here: the validator strips, so the route must
    # normalise and proceed. Before the fix this returned 503 after eight upstream retries.
    ("whitespace-padded MBID", "POST", "/api/v1/recommend", {"track_history": [f" {MBID} "]}, {200, 404}),
    ("SQL-ish injection", "POST", "/api/v1/recommend",
     {"track_history": ["'; DROP TABLE tracks;--"]}, {400}),
    ("path traversal in id", "POST", "/api/v1/recommend",
     {"track_history": ["../../etc/passwd"]}, {400}),
    ("params not an object", "POST", "/api/v1/recommend",
     {"track_history": [MBID], "params": "nope"}, {422}),
    ("tempo range reversed", "POST", "/api/v1/recommend",
     {"track_history": [MBID], "params": {"tempo_range": [200, 40]}}, {200, 404}),
    ("tempo range negative", "POST", "/api/v1/recommend",
     {"track_history": [MBID], "params": {"tempo_range": [-100, -1]}}, {200, 404, 422}),
    ("tempo range huge", "POST", "/api/v1/recommend",
     {"track_history": [MBID], "params": {"tempo_range": [0, 10**9]}}, {200, 404}),
    ("tempo range wrong arity", "POST", "/api/v1/recommend",
     {"track_history": [MBID], "params": {"tempo_range": [100]}}, {422}),
    ("tempo range non-numeric", "POST", "/api/v1/recommend",
     {"track_history": [MBID], "params": {"tempo_range": ["a", "b"]}}, {422}),
    ("exclude_artists not a list", "POST", "/api/v1/recommend",
     {"track_history": [MBID], "params": {"exclude_artists": "Nirvana"}}, {422, 200, 404}),
    ("huge exclusion list", "POST", "/api/v1/recommend",
     {"track_history": [MBID], "params": {"exclude_artists": [f"a{i}" for i in range(5000)]}},
     {200, 404}),
    ("unicode / emoji search", "POST", "/api/v1/search", {"query": "日本語 🎵 música"}, {200, 503}),
    ("oversized search query", "POST", "/api/v1/search", {"query": BIG}, {200, 400, 422, 503}),
    ("search limit 0", "POST", "/api/v1/search", {"query": "test", "limit": 0}, {422}),
    ("search limit 999", "POST", "/api/v1/search", {"query": "test", "limit": 999}, {422}),
    ("search limit negative", "POST", "/api/v1/search", {"query": "test", "limit": -5}, {422}),
    ("resolve empty title", "POST", "/api/v1/resolve", {"title": "", "artist": "x"}, {422}),
    ("resolve missing artist", "POST", "/api/v1/resolve", {"title": "x"}, {422}),
    ("resolve lucene metachars", "POST", "/api/v1/resolve",
     {"title": 'a" OR b:"c', "artist": 'x\\"y'}, {200, 503}),
    ("unknown endpoint", "GET", "/api/v1/nope", None, {404}),
    ("wrong method on /top", "POST", "/api/v1/top", {}, {405}),
    ("wrong method on /recommend", "GET", "/api/v1/recommend", None, {405}),
]


def main() -> int:
    failures = []
    with httpx.Client(timeout=180) as client:
        for name, method, path, body, expected in CASES:
            try:
                if method == "GET":
                    resp = client.get(URL + path)
                else:
                    resp = client.post(URL + path, json=body)
                status = resp.status_code
                ok = status in expected
                # A 500 is always a failure regardless of the expectation set.
                if status >= 500 and status != 503:
                    ok = False
                mark = "ok  " if ok else "FAIL"
                print(f"  {mark} {status}  {name}")
                if not ok:
                    failures.append((name, status, sorted(expected), resp.text[:200]))
            except Exception as exc:  # noqa: BLE001
                print(f"  FAIL EXC {name}: {exc}")
                failures.append((name, "exception", sorted(expected), str(exc)[:200]))

    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} behaved acceptably")
    if failures:
        print("\nFAILURES:")
        for name, status, expected, detail in failures:
            print(f"  {name}: got {status}, expected one of {expected}")
            print(f"    {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
