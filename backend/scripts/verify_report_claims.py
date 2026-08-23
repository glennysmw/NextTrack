"""Verify every substantive claim in the final report against code and raw results.

Prose drifts from data. A number gets rounded during an edit, a metric is re-run and the
paragraph quoting it is not, a file the report names gets renamed. This script closes
that gap mechanically: it re-reads ``FinalReport.md`` and checks 85 assertions against
``offline_eval_results.json``, ``latency_benchmark.json``, the evaluation corpus, the
live configuration values, the test suite, and the files on disk.

It also checks two things that matter for academic integrity: that every in-text citation
appears in the reference list, and that no sentence claiming user-study results — which
were never gathered — has crept into the text.

Run it after any edit to the report or any re-run of the evaluation.

Usage:  python scripts/verify_report_claims.py     # exits non-zero on any mismatch
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
report = (ROOT / "FinalReport.md").read_text(encoding="utf-8")
results = json.loads((ROOT / "docs/final-evidence/offline_eval_results.json").read_text(encoding="utf-8"))
latency = json.loads((ROOT / "docs/final-evidence/latency_benchmark.json").read_text(encoding="utf-8"))
corpus = json.loads((ROOT / "backend/data/eval_corpus.json").read_text(encoding="utf-8"))
sessions = json.loads((ROOT / "backend/data/eval_sessions.json").read_text(encoding="utf-8"))
config = (ROOT / "backend/app/config.py").read_text(encoding="utf-8")

problems, checks = [], 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not ok:
        problems.append(f"{label}: {detail}")


arms = results["arms"]
reach = results["retrieval_reachability"]
sig = results["significance"]


def in_report(text: str) -> bool:
    return text in report


# --- numbers quoted in the report -------------------------------------------------
check("reachability exact", reach["exact_mbid"] == 0.0, str(reach["exact_mbid"]))
check("reachability same_song", reach["same_song"] == 0.0, str(reach["same_song"]))
check("reachability artist 0.130 quoted",
      abs(reach["same_artist"] - 0.130) < 0.001 and in_report("0.130"), str(reach["same_artist"]))
check("mean pool 145.7 quoted",
      abs(reach["mean_pool_size"] - 145.7) < 0.05 and in_report("145.7"), str(reach["mean_pool_size"]))
check("138 sessions quoted", reach["sessions_measured"] == 138 and in_report("138"), "")

for arm, metric, quoted in [
    ("content_only", "hit@1", "0.623"), ("content_only", "ndcg@10", "0.648"),
    ("content_only", "hit@10", "0.674"), ("content_only", "ild@10", "0.367"),
    ("content_collab", "ndcg@10", "0.704"), ("content_collab", "hit@1", "0.659"),
    ("content_collab", "ild@10", "0.421"),
    ("content_mmr", "hit@1", "0.565"), ("content_mmr", "hit@10", "0.877"),
    ("content_mmr", "ild@10", "0.735"),
    ("full_cascade", "ndcg@10", "0.695"), ("full_cascade", "hit@10", "0.855"),
    ("popularity", "ndcg@10", "0.231"), ("popularity", "hit@1", "0.188"),
    ("random_pool", "ndcg@10", "0.039"),
]:
    actual = arms[arm][metric]
    check(f"{arm}.{metric} == {quoted}",
          abs(actual - float(quoted)) < 0.0005 and in_report(quoted),
          f"actual {actual}, quoted {quoted}, in report: {in_report(quoted)}")

check("collab p=0.003", abs(sig["content_collab vs content_only"]["p_value"] - 0.003) < 0.0005
      and in_report("0.003"), str(sig["content_collab vs content_only"]["p_value"]))
check("mmr p=0.095", abs(sig["content_mmr vs content_only"]["p_value"] - 0.095) < 0.0006
      and in_report("0.095"), str(sig["content_mmr vs content_only"]["p_value"]))
check("full-vs-content p=0.195", abs(sig["full_cascade vs content_only"]["p_value"] - 0.195) < 0.0006
      and in_report("0.195"), str(sig["full_cascade vs content_only"]["p_value"]))
check("gain vs random pool 0.656",
      abs(sig["full_cascade vs random_pool"]["mean_difference"] - 0.656) < 0.0006 and in_report("0.656"), "")
check("gain vs popularity 0.464",
      abs(sig["full_cascade vs popularity"]["mean_difference"] - 0.4635) < 0.001 and in_report("0.464"), "")

# --- dataset figures ---------------------------------------------------------------
tracks = corpus["tracks"]
session_ids = {m for s in sessions for m in (*s["history"], s["target"])}
session_tracks = {m: tracks[m] for m in session_ids if m in tracks}
acoustic = sum(1 for v in session_tracks.values() if v.get("acoustic"))
pct = 100 * acoustic / len(session_tracks)
check("859 session tracks", len(session_tracks) == 859 and in_report("859"), str(len(session_tracks)))
check("65.8% acoustic", abs(pct - 65.8) < 0.1 and in_report("65.8"), f"{pct:.1f}")
check("140 sessions", len(sessions) == 140 and in_report("140"), str(len(sessions)))
check("24 listeners", len({s["listener"] for s in sessions}) == 24 and in_report("24"), "")
check("5,844 catalogue", len(tracks) == 5844 and in_report("5,844"), str(len(tracks)))
check("4,985 candidates added", len(tracks) - 859 == 4985 and in_report("4,985"), "")
artists = {v["artist_mbid"] for v in session_tracks.values() if v.get("artist_mbid")}
withsim = sum(1 for a in artists if corpus["similar_artists"].get(a))
check("94.0% artist similarity",
      abs(100 * withsim / len(artists) - 94.0) < 0.1 and in_report("94.0"),
      f"{100*withsim/len(artists):.1f}")
check("281 artists", len(artists) == 281 and in_report("281"), str(len(artists)))
check("99 negatives", results["config"]["negatives_sampled"] == 99 and in_report("99"), "")
check("n=93 control", results["sessions_matched"] == 93 and in_report("93"), str(results["sessions_matched"]))

# --- latency -----------------------------------------------------------------------
sc = latency["scenarios"]
check("155.4 s first request",
      abs(sc["first_request"]["median_seconds"] - 155.368) < 0.05 and in_report("155.4"), "")
check("29.0 s warm", abs(sc["new_history_warm"]["median_seconds"] - 29.034) < 0.05 and in_report("29.0"), "")
check("0.45 s repeat", abs(sc["repeat_identical"]["median_seconds"] - 0.447) < 0.005 and in_report("0.45"), "")
check("8/8 determinism", latency["determinism"]["all_identical"] and in_report("8/8"), "")

# --- configuration values quoted ----------------------------------------------------
check("collab weight 0.3", "COLLAB_WEIGHT = 0.3" in config and in_report("w = 0.3"), "")
check("mmr lambda 0.7", "MMR_LAMBDA = 0.7" in config and in_report("λ = 0.7"), "")
check("candidate pool 50", "CANDIDATE_POOL_SIZE = 50" in config, "")
check("tempo 40-200", "TEMPO_MIN = 40" in config and "TEMPO_MAX = 200" in config and in_report("40–200 BPM"), "")

# --- code artefacts the report names ------------------------------------------------
for path in [
    "backend/app/engine/collaborative.py", "backend/app/engine/diversity.py",
    "backend/app/engine/recommender.py", "backend/app/data/listenbrainz.py",
    "backend/scripts/offline_eval.py", "backend/scripts/adversarial_sweep.py",
    "backend/scripts/word_count.py", "backend/scripts/make_figures.py",
    "backend/tests/test_network_guard.py", "backend/tests/test_candidate_cache.py",
]:
    check(f"exists {path}", (ROOT / path).exists(), "missing")

for fig in re.findall(r"docs/final-evidence/([\w.]+\.png)", report):
    check(f"figure {fig}", (ROOT / "docs/final-evidence" / fig).exists(), "missing")

# --- test counts --------------------------------------------------------------------
pytest_out = subprocess.run(
    [str(ROOT / "backend/venv/Scripts/python.exe"), "-m", "pytest", "-q"],
    cwd=ROOT / "backend", capture_output=True, text=True,
).stdout
m = re.search(r"(\d+) passed", pytest_out)
backend_tests = int(m.group(1)) if m else 0
check("backend test count matches report",
      backend_tests == 121 and in_report("**121 tests**"), f"actual {backend_tests}")

# --- claims that must NOT appear -----------------------------------------------------
for forbidden in ["participants were recruited", "SUS score of", "we recruited",
                  "user study found", "participants reported"]:
    check(f"no fabricated study claim: {forbidden!r}", forbidden.lower() not in report.lower(), "")

# --- every in-text citation appears in the reference list ----------------------------
refs = report[report.index("\n## References"):]
cited = set(re.findall(r"\(([A-ZÇÒ][A-Za-zÇÒàé'\-]+(?: and [A-Za-zÇÒ][A-Za-z]+)?)(?:,? et al\.)?,? \d{4}", report))
for name in sorted(cited):
    surname = name.split(" and ")[0]
    check(f"citation {surname} in reference list", surname in refs, "not found")

print(f"{checks - len(problems)}/{checks} consistency checks passed")
if problems:
    print("\nPROBLEMS:")
    for problem in problems:
        print("  -", problem)
sys.exit(1 if problems else 0)
