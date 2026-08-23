# NextTrack — Demonstration Video Plan

**Target length:** 4:00–4:30 (the brief allows 3–5 minutes; aim for 4:15 so a retake or
a slightly slower delivery still lands inside the window).

**Constraints from the brief, restated because breaking any of them is penalised:**

- Your own spoken narration throughout. **No AI-generated voice.**
- **No speed-up.** Record at normal pace; if it runs long, cut a scene rather than
  compress time.
- Must show the project *actually working*, not slides describing it.
- Appearing on camera is optional; audio is mandatory.
- Visuals should be appropriate and legible.

---

## Before you record

**Technical setup**

1. Start the backend from a clean process: `uvicorn app.main:app` — the caches must be
   empty so the "warm-up" behaviour in scene 3 is genuine.
2. Start the frontend: `npm run dev`, in **live mode** (`VITE_DEMO_MODE=false`). Demo
   mode is a fallback only; the brief rewards a working project, and the live system
   works. Have demo mode ready as a backup if the network misbehaves on the day — and
   if you fall back to it, say so on camera.
3. **Warm the caches first with one throwaway request**, then reset the browser
   session. The first cold request takes tens of seconds because of MusicBrainz's
   1 req/sec limit, and dead air is worse than a slightly less "pure" demo. Mention
   the cold/warm difference verbally instead of making the viewer sit through it —
   this is honest, and scene 3 explains exactly why the difference exists.
4. Screen resolution 1920×1080, browser zoom 100–110% so text is readable after
   compression. Close unrelated tabs and notifications.
5. Have these ready in tabs or windows so you never hunt for anything on camera:
   - the app at `localhost:5173`
   - Swagger UI at `localhost:8000/docs`
   - `docs/final-evidence/fig_ablation.png`
   - `docs/final-evidence/fig_accuracy.png`

**Rehearse once without recording.** The timings below are tight; one dry run is
usually the difference between 4:15 and 6:00.

---

## Scene-by-scene

### 1 — What NextTrack is, and the question it asks · 0:00–0:25 (25s)

**On screen:** the app's home view — header with the "STATELESS · NO TRACKING" badge,
Today's Top 5 below it.

**Narration (suggested):**
> "This is NextTrack, a music recommendation API built for Template 7.2. Almost every
> commercial recommender works by building a permanent profile of you. NextTrack asks
> whether that's actually necessary: the server here stores nothing about a listener
> between requests. Every recommendation is computed from the listening history the
> client sends in that one call, and then forgotten. The question the project sets out
> to answer is whether a recommender can still be useful under that constraint."

**Why this first:** the review criteria reward a justified concept. Lead with the
research question, not the feature list.

---

### 2 — The core loop, working · 0:25–1:45 (80s)

**On screen:** click a track in Today's Top 5 → the player starts → the setlist
records it → the *Recommended Next* card appears with its rationale, match score, and
tempo/key/energy readout. Then click **PLAY NEXT** to show the loop continuing, and
**NEXT OPTION** once to show the alternative path.

**Narration:**
> "I'll play something from today's picks. The track starts immediately, and in the
> background the app resolves it to a MusicBrainz identifier — search results carry a
> YouTube id, but the engine needs a MusicBrainz one, so that resolution happens lazily,
> only when a track is actually played.
>
> Here's the recommendation. Every response carries a plain-language reason, and the
> reason names the signals that actually matched — here it's [read the rationale
> aloud]. That matters because explainability is one of the things the literature
> identifies as supporting user trust, and it's also how I can tell at a glance which
> part of the engine is doing the work.
>
> Play Next continues the session, and Next Option asks for a different candidate
> while excluding the one I just rejected — again with no server-side memory of any of
> it, because the client sends the whole history each time."

**Pause on the rationale line long enough to read it.** It is the single most
demonstrable thing in the product.

---

### 3 — How it actually works · 1:45–3:00 (75s)

Pick **two** beats. Do not attempt all of them — this is where videos overrun.

**Beat A — the three-stage cascade (essential; this is the technical core).**

**On screen:** the recommendation card, then briefly the Swagger `/recommend` schema,
or a code window on `engine/recommender.py`.

> "Behind that card the engine runs three stages. First, content-based: every track
> becomes a feature vector — tempo, key, mode, energy, loudness, and a genre TF-IDF
> block — and candidates are scored by cosine similarity to the average of my session.
>
> Second, a collaborative stage. This is aggregate, not personal: I send ListenBrainz
> one artist identifier and get back artists that the whole ListenBrainz population
> tends to listen to alongside it. No user data leaves the server, so I get
> collaborative evidence without giving up statelessness. That's the stage that
> produced [name a cross-genre recommendation — e.g. Daft Punk to Röyksopp], which
> pure content matching would never have surfaced.
>
> Third, diversity re-ranking using Maximal Marginal Relevance, which penalises a
> candidate for being too similar to what I've *already heard* — that's the fix for
> the over-specialisation that content-based filtering is known for, and which my own
> earlier testing had found."

**Beat B — pick ONE of these:**

- *Reproducibility (recommended — it is the most interesting finding).* Show the same
  `/recommend` request run twice in Swagger returning the identical track.
  > "A stateless API ought to be reproducible: same input, same answer. It wasn't. I
  > found that MusicBrainz's tag search returns a different result set on every call —
  > two consecutive searches for 'grunge' shared none of their fifty results. So the
  > engine now caches the candidate pool per genre, which makes repeated requests
  > reproducible and, as a side effect, took a warm recommendation from about a minute
  > down to under a second."

- *Graceful degradation.* Show a recommendation whose card carries the "limited
  acoustic data" note.
  > "AcousticBrainz was largely decommissioned in 2022, so most tracks have no acoustic
  > data at all. Rather than fail or pretend, the system substitutes defaults and says
  > so — both in the API response and in the sentence the user reads."

---

### 4 — Evaluation, honestly · 3:00–4:00 (60s)

**On screen:** `fig_accuracy.png`, then `fig_ablation.png`.

> "To evaluate it I built a held-out dataset from real public ListenBrainz listening
> histories — [N] sessions from [M] listeners, split on a thirty-minute gap, with the
> last track of each session held back as the answer. Using real sessions matters:
> they're constructed with no knowledge of genre or tempo, so they don't quietly
> reward the engine for its own assumptions.
>
> [Read the headline comparison against the baselines from fig_accuracy.]
>
> And this is the ablation — what each stage actually contributes. [Read the honest
> result: which stages helped accuracy, which traded accuracy for diversity, which did
> less than hoped.]
>
> What I don't have is a user study. It was planned, it needs human participants, and
> I didn't run one — so I can tell you how often the engine predicts the right next
> track, but not whether listeners *enjoy* what it picks. That's the main gap in the
> evaluation and I'd rather name it than paper over it."

**Fill the bracketed values from `docs/final-evidence/offline_eval_summary.csv`
immediately before recording, and read the numbers off the figure on screen.** Do not
approximate from memory.

---

### 5 — Close · 4:00–4:15 (15s)

**On screen:** back to the running app.

> "So: a stateless recommender is clearly buildable, and it produces explained,
> reproducible recommendations from a single request. Whether it's *good enough* to
> replace a profile-based one is the part still open — that needs listeners, not
> metrics. The code is at [repository URL]. Thanks for watching."

---

## Checklist before uploading

- [ ] Length between 3:00 and 5:00 — check the final file, not the timeline estimate
- [ ] Your own voice throughout; no synthetic narration
- [ ] Playback speed unmodified
- [ ] Audio audible and free of clipping; no background music over speech
- [ ] The working application is on screen for the majority of the runtime
- [ ] Every number spoken matches `docs/final-evidence/offline_eval_summary.csv`
- [ ] The repository URL is stated and correct
- [ ] No credentials, personal email, or private paths visible on screen
- [ ] You state that no user study was conducted, rather than implying otherwise

## What to cut first if it runs long

1. The **NEXT OPTION** demonstration in scene 2 (10s)
2. Beat B in scene 3 — keep the cascade explanation, drop the second beat (25s)
3. The Swagger view — the cascade can be narrated over the app itself (10s)

Never cut: the rationale being read aloud, the ablation figure, or the sentence
acknowledging the missing user study.
