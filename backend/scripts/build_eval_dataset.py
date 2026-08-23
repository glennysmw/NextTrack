"""Harvest a held-out evaluation corpus from public data. Run once; not part of the API.

Why real listening sessions rather than a hand-built pool
--------------------------------------------------------
The draft report planned to build held-out sequences from the project's own curated
seed list. That would have been circular: sequences assembled by the developer from a
genre-organised pool, used to evaluate a genre-driven recommender, measure how well
the engine reproduces the developer's own grouping — not whether it predicts what a
listener actually plays next.

This script instead builds the ground truth from **real, voluntarily-public
ListenBrainz listening histories**. Each user's listens are segmented into sessions on
a 30-minute inactivity gap (the standard threshold in the session-based
recommendation literature, e.g. Hidasi et al., 2016); the final track of each session
is held out as the ground-truth "next track" and the preceding tracks form the history
a /recommend call would carry. Nothing about the sequence's construction knows
anything about genre, tempo, or co-listening, so it is independent of every signal the
engine ranks on.

Privacy
-------
ListenBrainz listening histories are published openly by their owners, and this
harvest reads only that public endpoint. Even so, since NextTrack's entire argument is
about not accumulating listener profiles, the corpus stores usernames only as a salted
SHA-256 prefix and keeps no timestamps beyond the session segmentation performed here.
The saved corpus therefore contains track identifiers and session boundaries, not
identifiable listening histories.

Phases (each resumable)
-----------------------
``sessions``  discover users, fetch listens, segment into sessions   -> eval_sessions_raw.json
``enrich``    MusicBrainz metadata + AcousticBrainz features         -> eval_corpus.json
``refresh-acoustics``  re-derive acoustics in bulk after a parser change
``finalise``  keep only fully-resolved sessions, add LB similarity   -> eval_sessions.json

Enrichment checkpoints every few tracks, so an interrupted run resumes where it left
off rather than restarting — MusicBrainz's 1 req/sec limit makes a full pass expensive
enough that this matters in practice.

Usage:
    python scripts/build_eval_dataset.py sessions  [--users 45] [--sessions 150]
    python scripts/build_eval_dataset.py enrich    [--max-tracks 700]
    python scripts/build_eval_dataset.py finalise
    python scripts/build_eval_dataset.py all
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import pathlib
import sys
import time

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.data import acousticbrainz, listenbrainz, musicbrainz  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
logger = logging.getLogger("build_eval_dataset")

DATA_DIR = pathlib.Path(__file__).resolve().parents[1] / "data"
RAW_SESSIONS_PATH = DATA_DIR / "eval_sessions_raw.json"
CORPUS_PATH = DATA_DIR / "eval_corpus.json"
SESSIONS_PATH = DATA_DIR / "eval_sessions.json"

LB_API = "https://api.listenbrainz.org/1"
SEED_USERS = ["rob", "alastairp", "mr_monkey", "akshaaatt", "lucifer"]

SESSION_GAP_SECONDS = 30 * 60      # standard session boundary
MIN_SESSION_LEN = 4                # >= 3 history tracks + 1 held-out target
MAX_SESSION_LEN = 8
LISTENS_PER_USER = 400
CHECKPOINT_EVERY = 20

# MusicBrainz responses are frequently slower than the API client's default socket
# timeout allows; a too-tight timeout turns a slow response into a retry that costs
# the timeout *plus* the retry, so a generous bound is measurably faster overall.
MB_SOCKET_TIMEOUT = 25.0

# MusicBrainz's published limit is one request per second, but sustained requests at
# exactly 1.0s draw 503 throttling responses, and musicbrainzngs answers a 503 with a
# backoff-and-retry that costs far more than the headroom. Pacing slightly under the
# limit is measurably faster end to end.
MB_ENRICH_INTERVAL_SECONDS = 1.3

# Usernames are hashed with this salt before storage; it is a de-identification
# measure for a local research artefact, not a security secret.
_SALT = b"nexttrack-offline-eval"


def _pseudonym(username: str) -> str:
    return hashlib.sha256(_SALT + username.encode()).hexdigest()[:12]


def _get(url: str, params: dict | None = None) -> dict | None:
    for attempt in range(3):
        try:
            resp = httpx.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            logger.warning("HTTP %s from %s", resp.status_code, url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("request failed (%s/3) %s: %s", attempt + 1, url, exc)
        time.sleep(2 * (attempt + 1))
    return None


# ------------------------------------------------------------------ phase: sessions


def discover_users(target: int) -> list[str]:
    """Snowball outward from the seed users via ListenBrainz's similar-users graph."""
    found: list[str] = []
    seen: set[str] = set()
    queue = list(SEED_USERS)
    while queue and len(found) < target:
        user = queue.pop(0)
        if user in seen:
            continue
        seen.add(user)
        found.append(user)
        payload = _get(f"{LB_API}/user/{user}/similar-users")
        for row in (payload or {}).get("payload", [])[:8]:
            name = row.get("user_name")
            if name and name not in seen:
                queue.append(name)
    logger.info("discovered %d users", len(found))
    return found[:target]


def fetch_listens(user: str) -> list[dict]:
    """Return the user's recent listens that carry a mapped recording MBID."""
    payload = _get(f"{LB_API}/user/{user}/listens", {"count": LISTENS_PER_USER})
    listens = (payload or {}).get("payload", {}).get("listens", [])
    rows = []
    for listen in listens:
        meta = listen.get("track_metadata", {})
        mapping = meta.get("mbid_mapping") or {}
        info = meta.get("additional_info") or {}
        mbid = mapping.get("recording_mbid") or info.get("recording_mbid")
        if not mbid:
            continue
        artist_mbids = mapping.get("artist_mbids") or info.get("artist_mbids") or []
        rows.append(
            {
                "mbid": mbid,
                "artist_mbid": artist_mbids[0] if artist_mbids else None,
                "listened_at": int(listen.get("listened_at", 0)),
            }
        )
    rows.sort(key=lambda r: r["listened_at"])  # API returns newest-first
    return rows


def sessionise(listens: list[dict]) -> list[list[dict]]:
    """Split a chronological listen stream on a 30-minute inactivity gap."""
    sessions: list[list[dict]] = []
    current: list[dict] = []
    previous_ts = None
    for row in listens:
        if previous_ts is not None and row["listened_at"] - previous_ts > SESSION_GAP_SECONDS:
            if len(current) >= MIN_SESSION_LEN:
                sessions.append(current)
            current = []
        current.append(row)
        previous_ts = row["listened_at"]
    if len(current) >= MIN_SESSION_LEN:
        sessions.append(current)
    return sessions


def _dedupe_consecutive(session: list[dict]) -> list[dict]:
    """Drop immediate repeats (a track put on loop is not a next-track signal)."""
    out: list[dict] = []
    for row in session:
        if not out or out[-1]["mbid"] != row["mbid"]:
            out.append(row)
    return out


def phase_sessions(user_target: int, session_target: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    users = discover_users(user_target)

    sessions: list[dict] = []
    # Cap sessions per listener so the sample is not dominated by one heavy user.
    per_user_cap = max(2, session_target // max(len(users) // 2, 1))
    for user in users:
        if len(sessions) >= session_target:
            break
        taken = 0
        for raw in sessionise(fetch_listens(user)):
            if taken >= per_user_cap or len(sessions) >= session_target:
                break
            session = _dedupe_consecutive(raw)[:MAX_SESSION_LEN]
            if len(session) < MIN_SESSION_LEN:
                continue
            sessions.append(
                {
                    "listener": _pseudonym(user),
                    "history": [t["mbid"] for t in session[:-1]],
                    "target": session[-1]["mbid"],
                }
            )
            taken += 1
        logger.info("%s -> +%d (%d total)", _pseudonym(user), taken, len(sessions))
        time.sleep(0.3)

    RAW_SESSIONS_PATH.write_text(json.dumps(sessions, indent=1), encoding="utf-8")
    distinct = {m for s in sessions for m in (*s["history"], s["target"])}
    logger.info(
        "wrote %s: %d sessions referencing %d distinct tracks",
        RAW_SESSIONS_PATH.name, len(sessions), len(distinct),
    )


# -------------------------------------------------------------------- phase: enrich


def _load_corpus() -> dict:
    if CORPUS_PATH.exists():
        return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return {"tracks": {}, "similar_artists": {}, "unresolvable": []}


def _save_corpus(corpus: dict) -> None:
    CORPUS_PATH.write_text(json.dumps(corpus, indent=1), encoding="utf-8")


async def phase_enrich(max_tracks: int) -> None:
    import socket
    import time as _time

    settings.MUSICBRAINZ_RATE_LIMIT_SECONDS = MB_ENRICH_INTERVAL_SECONDS
    musicbrainz.configure()
    socket.setdefaulttimeout(MB_SOCKET_TIMEOUT)
    started_at = _time.monotonic()

    sessions = json.loads(RAW_SESSIONS_PATH.read_text(encoding="utf-8"))
    corpus = _load_corpus()
    done = set(corpus["tracks"]) | set(corpus["unresolvable"])

    # Enrich session by session so that partial progress yields *complete* sessions
    # rather than a scatter of half-resolved ones.
    pending: list[str] = []
    for session in sessions:
        for mbid in (*session["history"], session["target"]):
            if mbid not in done and mbid not in pending:
                pending.append(mbid)
        if len(pending) >= max_tracks:
            break

    logger.info(
        "%d tracks already known, %d to fetch (cap %d)", len(done), len(pending), max_tracks
    )

    for index, mbid in enumerate(pending, 1):
        try:
            metadata = await musicbrainz.get_recording(mbid)
        except ConnectionError as exc:
            logger.warning("MusicBrainz failed for %s: %s", mbid, exc)
            continue
        if metadata is None:
            corpus["unresolvable"].append(mbid)
        else:
            try:
                acoustic = await acousticbrainz.get_features(mbid)
            except ConnectionError:
                acoustic = None
            corpus["tracks"][mbid] = {**metadata, "acoustic": acoustic}

        if index % CHECKPOINT_EVERY == 0:
            _save_corpus(corpus)
            elapsed = _time.monotonic() - started_at
            rate = index / elapsed
            remaining = (len(pending) - index) / rate if rate else 0
            logger.info(
                "enriched %d/%d (%d resolved, %d unresolvable) — %.1f tracks/min, "
                "~%.0f min left",
                index, len(pending), len(corpus["tracks"]), len(corpus["unresolvable"]),
                rate * 60, remaining / 60,
            )

    _save_corpus(corpus)
    logger.info(
        "enrichment complete: %d tracks resolved, %d unresolvable",
        len(corpus["tracks"]), len(corpus["unresolvable"]),
    )


# ---------------------------------------------------------- phase: refresh-acoustics


async def phase_refresh_acoustics() -> None:
    """Re-derive every track's acoustic features from AcousticBrainz, in bulk.

    The corpus stores *parsed* acoustic features, so a change to the parser silently
    leaves it stale. That happened once already: the energy dimension was re-derived
    from the mood classifiers after the danceability proxy was found to be wrong, and
    every track harvested before that carried the old value. Because the bulk
    endpoints fetch 25 recordings per request, refreshing the whole corpus costs
    seconds rather than the hours a re-harvest would — so this runs as part of
    ``all`` and can be run on its own whenever the parser changes.
    """
    corpus = _load_corpus()
    mbids = sorted(corpus["tracks"])
    if not mbids:
        logger.info("corpus is empty; nothing to refresh")
        return

    refreshed = await acousticbrainz.get_features_bulk(mbids)
    changed = preserved = 0
    for mbid, acoustic in refreshed.items():
        existing = corpus["tracks"][mbid].get("acoustic")
        # A failed batch is indistinguishable from "no data" at this layer, so a
        # transient timeout would otherwise *delete* previously-good data — which is
        # exactly what happened on the first refresh run. AcousticBrainz is frozen, so
        # a record that existed does not legitimately vanish; keep it and say so.
        if acoustic is None and existing is not None:
            preserved += 1
            continue
        if existing != acoustic:
            changed += 1
        corpus["tracks"][mbid]["acoustic"] = acoustic

    _save_corpus(corpus)
    with_data = sum(1 for v in corpus["tracks"].values() if v.get("acoustic"))
    logger.info(
        "refreshed %d tracks (%d changed, %d preserved through a failed fetch); "
        "%d have acoustic data (%.1f%%)",
        len(mbids), changed, preserved, with_data, 100 * with_data / len(mbids),
    )


# ------------------------------------------------------------------ phase: finalise


async def phase_finalise() -> None:
    sessions = json.loads(RAW_SESSIONS_PATH.read_text(encoding="utf-8"))
    corpus = _load_corpus()
    tracks = corpus["tracks"]

    # A sequence the engine cannot be fed is not a fair test case; scoring it zero
    # would measure MusicBrainz coverage rather than recommendation quality.
    usable = [
        s
        for s in sessions
        if s["target"] in tracks and all(m in tracks for m in s["history"])
    ]
    logger.info("%d/%d sessions fully resolved", len(usable), len(sessions))

    artists = sorted(
        {
            tracks[m]["artist_mbid"]
            for s in usable
            for m in (*s["history"], s["target"])
            if tracks[m].get("artist_mbid")
        }
    )
    logger.info("fetching ListenBrainz similarity for %d artists", len(artists))
    for index, artist in enumerate(artists, 1):
        if artist in corpus["similar_artists"]:
            continue
        corpus["similar_artists"][artist] = await listenbrainz.get_similar_artists(artist)
        if index % 25 == 0:
            logger.info("similarity %d/%d", index, len(artists))

    _save_corpus(corpus)
    SESSIONS_PATH.write_text(json.dumps(usable, indent=1), encoding="utf-8")
    with_similarity = sum(1 for v in corpus["similar_artists"].values() if v)
    logger.info(
        "wrote %s (%d sessions); corpus: %d tracks, %d/%d artists with collaborative data",
        SESSIONS_PATH.name, len(usable), len(tracks), with_similarity, len(artists),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=["sessions", "enrich", "refresh-acoustics", "finalise", "all"],
        default="all",
        nargs="?",
    )
    parser.add_argument("--users", type=int, default=45)
    parser.add_argument("--sessions", type=int, default=150)
    parser.add_argument("--max-tracks", type=int, default=700)
    args = parser.parse_args()

    settings.MUSICBRAINZ_RATE_LIMIT_SECONDS = 1.0
    if args.phase in ("sessions", "all"):
        phase_sessions(args.users, args.sessions)
    if args.phase in ("enrich", "all"):
        asyncio.run(phase_enrich(args.max_tracks))
    if args.phase in ("refresh-acoustics", "all"):
        asyncio.run(phase_refresh_acoustics())
    if args.phase in ("finalise", "all"):
        asyncio.run(phase_finalise())
