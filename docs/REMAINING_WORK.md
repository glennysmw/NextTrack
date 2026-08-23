# NextTrack — Remaining Work & Improvement Plan

**For:** CM3070 Final Year Project — Final Report (7.2 Project Idea 2: NextTrack: A music recommendation API)
**Author:** Soe Ming Wei, Glenn (230657168) — Supervisor: Yeo Sze Wee
**Due:** 28 September 2026, 21:00 +08:00
**Basis:** the 8 objectives in the preliminary report (§1.4), cross-checked against the actual codebase as of this document's writing, and against the final report brief (`FYP_FINALREPORT_INSTRUCTIONS.txt`).

This document is a gap analysis, not a status report you submit — it exists to tell you exactly what to build, test, write, and record between now and the deadline, in priority order.

---

## 0. Read this first: what changed between the draft and final report briefs

| | Draft report | Final report |
|---|---|---|
| Total word cap | 9,500 | **10,500** |
| Introduction | ≤1000 | ≤1000 (unchanged) |
| Literature Review | ≤2500 | ≤2500 (unchanged, but must incorporate feedback received) |
| Design | ≤2000 | ≤2000 (unchanged, but must incorporate feedback received) |
| Implementation | ≤2000 | **≤2500** (must now cover the *entire* implementation, not just the prototype) |
| Evaluation | ≤2500 | ≤2500 (but must now report *actual* evaluation results, not a plan) |
| Conclusion | ≤1000 | ≤1000 (unchanged) |
| Code repository | not required | **Required** — a link to a publicly viewable repo, viewable until results are released |
| Video | not required | **Required** — 3–5 minutes, your own spoken narration (no AI voice, not sped up), showing the working project |

Two requirements are new and non-negotiable, and neither exists yet in this project. They are Section 1 below because missing either one is a severe, avoidable mark penalty regardless of how good the report text is.

---

## 1. Critical blockers (do these first, they are currently at zero)

### 1.1 There is no git repository at all
`git status` in the project root returns `fatal: not a git repository`. Nothing has been committed, anywhere, at any point. Before anything else:

1. `git init` in `nexttrack/`.
2. Write a real `.gitignore` (exclude `backend/venv/`, `frontend/node_modules/`, `frontend/.env.local`, `**/__pycache__/`, `.pytest_cache/`).
3. Commit the existing work with a sensible history — even a handful of logically-grouped commits (backend engine, backend API, frontend, tests) reads far better to a marker than one giant initial commit, and costs almost nothing extra now versus enormous pain if left until the week before submission.
4. Push to a **public** GitHub (or equivalent) repository. Double-check the visibility setting — a private repo you forgot to flip to public is the single easiest way to lose marks on a requirement you actually did the work for.
5. Put the repo URL in the report's title page or introduction as instructed, and keep the repo public/viewable until results are released — don't delete or re-privatise it right after submitting.

### 1.2 There is no demo video
Needs to be produced from scratch: 3–5 minutes, your own spoken audio (explicitly: **no AI-generated voice, no sped-up footage**), showing the project actually working end to end, with enough spoken explanation that a viewer understands *how* it works, not just that it runs. See §6 for a suggested structure and what to demonstrate.

---

## 2. Objective-by-objective: what's left

This reuses the status already established in the draft report's Evaluation chapter, expanded into concrete tasks.

### Objective 1 — Literature Review: mostly done, one real task left
The literature review itself is written and revised. What's *not* done: incorporating actual feedback from your supervisor/module team on the preliminary and draft submissions. **Action:** locate whatever feedback you were given on both prior submissions (module feedback portal, supervisor email/notes) and explicitly work it into the Chapter 2 revision for the final report — the brief asks for this directly ("incorporating the feedback you have obtained from your submissions"), and a marker who gave feedback will notice if it was ignored.

### Objective 2 — Critical Evaluation: done
Folded into the literature review; no separate action beyond keeping it sharp in the revision pass.

### Objective 3 — RESTful API: done
Five endpoints, live, documented via OpenAPI/Swagger. No further work required for this objective specifically, though see §3 for polish items.

### Objective 4 — Recommendation Engine: **the largest open item**
Only the content-based stage exists. The original plan was a three-stage cascade hybrid (content-based → aggregate collaborative re-ranking via Last.fm → MMR diversity re-ranking). Concrete options, in order of recommended priority:

1. **Add a diversity re-ranking stage (Maximal Marginal Relevance).** This is the highest-value single addition: the draft report's own evaluation already found, empirically, that the current engine over-favours the closest genre match (a known content-based-filtering weakness — Lops et al., 2011). MMR directly fixes an already-documented, already-cited problem, needs no new external API, and is a self-contained addition to `backend/app/engine/` (a new module, e.g. `diversity.py`, taking the scored candidate list and re-ranking by `λ·relevance − (1−λ)·max_similarity_to_already_selected`). This is implementable and testable in isolation without touching the rest of the pipeline.
2. **Add the Last.fm aggregate collaborative signal, or explicitly and justifiably drop it.** This is a bigger integration (new API client, new candidate-scoring stage, API key management, rate limiting) for a less certain evaluation payoff in the remaining time. If you do it: mirror the existing `data/musicbrainz.py` / `data/acousticbrainz.py` pattern (async wrapper, caching, graceful degradation on failure) for consistency. If you don't: say so explicitly and honestly in the Design chapter, with the reasoning (time constraint vs. a lower-priority literature-supported gain), rather than silently dropping it — the review criteria explicitly reward justified decisions, not just delivered features.
3. **Run the ablation study** the design chapter already promises, once there is more than one stage to ablate: content-based only, content-based + MMR, (content-based + Last.fm if built), and the full pipeline. This becomes possible only after step 1 (and optionally 2) exist, and directly produces evidence for the Evaluation chapter.

### Objective 5 — Web Front-End: done, with two known issues to fix
1. **Demo-mode bug** (found while producing the draft report's screenshots): mock search/Top-5 results carry a `track_id` like `mock-0001-teen-spirit`, which fails the frontend's `isMbid()` check, so playing a track from search/Top-5 in demo mode never actually reaches `nextMockRecommendation` — the recommendation card silently shows "we couldn't identify that track" instead. Fix: give mock track ids a valid MBID-shaped string (e.g. reuse the real seed MBIDs already in `backend/app/seeds.py`), or resolve them through a mock-aware path. Small fix, but currently makes the demo mode you'll likely use in your video look broken if you don't know to route around it.
2. **No automated frontend tests.** The backend has 36 tests; the frontend has none. At minimum, add component/hook tests for `useRecommendation` (request-id race protection) and `useLocalStorageState` (schema-guard fallback behaviour) using Vitest + React Testing Library, since these are the two pieces of frontend logic with real, testable correctness properties, not just rendering.

### Objective 6 — Offline Evaluation: not started, needed for the final Evaluation chapter
The plan already exists (draft report §3.6): Precision@K, nDCG@K, diversity, novelty, catalogue coverage, against random and popularity baselines, using held-out listening sequences. Concrete steps:
1. Build a small held-out dataset. The existing seed pool (`backend/app/seeds.py` and the "Today's Top 5" pool in `backend/app/daily.py`) is a ready-made starting point — expand it to ~50–100 short listening sequences (5–10 tracks each, last track held out as ground truth). This does not require new external data access, only curation time.
2. Write an evaluation script (e.g. `backend/scripts/offline_eval.py`, not part of the API) that runs `recommender.recommend()` (or the pipeline once MMR/collaborative stages exist) against each sequence and computes the five metrics against the held-out track, a random baseline, and a popularity baseline.
3. Run it, record numbers, and — critically — write the actual results and their interpretation into the Evaluation chapter. A results table plus 2–3 paragraphs of honest interpretation (where the engine beats baselines, where it doesn't, why) is worth far more to the review criteria than the number of metrics computed.

### Objective 7 — User Study: not started, longest lead time — start recruiting now
The plan (draft report §3.6): 12+ participants, popularity baseline vs. NextTrack in counterbalanced order, System Usability Scale (Brooke, 1996), acceptance rate, interview feedback, thematic analysis (Braun & Clarke, 2006), Wilcoxon signed-rank test (Wilcoxon, 1945) at p<0.05. This has the longest lead time of everything on this list (recruitment, scheduling, running sessions, transcribing/coding, analysing) and should start in parallel with, not after, Objective 4/6 work — see the timeline in §7. Concrete steps:
1. Draft a short study protocol and consent text (what participants do, what data you keep, how long it takes — roughly 20–30 minutes per participant for three 10-track sessions per condition).
2. Recruit 12+ participants (course peers, friends, online communities — the draft report already scopes "general listener" as the target group, which is easy to recruit).
3. Run sessions using the live app (demo mode is not suitable here — real recommendations are the point).
4. Score SUS per participant, compute acceptance rate (recommendations accepted / offered), run the Wilcoxon test comparing NextTrack vs. the popularity baseline, and thematically code interview notes.
5. Report results with tables/figures in the Evaluation chapter, and use them to critically discuss whether the stateless approach actually delivers acceptable recommendations to real users — this is the piece of evidence the whole project has been missing.

### Objective 8 — Final Report: everything above feeds into this
Once Objectives 4, 6, and 7 have real results, the final report chapters need a substantive rewrite (not just word-count padding) versus the draft:
- **Literature Review:** incorporate feedback (§2.1 above).
- **Design:** revise for whatever engine changes were actually made (MMR, Last.fm or its justified omission).
- **Implementation (now ≤2500 words, "greatly expanded to cover the entire implementation"):** the draft chapter covered the content-based engine, the two defects fixed, graceful degradation, and the frontend; expand it to also cover whichever of MMR/Last.fm/offline-eval-harness/frontend-tests were built, with the same level of algorithmic and code-level detail the draft chapter used for the existing engine.
- **Evaluation (now must report *actual* results, not a plan):** this is the chapter that changes most. Replace "this has not been run yet" throughout with real numbers, tables, and figures from Objectives 6 and 7, and use them — as the review criteria explicitly ask — to critically analyse the project against its original aims, not just report metrics in isolation.
- **Conclusion:** revise to answer the project's original research question ("does a stateless recommender need a permanent profile to be useful?") using the *evidence now available*, rather than the draft's "early but positive" holding position.

---

## 3. What can be improved (beyond the objectives)

Items that would raise implementation quality and "technical challenge" marks even though no objective strictly requires them:

- **Redis-backed caching**, already flagged in the code itself (`backend/app/data/cache.py`: *"Redis-backed caching is deferred to Phase 2"*). The current in-memory cache resets on every server restart and doesn't scale past one process. Even a minimal Redis swap-in (same interface, different backing store) is a legitimate "Phase 2" deliverable that demonstrates production-readiness thinking, and is a natural thing to mention as future work either way.
- **MusicBrainz rate-limit resilience.** The 1 req/sec limit is a known, cited limitation (draft report §5.4). A candidate-pool cache keyed by genre (also already suggested in your own prototype-stage self-critique) would cut repeated round trips and measurably speed up cold-cache recommendations — worth doing if Objective 6's offline evaluation shows latency mattering.
- **Search ranking quality.** Preferring canonical/official releases over covers, mashups, and remixes in candidate retrieval (also flagged in your own prototype notes) would likely improve both offline metrics and user-study acceptance rate, so it's worth doing before Objective 6/7 rather than after, if time allows — it directly affects the numbers those evaluations will produce.
- **Health/observability polish.** `/health` already reports per-source reachability; consider surfacing this in the frontend (a small status indicator) as a nice, low-effort way to make the video demo more impressive without new backend work.
- **API key / secrets hygiene.** Confirm no credentials are committed once the repo goes public (§1.1) — `ytmusicapi`/`musicbrainzngs` don't need keys, but double-check `.env` files are gitignored, not just present, before pushing.

---

## 4. Suggested timeline against the 28 Sep 2026 deadline

Roughly seven weeks from now. Objective 7 (user study) has by far the longest lead time and should not be left until last.

| Weeks | Focus |
|---|---|
| Week 1 (now) | §1 blockers: git init, commit history, push public repo. Fix the demo-mode bug (§Obj 5). Start user-study recruitment and protocol (§Obj 7) in parallel — this runs in the background from here on. |
| Weeks 2–3 | Build MMR diversity re-ranking (§Obj 4.1). Decide on Last.fm (build or justified drop). Build the offline-evaluation harness and held-out dataset (§Obj 6). |
| Week 4 | Run offline evaluation, record and interpret results. Run the ablation study. Begin running user-study sessions as participants become available. |
| Week 5 | Finish user-study sessions; analyse (SUS scoring, Wilcoxon test, thematic coding of interviews). Start rewriting the Implementation and Evaluation chapters with real content. |
| Week 6 | Finish report rewrite (all six chapters, word-budget pass). Record and edit the demo video. Add frontend tests if time remains. |
| Week 7 (buffer) | Proofread, verify citations and word counts per chapter, verify the repo is public and the video meets the length/audio constraints, submit early rather than at 20:59. |

---

## 5. Word-budget planning for the final report (10,500 total, up from 9,500)

The draft report used roughly 7,384 words across the six chapters, leaving real headroom under even the draft's 9,500 cap. For the final report, most of the extra 1,000-word allowance should go to:
- **Implementation** (cap now 2,500, was 2,000): describing whatever of MMR/Last.fm/offline-harness gets built, at the same code-level depth as the existing sections.
- **Evaluation** (still 2,500, but now needs real results instead of a plan): tables and result interpretation for Objectives 6 and 7 will need real space; the draft's evaluation prose (~1,478 words) has plenty of room to grow into this cap once there are actual numbers to report.
Leave Introduction, Literature Review, Design, and Conclusion close to their draft-report lengths unless supervisor feedback specifically asks for more there.

---

## 6. Suggested video structure (3–5 minutes)

1. **~20s** — what NextTrack is and the core question (stateless, no stored profile — can it still recommend well?).
2. **~90s** — live demo: search or Top 5 → play a track → show the recommendation card, its rationale, and the score, explaining briefly what's happening server-side (feature vectors, cosine similarity, no stored history).
3. **~60s** — one or two "how it works" beats worth narrating on screen: the two-ID resolution flow, or graceful degradation when AcousticBrainz has no data — pick whichever is most visually demonstrable.
4. **~60s** — evaluation results: a results table or chart from the offline evaluation and/or user study, with a sentence or two of honest interpretation.
5. **~30s** — close: what's still limited, what you'd do next, and why the project's core hypothesis does or doesn't hold up so far.

Keep it to real screen capture of the actual running app (not demo mode, if you can get live data reliably — otherwise demo mode is acceptable but say so on camera), your own voice throughout, and no artificial speed-up.
