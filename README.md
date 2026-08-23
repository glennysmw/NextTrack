# NextTrack

## What is NextTrack?

NextTrack is a privacy-first, **stateless** music recommendation API with a polished
React demo frontend. You play a song; NextTrack analyses its tempo, key, genre, and
energy, then recommends what should come next — and tells you exactly *why*.

The engine is a three-stage cascade hybrid:

1. **Content-based** — each track becomes a feature vector (tempo, key, mode, energy,
   loudness, plus a request-scoped genre TF-IDF block); candidates are scored by cosine
   similarity to the session centroid.
2. **Aggregate collaborative** — ListenBrainz artist co-listening similarity, computed
   across the whole ListenBrainz population, is blended into the relevance score. No
   user data is sent or stored; only an artist identifier goes out.
3. **Diversity (MMR)** — Maximal Marginal Relevance re-ranks against the *listening
   history*, so a candidate that merely duplicates what was just played is demoted.

Metadata comes from MusicBrainz, acoustic features from AcousticBrainz, collaborative
signal from ListenBrainz, and playback from YouTube Music. Playback prefers each
artist's **official** track (not covers or parodies), the way YouTube Music does.

## The privacy story

The server stores **no user data between requests**. Every recommendation call is
self-contained: the client sends its listening history, the server returns the next
track, and then forgets everything. There are no accounts, no tracking, and no
server-side database — your session lives only in your browser tab (via `localStorage`),
and closing the tab erases it.

## Prerequisites

- **Python 3.11+**
- **Node.js 20+**

> **No API keys required.** All four upstream services are open. Playback is resolved
> through YouTube Music's internal API via
> [`ytmusicapi`](https://github.com/sigma67/ytmusicapi) — no Google API key and no daily
> quota. (Earlier versions used the YouTube Data API v3, whose ~100-searches/day free
> quota this app exhausted almost immediately.) The collaborative signal comes from
> ListenBrainz's open labs endpoints rather than Last.fm, which would have required a
> registered developer key.

## Setup

Clone the repository, then set up each half.

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

The backend needs **no required configuration**. Optionally, copy the env template at
the **project root** (one level above `backend/`) to override CORS origins or log level:

```bash
cp .env.example .env            # Windows: copy .env.example .env  (optional)
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env            # Windows: copy .env.example .env
```

## Running

Run the backend and frontend in two separate terminals.

**Backend** (from `backend/`, with the venv active):

```bash
uvicorn app.main:app --reload
```

- API: <http://localhost:8000>
- Interactive API docs (Swagger UI): <http://localhost:8000/docs>

**Frontend** (from `frontend/`):

```bash
npm run dev
```

- App: <http://localhost:5173>

Open the app, pick a seed track (or search for one), and watch the recommendations —
with rationales — appear.

## Testing

**Backend** (118 tests, from `backend/`):

```bash
pytest -v
```

**Frontend** (29 tests, from `frontend/`):

```bash
npm test
```

Every external API (MusicBrainz, AcousticBrainz, ListenBrainz, YouTube) is mocked in the
backend suite, and this is *enforced*, not merely intended: an autouse fixture replaces
`socket.connect` with a guard that fails any test attempting a non-loopback connection,
so an unmocked client fails loudly rather than silently depending on third-party uptime.

### Adversarial input sweep

With the backend running, a 32-case hostile-input sweep checks that no malformed request
produces a 5xx:

```bash
cd backend && python scripts/adversarial_sweep.py
```

### Static checks

```bash
cd backend && ruff check . && mypy app
```

```bash
cd frontend && npm run typecheck
```

## Evaluation

The offline evaluation, its held-out dataset, and the figures in the report are all
reproducible from `backend/scripts/`:

```bash
python scripts/build_eval_dataset.py all   # harvest held-out sessions (network, slow)
python scripts/augment_catalogue.py        # snapshot real candidate retrieval (network)
python scripts/offline_eval.py             # run the ablation offline and deterministically
python scripts/make_figures.py             # render every figure from the raw results
```

Results, raw data and figures live in `docs/final-evidence/`. See
`FINAL_REQUIREMENTS_AUDIT.md` for the requirements traceability matrix and
`FINAL_ENGINEERING_LOG.md` for the defect and implementation record.

## Demo mode

To run the frontend offline (no backend at all), set demo mode in
`frontend/.env`:

```
VITE_DEMO_MODE=true
```

Search returns a fixed set of results and recommendations follow a deterministic,
reproducible sequence. YouTube IDs are real, so playback still works. A **DEMO MODE**
banner appears at the top of the screen while it is active.

## Known limitations

- **AcousticBrainz coverage gaps** — the service was largely decommissioned in 2022, so
  many tracks lack acoustic data. NextTrack falls back to default acoustic features and
  flags the recommendation (`limited_acoustic_data`) when this happens; the fallback is
  the norm, not the exception.
- **MusicBrainz rate limit** — 1 request/second, so recommendation latency is dominated
  by upstream lookups on a cold cache.
- **In-memory cache only** — fetched features, ListenBrainz similarity, and YouTube
  lookups are cached per process and lost on restart. (Redis is planned for Phase 2.)
- **Partial collaborative coverage** — ListenBrainz artist similarity resolves for
  well-listened artists but returns nothing for the long tail. A candidate with no
  collaborative evidence keeps its content score unchanged rather than being penalised.
- **Unofficial playback API** — `ytmusicapi` talks to YouTube Music's internal API. It
  needs no key and has no quota, but is undocumented and could change without notice.
- **Embedding restrictions** — a small number of official videos disable third-party
  embedding; for recommendations NextTrack falls through to the next candidate.

## Project structure

```
nexttrack/
├── README.md
├── .gitignore
├── .env.example                     # optional CORS_ORIGINS / LOG_LEVEL overrides
├── FinalReport.md                   # CM3070 final project report
├── FINAL_REQUIREMENTS_AUDIT.md      # requirements traceability matrix
├── FINAL_ENGINEERING_LOG.md         # defects found/fixed, functionality implemented
├── FINAL_SUBMISSION_READINESS.md    # environment, build, test and verification record
├── FINAL_VIDEO_PLAN.md              # demonstration video plan
├── docs/
│   ├── REMAINING_WORK.md            # pre-existing gap analysis (superseded)
│   └── final-evidence/              # results, figures, screenshots, API transcripts
├── backend/
│   ├── requirements.txt
│   ├── requirements-dev.txt         # ruff, mypy, matplotlib
│   ├── pyproject.toml               # pytest, ruff and mypy configuration
│   ├── app/
│   │   ├── main.py                  # FastAPI app, CORS, lifespan, error handler
│   │   ├── config.py                # settings and tunables
│   │   ├── seeds.py                 # verified cold-start MBIDs
│   │   ├── daily.py                 # Today's Top 5 (date-seeded, no storage)
│   │   ├── models/                  # request.py, response.py (Pydantic v2)
│   │   ├── engine/
│   │   │   ├── recommender.py       # cascade orchestration + PipelineConfig
│   │   │   ├── features.py          # feature vectors, request-scoped genre TF-IDF
│   │   │   ├── similarity.py        # centroid + cosine  (stage 1)
│   │   │   ├── collaborative.py     # ListenBrainz affinity blending (stage 2)
│   │   │   ├── diversity.py         # MMR re-ranking + ILD metric (stage 3)
│   │   │   └── rationale.py         # plain-language explanation
│   │   ├── data/
│   │   │   ├── musicbrainz.py       # metadata + genre tags (rate-limited)
│   │   │   ├── acousticbrainz.py    # acoustic features, incl. bulk fetching
│   │   │   ├── listenbrainz.py      # aggregate artist co-listening
│   │   │   ├── youtube.py           # playback resolution via ytmusicapi
│   │   │   └── cache.py             # features, video ids, genre candidate pools
│   │   └── api/routes.py            # the five endpoints
│   ├── data/                        # committed evaluation corpus and sessions
│   ├── scripts/
│   │   ├── build_eval_dataset.py    # harvest held-out listening sessions
│   │   ├── augment_catalogue.py     # snapshot real candidate retrieval
│   │   ├── offline_eval.py          # baselines + ablation, offline and deterministic
│   │   ├── make_figures.py          # every figure, from the raw results
│   │   ├── latency_benchmark.py     # live end-to-end latency
│   │   ├── capture_api_examples.py  # live request/response transcripts
│   │   └── verify_seeds.py          # validate seed MBIDs against MusicBrainz
│   └── tests/                       # 115 tests across 14 files
│       ├── conftest.py              # mocked externals + enforced network guard
│       ├── fixtures/
│       ├── test_api.py              test_pipeline.py        test_diversity.py
│       ├── test_collaborative.py    test_listenbrainz.py    test_acousticbrainz.py
│       ├── test_candidate_cache.py  test_network_guard.py   test_musicbrainz.py
│       ├── test_features.py         test_similarity.py      test_rationale.py
│       └── test_recommend_errors.py test_recommend_concurrency.py
└── frontend/
    ├── package.json                 # dev, build, test, typecheck
    ├── vite.config.ts               vitest.config.ts
    ├── tsconfig.json                tailwind.config.js      postcss.config.js
    ├── .env.example                 # VITE_API_URL, VITE_DEMO_MODE
    └── src/
        ├── App.tsx                  # state container + layout
        ├── types.ts                 constants.ts            index.css
        ├── mockData.ts              # demo mode (real MBIDs, so it uses the live path)
        ├── mockData.test.ts
        ├── api/nexttrack.ts
        ├── hooks/
        │   ├── useLocalStorageState.ts   useLocalStorageState.test.ts
        │   └── useRecommendation.ts      useRecommendation.test.ts
        ├── test/setup.ts
        └── components/              # Header, SearchBar, SearchResults, TopTracks,
                                     # Player, HistoryList, RecommendationCard,
                                     # PreferenceControls, FeedbackButtons, ModeToggle,
                                     # AlbumArt, Equalizer, PrivacyBadge
```

## API reference (summary)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/search` | Search YouTube Music for official songs (title/artist) |
| `GET`  | `/api/v1/top` | Today's Top 5 — a daily-rotating set with album art |
| `POST` | `/api/v1/resolve` | Map a played track (title + artist) → MusicBrainz id |
| `POST` | `/api/v1/recommend` | Next track for a listening history + rationale |
| `GET`  | `/api/v1/health` | Version, cache stats, upstream source status (4 sources) |

See the live Swagger UI at <http://localhost:8000/docs> for full request/response schemas.

---

*NextTrack v0.1 — a Final Year Project demo. Research grounding: Whitman & Lawrence
(2002), Burke (2002), Fielding (2000), Cavoukian (2009).*
