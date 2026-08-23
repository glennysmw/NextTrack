# NextTrack — Final Submission Readiness

Verification record for the CM3070 final submission. Every figure here was produced by
running the command shown, on the code as it stands.

*Placeholders marked `[PENDING]` are filled by the final verification pass; see the end
of this document for the completion timestamp.*

---

## 1. Environment

| | |
|---|---|
| Operating system | Microsoft Windows 11 Home, build 10.0.26200 |
| Python | 3.12.10 |
| Node.js | 24.15.0 |
| npm | 11.12.1 |
| Backend virtualenv | `backend/venv` |

### Key dependency versions

| Package | Version | Role |
|---|---|---|
| fastapi | 0.138.0 | API framework |
| uvicorn | 0.49.0 | ASGI server |
| pydantic | 2.13.4 | request/response validation |
| numpy | 2.4.6 | feature vectors |
| scikit-learn | 1.9.0 | cosine similarity |
| scipy | 1.18.0 | Wilcoxon signed-rank test (evaluation only) |
| httpx | 0.28.1 | async HTTP (AcousticBrainz, ListenBrainz) |
| musicbrainzngs | 0.7.1 | MusicBrainz client |
| ytmusicapi | 1.12.1 | playback resolution |
| pytest / pytest-asyncio / pytest-mock | 9.1.1 / 1.4.0 / 3.15.1 | test suite |
| ruff | 0.16.4 | linting |
| mypy | 2.3.1 | type checking |
| matplotlib | 3.11.1 | figure generation (evaluation only) |
| react / react-dom | 18.3.1 | frontend |
| vite | 8.0.16 | build tooling |
| @vitejs/plugin-react | 5.2.0 | React plugin (bumped from 4.7.0 — see §9) |
| typescript | 5.6.x | type checking |
| vitest | 4.1.11 | frontend tests |

### Setup

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt                    # or requirements-dev.txt for tooling

# Frontend
cd frontend
npm install
cp .env.example .env
```

**No credentials are required.** All four upstream services (MusicBrainz,
AcousticBrainz, ListenBrainz, YouTube Music) are open. The application starts with no
`.env` file present.

---

## 2. Build

| Command | Result |
|---|---|
| `cd frontend && npm run build` (`tsc && vite build`) | **PASS** — 1642 modules, `dist/` produced |
| `cd frontend && npm run typecheck` (`tsc --noEmit`) | **PASS** — no errors |
| `cd backend && uvicorn app.main:app` | **PASS** — starts, serves, four sources probed on `/health` |

The backend is not a compiled artefact; "build" is a clean import and startup, verified
by the application serving live traffic throughout the verification described in §5.

---

## 3. Tests

| Suite | Command | Passed | Failed | Skipped |
|---|---|---:|---:|---:|
| Backend | `cd backend && pytest -q` | **121** | 0 | 0 |
| Frontend | `cd frontend && npm test` | **29** | 0 | 0 |
| **Total** | | **150** | **0** | **0** |

**No tests are skipped, and none are marked xfail.** The suite grew from 37 backend
tests and 0 frontend tests at the draft stage.

Backend coverage by file:

| File | Focus |
|---|---|
| `test_api.py` | the five endpoints, happy paths and input validation |
| `test_recommend_errors.py` | all five machine-readable failure reason codes |
| `test_pipeline.py` | the cascade as a whole; stage ablation; outage tolerance; determinism |
| `test_collaborative.py` | stage-2 affinity normalisation and blending |
| `test_diversity.py` | stage-3 MMR, including the λ=1 ablation identity and tie determinism |
| `test_listenbrainz.py` | client parsing and six distinct failure modes |
| `test_acousticbrainz.py` | bulk fetching, batching, failure paths, energy derivation |
| `test_candidate_cache.py` | pool caching and the reproducibility property it protects |
| `test_network_guard.py` | the test suite's own hermeticity guard |
| `test_recommend_concurrency.py` | request-scoped genre vocabulary isolation |
| `test_features.py`, `test_similarity.py`, `test_rationale.py`, `test_musicbrainz.py` | unit-level engine and data behaviour |

**Hermeticity is enforced, not assumed.** An autouse fixture guards both the socket
layer and `httpx`; any test reaching an unmocked external host fails with an explicit
message. `test_network_guard.py` tests the guard itself.

---

## 4. Static checks

| Check | Command | Result |
|---|---|---|
| Python lint | `cd backend && ruff check .` | **PASS** — all checks passed |
| Python types | `cd backend && mypy app` | **PASS** — no issues in 23 source files |
| TypeScript types | `cd frontend && npm run typecheck` | **PASS** — no errors |
| Frontend audit | `cd frontend && npm audit` | **PASS** — 0 vulnerabilities |
| Dependency tree | `cd frontend && npm ls vite` | **PASS** — valid (was `invalid` before §9) |

Ruff runs with `E, F, W, I, B, UP, C4, SIM, ARG, RET, PTH` enabled. `mypy` earned its
place in this workflow by finding defect D1 in the engineering log.

---

## 5. Functional verification (live, against real upstream services)

| Workflow | Method | Status |
|---|---|---|
| Backend starts and serves | `uvicorn app.main:app` | **PASS** |
| `/health` reports all four sources | live capture | **PASS** |
| Search returns official tracks first | UI: searched "Mr. Brightside" | **PASS** — official Killers version ranked first, above covers and remixes |
| Today's Top 5 loads with album art | UI, live | **PASS** |
| Play → resolve → recommend (Top 5 entry) | UI, live | **PASS** — Daft Punk → Röyksopp with collaborative rationale |
| Play → resolve → recommend (search entry) | UI, live | **PASS** — The Killers → Muse, two rationale signals |
| Recommendation carries score, rationale, features | UI + live captures | **PASS** |
| "Next option" excludes the rejected track | UI | **PASS** |
| Radio mode auto-advance | code + hook tests | **PASS** |
| Session reset clears all local state | UI | **PASS** |
| Day/night theme persists | UI | **PASS** |
| Demo mode end to end | UI with `VITE_DEMO_MODE=true` | **PASS** — was broken before D2 |
| Mobile layout (390×844) | UI | **PASS** — no horizontal overflow |
| Swagger UI documents all five endpoints | `/docs` | **PASS** |
| Error contract (4 distinct failures) | live captures | **PASS** — correct status and `reason` for each |
| Unknown request field rejected | live capture | **PASS** — 422 |
| Determinism across identical requests | live, 8 paired requests | **PASS** — 8/8 identical |
| Adversarial input sweep | `python scripts/adversarial_sweep.py` | **PASS** — 32/32; no 5xx from any malformed input |
| Accessibility baseline | DOM audit in the running app | **PASS** — see below |

Evidence: `docs/final-evidence/api_examples.json` (13 live transcripts plus a
determinism check), `screenshot_home.png`, `screenshot_recommendation.png`,
`screenshot_demo_day.png`, `screenshot_mobile.png`, `screenshot_swagger.png`,
`adversarial_sweep.txt`.

**Accessibility baseline.** A DOM audit of the running application found no unlabelled
buttons, no unlabelled form controls and no images without `alt`; the heading hierarchy
is coherent (one `h1`, section `h2`s); `lang="en"` is set; keyboard focus is visible
(`:focus-visible` with a 2px outline and offset rather than a removed outline); and a
`prefers-reduced-motion` block is honoured. This is a baseline check, not a full WCAG
audit — no assistive-technology testing was performed, and none is claimed.

**Adversarial pass (verification pass 2).** A 32-case hostile-input sweep against the
live API covering wrong types, wrong arity, oversized payloads (100 KB strings),
injection-shaped identifiers, reversed and negative ranges, unicode and emoji, Lucene
metacharacters, boundary values at the history limit, unknown routes and wrong methods.
All 32 now behave acceptably. The sweep found one real defect (D5c) and is retained in
the repository as `backend/scripts/adversarial_sweep.py`.

---

## 6. Evaluation

[PENDING]

---

## 7. Requirements coverage

Full detail in `FINAL_REQUIREMENTS_AUDIT.md`. Summary:

| Status | Count | Requirements |
|---|---:|---|
| VERIFIED | 24 | pre-existing and independently re-tested |
| IMPLEMENTED AND VERIFIED | 8 | built this pass (collaborative stage, MMR stage, ablatable pipeline, offline evaluation, frontend tests, health extension, static gates, evaluation tooling) |
| FIXED AND VERIFIED | 7 | defective on arrival (rationale key signal, energy feature, seed MBIDs, demo mode, determinism, hermetic tests, dependency tree) |
| NOT APPLICABLE (justified) | 4 | Last.fm (substituted), Redis (deferred), track-level similarity (rejected on evidence), neural session models (out of scope) |
| **BLOCKED** | 1 | **user study — not performed and not claimed** |

---

## 8. Remaining known limitations

Stated here in full; each is also discussed in the report.

1. **No user study.** Objective 7 was not delivered. The evaluation measures whether
   the engine predicts a held-out next track, not whether a listener would enjoy its
   choices. This is the project's principal evidential gap.
2. **Determinism is bounded by the cache TTL.** Identical requests return identical
   results while a genre's candidate pool is cached (one hour). MusicBrainz's tag
   search is not stable between calls, so absolute determinism is not achievable
   against that upstream.
3. **Cold-start latency is poor.** The first request to a fresh process took 155 s in
   the benchmark, dominated by MusicBrainz's 1 req/sec limit. Warm requests take under
   half a second.
4. **Acoustic coverage is sparse**, particularly among retrieved candidates, because
   AcousticBrainz was largely decommissioned in 2022. The genre block consequently
   carries most of the ranking signal.
5. **Collaborative coverage is popularity-biased.** ListenBrainz artist similarity
   resolves for well-listened artists and returns nothing for the long tail.
6. **In-memory caches only.** All caches are per-process and lost on restart.
7. **Evaluation sample is modest and skewed** toward listeners active enough on
   ListenBrainz to be sampled.
8. **`ytmusicapi` is an unofficial client** for YouTube Music's internal API: no key,
   no quota, but undocumented and able to change without notice.

---

## 9. Repository status

| | |
|---|---|
| Version control | Git repository initialised at `nexttrack/` |
| Branch | `main` |
| Commit | [PENDING] |
| Uncommitted changes | [PENDING] |
| Remote | **none configured** |
| Tracked files | 104 (no `venv/`, no `node_modules/`, no `.env`) |

**Secrets check:** the tree was scanned for key/token/secret/password patterns across
Python, TypeScript, JSON and Markdown files — none found. `.env` contains only a comment
recording that a previously-stored YouTube key was removed, and is excluded by
`.gitignore` at both project and backend level. The committed `.env.example` files list
only optional, non-secret overrides.

> **ACTION REQUIRED: VERIFY PUBLIC REPOSITORY ACCESS**
>
> No Git remote is configured and no GitHub CLI credentials are available in this
> environment, so the repository could not be pushed or its visibility verified. The
> assignment requires a publicly viewable repository link, remaining viewable until
> results are released. Before submitting you must:
>
> 1. Create a repository on GitHub (or equivalent) and set it to **public**.
> 2. `git remote add origin <url> && git push -u origin main`.
> 3. Open the URL in a signed-out browser window to confirm it is genuinely public.
> 4. Paste the URL into the placeholder on the title page of `FinalReport.md`.

---

## 10. Final verdict

[PENDING]
