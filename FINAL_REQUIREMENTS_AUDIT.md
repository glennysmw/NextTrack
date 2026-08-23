# NextTrack — Final Requirements Traceability Audit

**Project:** CM3070 Final Year Project — Template 7.2, Project Idea 2:
*NextTrack: A music recommendation API*
**Author:** Soe Ming Wei, Glenn (230657168) · **Supervisor:** Yeo Sze Wee

This matrix reconstructs what NextTrack was actually specified to contain, from the
project's own evidence, and traces each requirement to the code that implements it and
the test or measurement that demonstrates it. Its purpose is to stop functionality
disappearing silently between the proposal, the design, and the final implementation —
and to stop the report claiming anything the code does not do.

## Sources of requirements

| Tag | Document |
|---|---|
| **PROP** | `NextTrack_Proposal_Revised.pdf` — original project proposal |
| **PRELIM** | `FYP_Prelim_Report_FINAL.pdf` — preliminary report (design, objectives) |
| **DRAFT** | `NextTrack_CM3070_Draft_Report.pdf` — draft report (§1.4 objectives, §3 design, §5 evaluation) |
| **BRIEF** | `FinalReportInstructions.md` — assessed final-submission requirements |
| **GAP** | `docs/REMAINING_WORK.md` — the project's own pre-existing gap analysis |
| **README** | `README.md` — claims made to a user of the repository |

## Status vocabulary

| Status | Meaning |
|---|---|
| **VERIFIED** | Was already implemented; independently re-tested this pass |
| **IMPLEMENTED AND VERIFIED** | Was missing or incomplete; built and tested this pass |
| **FIXED AND VERIFIED** | Was present but defective; repaired and covered by a regression test |
| **PARTIAL** | Delivered in substance, with a documented shortfall |
| **NOT APPLICABLE** | Deliberately and explicitly dropped, with the reasoning recorded |
| **BLOCKED** | Cannot be completed locally; requires the author |

---

## A. Project objectives (DRAFT §1.4)

| ID | Requirement | Source | Expected behaviour | Implementation | Test / evidence | Status | Notes |
|---|---|---|---|---|---|---|---|
| O1 | Literature review | DRAFT §1.4 | Review recommender systems, MIR, REST, privacy-by-design, evaluation | `FinalReport.md` ch. 2 | 28 references, all traceable to the draft's bibliography | VERIFIED | Revised, not rewritten; new material added for the collaborative and MMR stages |
| O2 | Critical evaluation of prior work | DRAFT §1.4 | Assess Spotify, Last.fm, Whitman & Lawrence, hybrid work; relate to NextTrack | `FinalReport.md` ch. 2 | — | VERIFIED | Now argues from measured results rather than expectation |
| O3 | RESTful API | DRAFT §1.4 | FastAPI backend documented via OpenAPI | `backend/app/api/routes.py`, `main.py` | `tests/test_api.py`; `docs/final-evidence/api_examples.json` (13 live transcripts) | VERIFIED | Five endpoints live; error contract exercised as well as the happy path |
| O4 | Hybrid recommendation engine | DRAFT §1.4, PRELIM | Cascade hybrid: content-based → aggregate collaborative → diversity re-ranking | `engine/similarity.py`, `engine/collaborative.py`, `engine/diversity.py`, `engine/recommender.py` | `tests/test_collaborative.py`, `test_diversity.py`, `test_pipeline.py`; ablation in `docs/final-evidence/offline_eval_results.json` | IMPLEMENTED AND VERIFIED | Was content-only. All three stages now exist and are independently ablatable |
| O5 | Web front-end | DRAFT §1.4 | React SPA: search, playback, history, recommendation display, preferences, local session storage | `frontend/src/` | 29 Vitest tests; `docs/final-evidence/screenshot_*.png` | VERIFIED | Two defects fixed (demo mode, unhandled resolve rejection); test coverage added |
| O6 | Offline evaluation | DRAFT §1.4, §3.6 | Ranking-quality metrics against baselines, plus an ablation study | `backend/scripts/offline_eval.py` + dataset scripts | `docs/final-evidence/offline_eval_*.csv`, `fig_*.png` | IMPLEMENTED AND VERIFIED | Was not started |
| O7 | User study (12+ participants) | DRAFT §1.4, §3.6 | SUS, acceptance rate, Wilcoxon test, thematic analysis | — | — | **BLOCKED** | Requires human participants. **No study has been run and none is claimed.** See §E |
| O8 | Final report | DRAFT §1.4, BRIEF | Six chapters, ≤10,500 words, repository link | `FinalReport.md` | Word counts in `FINAL_SUBMISSION_READINESS.md` | IMPLEMENTED AND VERIFIED | Describes the system as it now exists |

---

## B. Functional requirements — API (DRAFT §3.3, Appendix A; README)

| ID | Requirement | Source | Expected behaviour | Implementation | Test / evidence | Status |
|---|---|---|---|---|---|---|
| F1 | `POST /api/v1/search` | DRAFT App. A | Search YouTube Music for playable official songs | `routes.py:search`, `data/youtube.py` | `test_api.py::test_search_returns_results`, `…carry_album_art`; live capture `search` (200, 0.6 s) | VERIFIED |
| F2 | `GET /api/v1/top` | DRAFT §4.6 | Daily-rotating Top 5, stable within a UTC day, no server-side storage | `routes.py:top`, `app/daily.py` | `test_api.py::test_top_returns_five_tracks_with_art`; live capture `top` | VERIFIED |
| F3 | `POST /api/v1/resolve` | DRAFT §3.3.1 | Map played title+artist → MusicBrainz id via a fielded query | `routes.py:resolve`, `musicbrainz._build_search_query` | `test_api.py::test_resolve_maps_title_artist_to_mbid`; live capture `resolve` | VERIFIED |
| F4 | `POST /api/v1/recommend` | DRAFT §4.1 | Next track + score + rationale from a self-contained history | `engine/recommender.py:recommend` | `test_api.py`, `test_pipeline.py`; live captures (3 variants) | VERIFIED |
| F5 | `GET /api/v1/health` | DRAFT §4.6 | Version, cache stats, per-source reachability | `routes.py:health` | `test_api.py::test_health_returns_ok`; live capture shows all 4 sources | VERIFIED |
| F6 | Machine-readable failure reasons | DRAFT §4.5 | Five distinct `reason` codes alongside a human `detail` | `recommender.RecommendationError`, `main.recommendation_error_handler` | `test_recommend_errors.py` (6 tests); live captures of 4 error cases | VERIFIED |
| F7 | Request validation rejects unknown fields | DRAFT §3.4 | Pydantic `extra="forbid"` | `models/request.py` | Live capture `error_unknown_parameter_rejected` → 422 | VERIFIED |
| F8 | History bounds enforced (1–20) | DRAFT §4.5 | 400 on empty or oversized history | `routes.py:recommend` | `test_api.py::test_recommend_empty_history…`, `…too_many_tracks…` | VERIFIED |
| F9 | MBID syntax validation | DRAFT §4.5 | 400 on a malformed identifier | `models/request.py:is_valid_mbid` | `test_api.py::test_recommend_invalid_mbid_returns_400` | VERIFIED |
| F10 | Exclusion filters (artist / track) | DRAFT §4.1 | Named artists and tracks removed from candidates | `recommender.recommend_ranked` | `test_api.py::test_recommend_exclude_tracks_param_works` | VERIFIED |
| F11 | Tempo-range constraint | DRAFT §4.1 | Hard filter on candidate tempo | `recommender.recommend_ranked` | `test_recommend_errors.py::test_no_candidates_after_filters` | VERIFIED |
| F12 | OpenAPI/Swagger documentation | O3, DRAFT §3.3 | Interactive docs at `/docs` | FastAPI, `main.py` | `docs/final-evidence/screenshot_swagger.png` | VERIFIED |

---

## C. Functional requirements — recommendation engine

| ID | Requirement | Source | Expected behaviour | Implementation | Test / evidence | Status |
|---|---|---|---|---|---|---|
| E1 | Feature-vector construction | DRAFT §4.1 | 16 fixed acoustic dims + request-scoped genre TF-IDF | `engine/features.py` | `tests/test_features.py` | VERIFIED |
| E2 | Enharmonic key normalisation | DRAFT §4.1 | Flats map to sharp equivalents | `features.canonical_key` | `tests/test_features.py` | VERIFIED |
| E3 | Session centroid + cosine ranking | DRAFT §4.1 | Mean history vector; cosine clamped to [0,1]; 0 for a zero vector | `engine/similarity.py` | `tests/test_similarity.py` | VERIFIED |
| E4 | **Aggregate collaborative re-ranking** | PRELIM, DRAFT §3.2 | Blend population-level co-listening evidence into relevance | `data/listenbrainz.py`, `engine/collaborative.py` | `test_collaborative.py` (8), `test_listenbrainz.py` (15), `test_pipeline.py::test_collaborative_stage_boosts_a_co_listened_artist` | IMPLEMENTED AND VERIFIED |
| E5 | **MMR diversity re-ranking** | PRELIM, DRAFT §5.3, GAP §2 | `λ·rel − (1−λ)·max sim` against already-heard tracks | `engine/diversity.py` | `test_diversity.py` (9), `test_pipeline.py::test_diversity_stage_demotes_redundant_candidates` | IMPLEMENTED AND VERIFIED |
| E6 | **Ablatable pipeline** | DRAFT §3.6 | Each stage independently switchable for the ablation study | `recommender.PipelineConfig` | `test_pipeline.py` (10); ablation results | IMPLEMENTED AND VERIFIED |
| E7 | Plain-language rationale | DRAFT §4.1 | One sentence naming the signals that actually matched | `engine/rationale.py` | `tests/test_rationale.py` (7) | FIXED AND VERIFIED — key signal was unreachable (log D1) |
| E7b | Perceived-energy feature | DRAFT §4.1 | An energy dimension that reflects energy | `acousticbrainz._energy` | `test_acousticbrainz.py` (7 energy tests) | FIXED AND VERIFIED — proxied by danceability, which scored a loud rock track at 0.02 (log D2b) |
| E8 | Graceful acoustic degradation | DRAFT §4.3 | Missing AcousticBrainz data → defaults + `limited_acoustic_data` flag | `recommender._resolve_track_features` | `test_pipeline.py`; live captures show the flag and the rationale note | VERIFIED |
| E9 | Graceful collaborative degradation | New (E4 implies) | Any ListenBrainz failure → content-only scoring, never a 5xx | `listenbrainz.get_similar_artists` | `test_listenbrainz.py` (6 parametrised failure modes), `test_pipeline.py::test_listenbrainz_outage_does_not_break_recommendations` | IMPLEMENTED AND VERIFIED |
| E10 | Artist-tag genre enrichment | DRAFT §4.2 | Recording tags are usually empty; merge the artist's ranked tags | `musicbrainz._get_recording_sync` | `tests/test_musicbrainz.py` | VERIFIED |
| E11 | Non-genre tag filtering | DRAFT §4.2 | Drop place, decade and housekeeping tags | `musicbrainz._looks_like_genre` | `tests/test_musicbrainz.py` | VERIFIED |
| E12 | Deterministic genre tie-breaking | DRAFT §4.1 | Identical histories select identical search genres | `recommender._top_genres` | `tests/test_musicbrainz.py`, `test_pipeline.py::test_identical_requests_produce_identical_rankings` | VERIFIED |
| E13 | Playback fall-through on YouTube misses | DRAFT §4.1 | Try the next candidate rather than failing | `recommender.recommend` | `test_recommend_errors.py::test_no_youtube_match` | VERIFIED |
| E14 | Verified cold-start seed pool | DRAFT §5.6 | Seed MBIDs resolve to the tracks they claim | `app/seeds.py`, `scripts/verify_seeds.py` | `verify_seeds.py --check` | FIXED AND VERIFIED — 10 of 12 were wrong (log D3) |

---

## D. Non-functional requirements

| ID | Requirement | Source | Expected behaviour | Implementation | Test / evidence | Status |
|---|---|---|---|---|---|---|
| N1 | **Statelessness** — no user data retained between requests | PROP, PRELIM, DRAFT §1.1 | Server holds no account, profile or history; caches hold only public per-track facts | No database anywhere; `data/cache.py` keyed by MBID/genre | Code audit (§F below); `/health` exposes the entire retained state | VERIFIED |
| N2 | **Reproducibility** — identical requests give identical answers | DRAFT §4.1 | Same input ⇒ same output | `cache.get_candidates`, deterministic sorts, `diversity.mmr_rank` tie-break | `test_candidate_cache.py` (10); live: 3 identical requests → identical track and score | FIXED AND VERIFIED — did not hold (log D1b) |
| N3 | Request-scoped genre vocabulary isolation | DRAFT §4.2 | Concurrent requests cannot pollute each other's feature space | await-free block in `recommender._rank` | `tests/test_recommend_concurrency.py` | VERIFIED |
| N4 | Non-blocking async I/O | DRAFT §3.4 | Synchronous third-party clients offloaded to worker threads | `asyncio.to_thread` in `musicbrainz.py`, `youtube.py` | `test_recommend_concurrency.py::test_concurrent_recommends_are_independent` | VERIFIED |
| N5 | No API keys required to run | README | Clone and run with no credentials | ListenBrainz + `ytmusicapi` both keyless | `.env.example` lists only optional overrides; app starts with no `.env` | VERIFIED |
| N6 | Acceptable latency | Implied by O5/O7 | Interactive on a warm cache | Candidate-pool cache, per-MBID feature cache | `docs/final-evidence/latency_benchmark.json` | VERIFIED — see report ch. 5 |
| N7 | Hermetic test suite | README, DRAFT §4.5 | No real network calls in tests | `conftest._no_network` (socket + httpx layers) | `tests/test_network_guard.py` (5 tests) | FIXED AND VERIFIED — was unenforced, and the first fix missed async httpx (log D4) |
| N8 | Static quality gates | New | Lint, type check, build all clean | `ruff`, `mypy`, `tsc` | `ruff check .` clean; `mypy app` clean (23 files); `tsc --noEmit` clean; `vite build` succeeds | IMPLEMENTED AND VERIFIED |
| N9 | Reproducible dependency tree | BRIEF (repo must be runnable) | Clean install resolves | `frontend/package.json` | `npm ls vite` valid; `npm audit` reports 0 vulnerabilities | FIXED AND VERIFIED (log D5) |
| N9b | Malformed input never returns 5xx | New (F6 implies) | A client error is a client error | `models/request.py`, `api/routes.py` | `scripts/adversarial_sweep.py` — 32/32; `docs/final-evidence/adversarial_sweep.txt` | FIXED AND VERIFIED — a padded MBID returned 503 (log D5c) |
| N9c | Accessibility baseline | BRIEF (usable interface) | Labelled controls, coherent headings, visible focus, reduced-motion support | `frontend/src/index.css`, components | DOM audit of the running app — 0 problems found | VERIFIED — baseline only; no assistive-technology testing performed |
| N10 | No committed secrets | GAP §3 | No keys, tokens or credentials in the tree | `.gitignore`; `.env` holds only a comment | Tree scanned for key/token/secret patterns — none found | VERIFIED |

---

## E. Requirements deliberately not delivered, with reasoning

| ID | Requirement | Source | Decision | Reasoning |
|---|---|---|---|---|
| X1 | **User study with 12+ participants** | DRAFT §3.6, O7 | **BLOCKED — not performed, not claimed** | Requires recruiting and running sessions with human participants. It cannot be simulated, and inventing participants, SUS scores or a Wilcoxon result would be fabrication. The report states plainly that no user study was conducted, explains what that costs the evaluation (acceptance and perceived quality remain unmeasured), and keeps the protocol as future work. The offline evaluation is expanded to carry as much of the evidential load as it legitimately can. |
| X2 | **Last.fm as the collaborative source** | PRELIM, DRAFT §2.3 | **NOT APPLICABLE — substituted, not dropped** | The *requirement* was an aggregate collaborative signal; the *named vendor* was Last.fm. ListenBrainz delivers the same requirement without an API key, keyed natively on the MusicBrainz identifiers the pipeline already carries, whereas Last.fm is keyed on artist/track name strings and would have needed a second lossy matching layer. The capability is delivered; the vendor changed, and the reasoning is recorded in `data/listenbrainz.py` and the Design chapter. |
| X3 | **Redis-backed caching** | `data/cache.py`, GAP §3 | **NOT APPLICABLE — explicitly Phase 2** | Marked as deferred in the code before this pass and never part of an assessed objective. The in-memory cache was extended instead (genre pools), which delivered the latency and determinism benefits Redis was wanted for, within one process. Remains honest future work. |
| X4 | **Track-level ListenBrainz similarity** | — | Rejected on evidence | Tried first; returned empty results for most seeds in this catalogue. Artist-level similarity resolves for essentially any charting artist and captures the same cross-genre audience overlap. Recorded in `data/listenbrainz.py`. |
| X5 | **Neural session models (GRU4Rec/SASRec/BERT4Rec)** | DRAFT §2.6 | Out of scope, as originally reasoned | The draft already argued against these on replicability grounds (Petrov & Macdonald, 2022) and project scale. Nothing changed that assessment; no objective required them. |

---

## F. Privacy claim audit

NextTrack's central claim is that the server stores nothing about a user between
requests. Because the report makes that claim, it was audited against the code rather
than assumed.

| Check | Finding |
|---|---|
| Any database, ORM, or persistent store? | None. No database dependency in `requirements.txt`; no schema, migration, or connection anywhere in `backend/`. |
| What survives a request? | Exactly three module-level dicts in `data/cache.py` (track features by MBID, video ids by MBID, candidate pools by genre tag), one in `musicbrainz.py` (artist tags by artist MBID), one in `listenbrainz.py` (similar artists by artist MBID), and `routes._top_cache` (today's five picks). Every one is keyed on a public identifier and holds a fact identical for every caller. None is keyed on, or derived from, a user, session, or request identity. |
| Is the retained state observable? | Yes — `GET /health` reports the size of each cache. The full extent of server-side retention is inspectable by any client. |
| Is the listening history persisted? | No. It arrives in the request body, is used within the call, and is not written anywhere. Client-side, it lives in `localStorage` and the Reset button clears all four keys. |
| Is any identifier assigned to a caller? | No cookies, no sessions, no auth, no client identifier of any kind. |
| Does the collaborative stage leak anything? | No. Only an artist MBID is sent to ListenBrainz; no user, session, or history data crosses that boundary. |
| Is feedback sent to the server? | No. Thumbs up/down is stored in `localStorage` only (`types.ts`: "never sent to the server"), capped at 200 events. |
| Logging | Warnings and errors log MBIDs and genre tags, never a full history payload. |

**Verdict:** the privacy claim is supported by the implementation. One nuance the
report states explicitly rather than glossing: the caches are *shared across callers*,
so a track another user caused to be fetched can serve a later request faster. That is
a public-data cache, not a user profile, but it is a real property and is described
honestly.

**Evaluation-data privacy.** The offline evaluation uses public ListenBrainz listening
histories. Since the project's own argument is about not accumulating listener
profiles, usernames are stored only as a salted SHA-256 prefix and no timestamps are
retained beyond the session segmentation. The committed corpus contains track
identifiers and session boundaries, not identifiable listening histories.

---

## G. Documentation-versus-reality corrections

Claims found in prior documents that this pass had to correct.

| Claim | Where | Reality | Action |
|---|---|---|---|
| "All external APIs are mocked — no real network calls are made" | README, DRAFT §4.5 | True by convention only; the ListenBrainz health probe made a live call | Enforced with a socket guard (D4); the claim is now accurate |
| "identical histories always produce the same candidate search" | DRAFT §4.1 | True of genre *selection*, false end-to-end — upstream search is unstable | Fixed (D1b); the report now states the property and its residual limit |
| "every response states, in one readable sentence, why that track and not another" | DRAFT §4.1 | True, but one of the four signals could never fire, and a second could fire wrongly | Fixed (D1, D2b); the claim now holds for all signals |
| Feature vectors include "energy" | PRELIM, DRAFT §4.1 | The dimension carried a danceability probability, near-orthogonal to energy | Fixed (D2b); the dimension now reflects what it is named |
| "36 automated tests" | DRAFT §4.5 | 37 at the start of this pass | Superseded: 118 backend + 29 frontend |
| Burke (2002) cited as *Knowledge and Information Systems*, 1(4), 331–370 | PRELIM, DRAFT refs | Published in *User Modeling and User-Adapted Interaction*, 12(4), 331–370 (DOI 10.1023/A:1021240730564). The page range was right; the journal and volume were not | Reference corrected |
| Brooke (1996) titled "SUS: A quick and practical usability scale" | DRAFT refs | The chapter is titled "SUS: A quick and dirty usability scale" | Reference corrected |
| Kaminskas & Bridge (2016) cited as 7(1), 1–42 | DRAFT refs | ACM TiiS 7(1), Article 2 | Reference corrected to article-number form |
| Whitman & Lawrence (2002) cited as "Automatically retrieving soft information for music", ISMIR 2002, pp. 197–198 | PRELIM, DRAFT §2.4 | **No such paper exists in the ISMIR 2002 proceedings.** The 78% result comes from *Inferring Descriptions and Similarity for Music from Community Metadata*, ICMC 2002, pp. 591–598, verified against the paper itself | Reference corrected; the claim it supports also tightened — the figure is *artist*-similarity accuracy from single-word web-text term profiles, not "agreement with human similarity judgements" |
| "the content-based stage is built … the collaborative and diversity stages remain future work" | DRAFT §1.4, §5.2 | Accurate at the time | Superseded: both stages now exist (E4, E5) |
| Seed pool proposed as the basis for held-out evaluation sequences | DRAFT §5.6, GAP §2 | The pool's identifiers were mostly invalid, and the approach was circular | Seeds fixed (D3); evaluation rebuilt on real listening sessions (I4) |
| "roughly 216 dimensions" feature vectors | PRELIM | Already corrected in DRAFT §3.4 | No further action; the correction stands |

## G2. Citation verification

Every reference the report leans on materially was checked against the published record
rather than carried forward on trust. Five were verified as correct exactly as cited
(Deldjoo et al. 2024, Article 100618; Petrov & Macdonald 2022, pp. 436–447; Afchar et al.
2022, AI Magazine 43(2) 190–208; Kaminskas & Bridge 2016, ACM TiiS 7(1); Burke 2002,
pp. 331–370). Four required correction, recorded in §G above — one of them a paper that
**does not exist as cited**, and which is the single most load-bearing source in the
project. The 78% figure attributed to it was also re-read in the original and tightened:
it is artist-similarity accuracy from single-word web-text term profiles, not "agreement
with human similarity judgements".

No reference in the final report is cited without a verified venue, and every in-text
citation appears in the reference list.

## H. Functionality present but previously undocumented

Recorded so the report describes the system that exists.

- Genre candidate-pool caching, and the reproducibility property it exists to protect.
- ListenBrainz as a fourth upstream source, surfaced on `/health`.
- The evaluation harness, held-out dataset, and figure pipeline as first-class,
  reproducible parts of the repository.
- A `verify_seeds.py` maintenance script.
- Enforced test hermeticity.
