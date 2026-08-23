# NextTrack — Final Engineering Log

Every defect found and fixed, and every piece of missing functionality implemented,
during the final pre-submission engineering pass. Entries are ordered by severity
within their category, not chronologically.

Repository state at the start of this pass: 37 backend tests passing, 0 frontend
tests, no version control, content-based recommendation stage only.

---

## Part 1 — Defects found and fixed

### D1. The "compatible key" rationale signal could never fire

| | |
|---|---|
| **Severity** | High — a user-facing feature that silently did nothing |
| **Location** | `backend/app/engine/rationale.py:summarise_history` |
| **Found by** | `mypy` static type checking (not by any existing test) |

**Issue.** `summarise_history` builds a `Counter` keyed on `(pitch, mode)` tuples, then
unpacked the result of `most_common(1)[0]` as if it were that tuple:

```python
common_pitch, common_mode = key_counts.most_common(1)[0]
```

`Counter.most_common` yields `(item, count)` pairs, so `common_pitch` was bound to the
whole `('F#', 'minor')` tuple and `common_mode` to the integer count.

**Impact.** Two user-visible consequences. First, the key-match branch in
`generate_rationale` compares `candidate["key"] == summary["common_pitch"]` — a string
against a tuple — which is never true, so the "compatible key" explanation was
unreachable for every recommendation the system has ever produced. Second,
`common_key_display` rendered as `"('F#', 'minor') 2"` rather than `"F# minor"`.

**Root cause.** A tuple-unpacking mistake that Python accepts silently because both
sides have arity two. The existing rationale tests exercised the genre, tempo and
energy signals but never asserted a key-only match, so nothing caught it.

**Fix.** Take element `[0]` of the pair, and annotate the `Counter` so the type checker
can verify the shape:

```python
key_counts: Counter[tuple[str, str]] = Counter(...)
common_pitch, common_mode = key_counts.most_common(1)[0][0] if key_counts else ("C", "major")
```

**Verification.** Three regression tests in `tests/test_rationale.py`:
`test_summarise_history_extracts_pitch_and_mode_not_the_count`,
`test_summarise_history_picks_the_majority_key`, and
`test_compatible_key_signal_can_now_fire` — the last constructs a candidate that
matches on key *only* (tempo, energy and genre all deliberately outside their
thresholds) and asserts the phrase appears. All fail against the old code.

**Status.** Fixed and verified.

---

### D1b. Identical requests returned different recommendations

| | |
|---|---|
| **Severity** | High — contradicted the project's central design property |
| **Location** | `backend/app/engine/recommender.py`, `backend/app/data/cache.py` |
| **Found by** | A determinism assertion added to the live API-capture script |

**Issue.** `scripts/capture_api_examples.py` issues the same `/recommend` request twice
and asserts the responses match. They did not: `fac363f8-…` then `7b42df2c-…`.

**Impact.** This is not a cosmetic inconsistency. The draft report states that identical
histories "always produce the same candidate search — a small but necessary property
for a stateless API, since repeated requests with the same input should not silently
drift", and reproducibility is a large part of what statelessness is supposed to buy.
The property did not hold end to end.

**Root cause.** Not in NextTrack's code. Probing MusicBrainz directly showed that its
tag search is **not stable between calls**:

```
grunge            run1 == run2: False    |symmetric difference| = 100  (of 50 + 50)
alternative rock  run1 == run2: False    |symmetric difference| = 38
```

Two consecutive searches for `grunge` shared **zero** of their fifty results.
Thousands of recordings tie on relevance and the tie order is arbitrary, so the
candidate pool — and therefore the winner — changed between requests. The genre
*selection* was deterministic, as the draft claimed; the search results were not.

**Fix.** A per-genre candidate-pool cache (`cache.get_candidates` /
`set_candidates`, TTL 1 hour) plus a deterministic sort by MBID before the pool is
stored. Both parts are needed: the sort removes any dependence on upstream ordering,
and the cache holds the pool stable across requests. Like the existing caches this
stores only public per-tag facts and nothing about a user.

**Secondary benefit — a large latency win.** Three rate-limited MusicBrainz searches
were the dominant cost of every recommendation. Measured against the live API before
and after, on the same three requests:

| Request | Before | After |
|---|---|---|
| `recommend` (cold) | 42.3 s | 24.7 s |
| `recommend` (multi-track history) | 61.5 s | 0.53 s |
| `recommend` (with constraints) | 32.2 s | 0.79 s |

**Honest limitation.** Determinism now holds for the cache TTL, not absolutely. Once a
pool expires, an identical request can legitimately produce a different track, because
the upstream catalogue view has changed. This is a property of MusicBrainz, not
something NextTrack can fix, and it is reported as a limitation rather than papered
over.

**Verification.** `tests/test_candidate_cache.py` — 10 tests, including one that rigs
the mocked search to reverse its results on every call (standing in for the unstable
upstream) and asserts two identical recommendations still agree. Live: three identical
requests now return `fac363f8-… / "Agitated" / Muse / score 0.433` every time.

**Status.** Fixed and verified, with a documented residual limitation.

---

### D2. Demo mode was broken end to end

| | |
|---|---|
| **Severity** | High — the mode most likely to be used for the demonstration video |
| **Location** | `frontend/src/mockData.ts`, `frontend/src/api/nexttrack.ts` |
| **Found by** | Previously documented in `docs/REMAINING_WORK.md`; reproduced and fixed here |

**Issue.** Mock tracks carried placeholder identifiers (`mock-0001-teen-spirit`), and
the demo-mode stub for `POST /resolve` returned `` `mock:${artist}:${title}` ``. Both
fail the `isMbid()` guard in `useRecommendation`, which filters the history down to
MBID-shaped ids before calling the recommendation API.

**Impact.** In demo mode, playing anything from search or Today's Top 5 produced
"We couldn't identify that track well enough to recommend a next one" instead of a
recommendation. The recommendation card — the centrepiece of the product — never
appeared on the path a demo viewer would take.

**Root cause.** The mock data predates the two-ID resolution model. When search moved
to YouTube Music and `isMbid()` was introduced to distinguish a video id from a
MusicBrainz id, the mock fixtures were not revisited.

**Fix.** Mock tracks now carry **real MusicBrainz identifiers**, resolved from the live
MusicBrainz API for the six demo tracks, and `resolveTrack` delegates to a new
`resolveMockTrack(title, artist)` that mirrors the live endpoint's contract (returning
`null` for an unknown track). Demo mode now runs the identical frontend code path as
live mode; only the transport is stubbed.

**Verification.** `frontend/src/mockData.test.ts` asserts every mock identifier passes
`isMbid()`, that `resolveMockTrack` is case-insensitive and returns `null` for unknown
tracks, and that the deterministic cycling still holds.

**Status.** Fixed and verified.

---

### D2b. The "energy" feature measured almost the opposite of energy

| | |
|---|---|
| **Severity** | High — a ranking feature and a user-facing readout, both wrong |
| **Location** | `backend/app/data/acousticbrainz.py:_parse` |
| **Found by** | Reading `ENERGY 0.00` on a live recommendation for a loud rock track |

**Issue.** AcousticBrainz publishes no direct energy descriptor, so one had to be
derived. The implementation used the high-level **danceability** classifier's
`all.danceable` probability, with a `# TODO: verify field name` comment attached.
Verifying it — which this audit did — showed the field name was correct and the
*choice of field* was wrong.

**Impact.** Danceability measures whether a track invites dancing, which is close to
orthogonal to energy for guitar music. Queried live for The Killers' "Mr. Brightside":

| Classifier | Probability |
|---|---:|
| `danceability.danceable` | **0.024** |
| `mood_aggressive.aggressive` | 0.983 |
| `mood_party.party` | 0.863 |
| `mood_relaxed.relaxed` | 0.034 |

So the value the engine used as energy was 0.02 for one of the most energetic tracks
in the seed pool. This propagated three ways: into the feature vector's energy
dimension, so cosine similarity ranked on a near-meaningless coordinate; into the
"matching energy level" rationale signal, which could fire between tracks with nothing
energetic in common; and onto the screen, where the recommendation card displayed
"ENERGY 0.00" for a rock song, which simply reads as broken.

**Root cause.** A plausible-sounding proxy adopted without validating it against real
output, and an explicit `TODO` that was never closed.

**Fix.** `_energy(high)` now averages three classifiers that do bear on energy and that
agree with each other on the example above: `mood_aggressive.aggressive`,
`mood_party.party`, and `1 − mood_relaxed.relaxed`. Averaging rather than choosing one
keeps a single mis-classification from dominating; whichever subset is present is used;
danceability remains a last-resort fallback ahead of the fixed default. Mr. Brightside
now scores **0.937** rather than 0.024.

**Verification.** Seven tests in `tests/test_acousticbrainz.py`, including a direct
regression test built from the live probabilities above asserting the track scores
above 0.9, plus fallback-chain and out-of-range handling.

**Knock-on.** The evaluation corpus stores *parsed* acoustic features, so every track
harvested before this fix carried the old value. A `refresh-acoustics` phase was added
to `build_eval_dataset.py` that re-derives the whole corpus through the bulk endpoints
in seconds, and it now runs as part of `all` so a future parser change cannot silently
leave the corpus stale.

**Status.** Fixed and verified.

---

### D3. Ten of the twelve cold-start seed MBIDs were wrong

| | |
|---|---|
| **Severity** | Medium — degraded a documented feature and invalidated a planned evaluation basis |
| **Location** | `backend/app/seeds.py` |
| **Found by** | Verifying every seed identifier against the live MusicBrainz API |

**Issue.** `SEED_TRACKS` pairs each seed title/artist with a MusicBrainz identifier.
Checking all twelve against MusicBrainz found that most did not resolve at all (HTTP
404) and two resolved to **entirely different recordings** — the id labelled
"Bohemian Rhapsody / Queen" returned *Paranoid Android* by Radiohead, and the one
labelled "Hotel California / Eagles" returned *Bohemian Rhapsody* by Queen.

**Impact.** The module's own docstring notes that wrong ids "are skipped gracefully at
runtime", which is true and is why this never surfaced as a crash — but a mislabelled
id is worse than a missing one, because it silently seeds a session with the wrong
track's genre and acoustic profile. The draft report also proposed this pool as the
basis for the offline evaluation's held-out sequences, which would have built the
evaluation on invalid data.

**Root cause.** The identifiers were written by hand and never validated against
MusicBrainz.

**Fix.** Every seed identifier re-resolved against the live MusicBrainz API with a
fielded `recording:"…" AND artist:"…"` query, and a validation script
(`scripts/verify_seeds.py`) added so the check is repeatable rather than a one-off.

**Status.** Fixed and verified.

---

### D4. The test suite made live network calls

| | |
|---|---|
| **Severity** | Medium — an unenforced correctness claim in the README and draft report |
| **Location** | `backend/tests/conftest.py` |
| **Found by** | Adding the ListenBrainz client and noticing `/health` still passed without a mock |

**Issue.** The README and the draft report both state that "all external APIs are
mocked — no real network calls are made". This was a convention, not a constraint:
nothing stopped an unmocked client from reaching the internet. When the ListenBrainz
health probe was added, `test_health_returns_ok` continued to pass — by making a real
HTTP request to ListenBrainz.

**Impact.** Tests silently depending on third-party uptime: they would fail on an
outage and pass for the wrong reason otherwise, and CI would be non-hermetic.

**Root cause.** The claim was never mechanised.

**Fix.** An autouse `_no_network` fixture replaces `socket.socket.connect` with a guard
that raises `AssertionError` on any non-loopback destination. Loopback is allowed
because asyncio's Windows event loop and pytest's own machinery open local socket
pairs; blocking those breaks the runner without catching anything.

**Verification.** Removing any external-client mock now fails the affected test with an
explicit message. The claim is now enforced by the suite rather than asserted in prose.

**Status.** Fixed and verified.

---

### D5. Invalid npm peer-dependency tree and two high-severity advisories

| | |
|---|---|
| **Severity** | Low-medium — reproducibility and supply-chain hygiene |
| **Location** | `frontend/package.json`, `frontend/package-lock.json` |
| **Found by** | `npm ls` / `npm audit` during the dependency audit |

**Issue.** `vite@8.0.16` was installed against `@vitejs/plugin-react@4.7.0`, which
declares support only up to Vite 7 — `npm ls vite` reported the tree as `invalid`, and
a clean `npm install` on another machine could resolve differently or refuse outright.
`npm audit` additionally reported two high-severity advisories (`nanoid`, `postcss`).

**Impact.** The build happened to work, but the dependency graph was not reproducible,
which matters for a submission a marker is expected to clone and run.

**Fix.** `@vitejs/plugin-react` bumped to `^5.2.0` (which declares Vite 8 support) and
`npm audit fix` applied. `npm audit` now reports zero vulnerabilities and `npm ls vite`
reports a valid tree.

**Status.** Fixed and verified.

---

### D5b. An unhandled promise rejection could strand a played track

| | |
|---|---|
| **Severity** | Low-medium — only on an upstream outage, but silent when it happens |
| **Location** | `frontend/src/App.tsx:playTrack` |
| **Found by** | Code review of the play path while investigating a stale-session state |

**Issue.** `playTrack` awaited `resolveTrack(...)` with no error handling. `POST
/resolve` returns 503 when MusicBrainz is unreachable, which makes the client promise
reject and abandons the rest of the function.

**Impact.** During a MusicBrainz outage the track would start playing but never enter
the setlist, no recommendation would be requested, and the only trace would be an
unhandled rejection in the browser console. The user sees a player and an otherwise
inert application with no explanation.

**Fix.** The resolve call is wrapped; a failure is treated as "unresolved" so playback
and history still work. The track simply cannot seed a recommendation, which
`useRecommendation` already explains to the user in plain language.

**Status.** Fixed.

---

### D5c. A padded identifier passed validation, then failed as a 503

| | |
|---|---|
| **Severity** | Medium — a client input error reported slowly, as a server fault |
| **Location** | `backend/app/models/request.py`, `backend/app/api/routes.py` |
| **Found by** | An adversarial input sweep against the live API (32 hostile cases) |

**Issue.** `is_valid_mbid` matches against `value.strip()`, so `"  <mbid>  "` passes
validation. The route then passed the **unstripped** value downstream. Validating one
value and using a different one is the defect; the padded string reached
`musicbrainzngs`, which retried eight times before failing with `URL can't contain
control characters`, and the generic exception handler classified that as
`ConnectionError` → **HTTP 503 "MusicBrainz unavailable"**.

**Impact.** A malformed client request produced a slow (eight upstream retries)
response blaming a third party that was working perfectly. For an API whose failure
contract is one of its selling points, misreporting a 400 as a 503 is a contract
violation, and the latency makes it a minor denial-of-service vector.

**Root cause.** The leniency in the validator was never carried through to the value
actually used — a validate-here/use-there split.

**Fix.** A `normalise_mbid` function returns the canonical form (stripped, lower-cased),
and the route maps the history through it immediately after validation, so the value
that was validated is the value that is used. The validator's docstring now records why
the strip is there.

**Verification.** Three regression tests in `tests/test_api.py` assert that a padded and
an upper-cased identifier both reach the data layer in canonical form, and that a
genuinely malformed identifier is still rejected with a 400. The adversarial sweep
now returns 32/32 acceptable.

**Status.** Fixed and verified.

---

### D6. Type-safety gaps in untyped external JSON handling

| | |
|---|---|
| **Severity** | Low — latent, none observed in practice |
| **Location** | `app/data/acousticbrainz.py`, `app/engine/features.py`, `app/data/youtube.py` |
| **Found by** | `mypy` |

**Issue.** Three related problems: `float()` applied directly to untyped values pulled
from third-party JSON (an AcousticBrainz field of an unexpected type would raise);
`asyncio.gather(..., return_exceptions=True)` results narrowed with
`isinstance(x, Exception)` rather than by the positive type, which does not exclude
non-`Response` values; and a `str` passed where `ytmusicapi` expects a `Literal`.

**Fix.** An `_as_float(value, default)` helper that narrows before coercing, positive
narrowing on `httpx.Response`, and a `Literal`-typed search-filter tuple. The mixed-type
`DEFAULT_ACOUSTIC` dict was also split into individually-typed constants
(`DEFAULT_TEMPO`, `DEFAULT_KEY`, …) with the dict retained for compatibility.

**Verification.** `mypy app` reports no issues across 23 source files.

**Status.** Fixed and verified.

---

## Part 2 — Missing functionality implemented

### I1. Aggregate collaborative re-ranking (cascade stage 2) — Objective 4

The preliminary and draft designs both specified a three-stage cascade hybrid
(Burke, 2002): content-based candidate generation, aggregate collaborative re-ranking,
and diversity post-processing. Only the first stage existed.

**What was built.** `app/data/listenbrainz.py` (client) and
`app/engine/collaborative.py` (scoring), wired into `recommender._rank` as stage 2.

**Design decision: ListenBrainz rather than Last.fm.** The draft named Last.fm as the
collaborative source. ListenBrainz is used instead, for three project-specific reasons:

1. **No API key.** Last.fm requires per-developer key registration. ListenBrainz's labs
   endpoints are open, preserving NextTrack's "clone and run, no credentials" property
   — the same argument that moved playback from the YouTube Data API to `ytmusicapi`.
2. **MBID-native.** ListenBrainz similarity is keyed on MusicBrainz identifiers, which
   the pipeline already carries end to end. Last.fm is keyed on `(artist, track)` name
   strings and would have needed a second, lossy name-matching layer — precisely the
   class of problem the two-ID resolution model was introduced to contain.
3. **Aggregate, not personal.** The endpoint returns artist-level co-listening
   similarity computed over the whole ListenBrainz population. NextTrack sends one
   artist MBID and receives a ranked list; no user, session, or history is transmitted,
   so the collaborative signal does not weaken the statelessness guarantee.

**Design decision: artist-level rather than track-level similarity.** ListenBrainz
publishes both. Track-level similarity was tried first and returned empty results for
most seeds in this project's catalogue (verified empirically during development),
whereas artist-level similarity resolves for essentially any charting artist. Artist
co-listening also captures the relationship content features structurally cannot: two
tracks whose descriptors diverge but whose audiences overlap.

**Scoring.** Each history artist's similar-artist list is normalised against its own
maximum before merging (raw scores are co-occurrence counts whose magnitude depends on
the reference artist's popularity, so they are not comparable across artists), and an
artist matching several history artists takes the strongest normalised score rather
than the sum, which keeps affinity bounded in [0, 1]. The blend is
`(1−w)·content + w·collaborative` with `w = 0.3`, applied only where collaborative
evidence exists — with no evidence the content score passes through unchanged, so
partial ListenBrainz coverage weakens the stage rather than deflating the confidence
score reported to the user.

**Tests.** `tests/test_collaborative.py` (8 unit tests on the scoring maths),
`tests/test_listenbrainz.py` (15 tests, most of them failure paths: HTTP errors,
malformed payloads, transport failures, timeouts, caching, and the requirement that a
failure is *not* cached), and pipeline-level tests in `tests/test_pipeline.py`.

---

### I2. MMR diversity re-ranking (cascade stage 3) — Objective 4

**What was built.** `app/engine/diversity.py`, implementing Carbonell and Goldstein's
(1998) Maximal Marginal Relevance as stage 3.

**Design decision: seeding the selected set with the listening history.** Classical MMR
trades a document's relevance against its redundancy with items *already selected*:
`λ·rel(c, Q) − (1−λ)·max_{s∈S} sim(c, s)`. A next-track recommender emits one item, so
an MMR whose `S` starts empty reduces to plain relevance ranking on the first pick and
changes nothing at all. NextTrack therefore seeds `S` with the session history, which
makes the redundancy term measure what actually matters here: how close the candidate
is to music the listener has just heard. That is exactly the over-specialisation
Lops et al. (2011) predict for pure content-based filtering, and which the draft
report's own testing observed.

`λ = 1` recovers pure relevance ranking, so the stage is exactly ablatable — the
evaluation's "no diversity" arm runs the same code path with `λ = 1` rather than a
separate branch.

**Tests.** `tests/test_diversity.py` — 9 tests including the ablation identity at
`λ = 1`, near-duplicate demotion, greedy accumulation into `S` across slots,
determinism under ties (a statelessness requirement), and the intra-list-diversity
metric's bounds.

---

### I3. Pipeline configuration and the ablation study — Objective 4

`recommender.PipelineConfig` makes each stage independently switchable. The API always
constructs the full pipeline; only the evaluation harness builds reduced
configurations. `recommend_ranked()` was split out of `recommend()` so the evaluation
can obtain a ranked list without spending a YouTube lookup per candidate, while the
API layers playback resolution on top of exactly the same ranking code.

---

### I4. Offline evaluation harness and held-out dataset — Objective 6

Three scripts under `backend/scripts/`:

- `build_eval_dataset.py` — harvests held-out listening sequences from **real public
  ListenBrainz listening histories**, segmented into sessions on a 30-minute
  inactivity gap. Runs in three resumable, checkpointed phases.
- `augment_catalogue.py` — snapshots the *real* MusicBrainz candidate-retrieval
  responses so the evaluation ranks the held-out track against the pool the live engine
  would actually retrieve.
- `offline_eval.py` — runs seven arms (three baselines, four engine configurations)
  over the same sessions and candidate pools.

**Design decision: real listening sessions rather than the curated seed pool.** The
draft proposed building held-out sequences from `seeds.py`. That would have been
circular — sequences assembled by the developer from a genre-organised pool, used to
evaluate a genre-driven recommender, measure how well the engine reproduces the
developer's own grouping. Real listening sessions are constructed with no knowledge of
genre, tempo or co-listening, so they are independent of every signal the engine ranks
on.

**Design decision: the engine evaluates itself.** The harness calls
`recommender.recommend_ranked` directly with the data clients redirected at the
snapshot. Only the network is stubbed. An evaluation that re-implements the scoring
logic measures the re-implementation.

**Privacy handling.** ListenBrainz histories are published openly by their owners, but
since NextTrack's argument is about not accumulating listener profiles, the corpus
stores usernames only as a salted SHA-256 prefix and retains no timestamps beyond the
session segmentation. See `FINAL_REQUIREMENTS_AUDIT.md` for the full note.

---

### I5. Frontend test suite — Objective 5

The backend had 37 tests; the frontend had none. Vitest + React Testing Library added,
with 29 tests covering the two pieces of frontend logic with real correctness
properties:

- `useRecommendation` — the monotonic request-id race guard (a stale *success* and a
  stale *failure* must both be discarded), MBID filtering, exclusion accumulation
  across "next alternative", reset semantics, and in-flight invalidation on `clear()`.
- `useLocalStorageState` — schema-guard fallback, malformed-JSON fallback, functional
  updates, reset, and survival of a `localStorage` quota failure.
- `mockData` — the D2 regression tests.

A pre-existing infrastructure problem surfaced here: Vitest's default `forks` pool
times out starting workers on this Windows/OneDrive checkout. `pool: 'threads'` is
configured in `vitest.config.ts` with a comment explaining why.

---

### I6. Health endpoint and response schema extended

`GET /api/v1/health` now probes ListenBrainz alongside the other three sources, and
`SourcesStatus` (backend) and `HealthStatus` (frontend `types.ts`) carry the new field.

---

## Part 3 — Test-suite changes and their justification

Two existing artefacts were modified. Neither weakens an assertion.

**`tests/fixtures/musicbrainz_recording.json` — extended.** The fixture catalogue held
four tracks, all by Nirvana. Artist-level co-listening cannot be exercised on a
single-artist catalogue, so two tracks by two further artists (Pearl Jam, Soundgarden)
were added, along with `artist_mbid` on every recording and a `similar_artists` block.
Nothing was removed.

**`tests/test_recommend_errors.py::test_no_candidates_found` — updated.** The test
empties the candidate pool by excluding every artist in the catalogue, then asserts the
`no_candidates_found` reason code. With three artists in the fixture instead of one, it
now excludes all three. The assertion is unchanged; only the input needed to reach the
condition changed. The reason for the change is documented in the test's own docstring.

---

## Part 4 — Verified as already correct

Checked against the draft report's claims and found accurate, requiring no change:

- **Request-scoped genre vocabulary isolation.** The await-free block in
  `recommender._rank` genuinely prevents cross-request vocabulary leakage. Preserved
  verbatim through the cascade refactor, with the constraint restated in the new
  function's docstring, and still covered by `tests/test_recommend_concurrency.py`.
- **Graceful AcousticBrainz degradation.** A missing acoustic record is treated as the
  normal case, substitutes fixed defaults, and propagates `limited_acoustic_data` to the
  API response and a leading note in the rationale.
- **Deterministic genre tie-breaking** in `_top_genres` (first appearance, not set
  iteration order).
- **Deterministic daily Top 5** — `random.Random` seeded on the UTC date, with no
  server-side storage of what was shown.
- **No secrets in the repository.** `.env` contains only a comment recording that the
  previously-stored YouTube key was removed; `.gitignore` excludes `.env` files at both
  levels. No credentials, tokens, or keys were found anywhere in the tree.
