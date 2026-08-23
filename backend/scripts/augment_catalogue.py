"""Snapshot the real candidate-retrieval stage into the evaluation corpus.

Without this, ``offline_eval.py`` would rank each held-out track against a catalogue
built *only* from the evaluation sessions themselves — a pool of a few hundred tracks
that other listeners in the sample happened to play. Retrieval recall would be 1.0 by
construction and every accuracy figure would be inflated, because the engine would
never face the obscure, weakly-tagged recordings that a live MusicBrainz tag search
actually returns.

This script therefore replays the live retrieval stage once and stores the result: for
every genre tag the engine would search on (the top three genres of each session's
history), it records MusicBrainz's real ``search_by_tag`` response, in MusicBrainz's
real order, and fetches the acoustic descriptors for those candidates. The evaluation
then replays those responses verbatim, so the engine ranks the held-out track against
exactly the pool it would have retrieved in production — while staying deterministic
and offline.

Usage:  python scripts/augment_catalogue.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.data import acousticbrainz, musicbrainz  # noqa: E402
from app.engine import recommender  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("augment_catalogue")

BACKEND = pathlib.Path(__file__).resolve().parents[1]
CORPUS_PATH = BACKEND / "data" / "eval_corpus.json"
SESSIONS_PATH = BACKEND / "data" / "eval_sessions.json"

# MusicBrainz throttles sustained requests at exactly 1 req/sec; pacing slightly under
# the limit avoids 503-and-retry cycles that cost far more than the headroom.
MB_INTERVAL_SECONDS = 1.3


def search_tags(corpus: dict, sessions: list[dict]) -> list[str]:
    """The genre tags the engine would actually search on, across all sessions."""
    tracks = corpus["tracks"]
    tags: dict[str, None] = {}
    for session in sessions:
        history = [tracks[m] for m in session["history"] if m in tracks]
        for genre in recommender._top_genres(history, recommender._TOP_GENRE_TAGS):
            tags.setdefault(genre, None)
    return list(tags)


async def fetch_acoustics(mbids: list[str]) -> dict[str, dict | None]:
    """Fetch acoustic descriptors for every candidate through the bulk endpoints.

    Per-track fetching would be two requests per candidate — thousands of round trips
    for a catalogue this size. ``get_features_bulk`` batches 25 recordings per request
    and never raises, so a missing record and an outage are handled alike.
    """
    chunk = 500
    out: dict[str, dict | None] = {}
    for start in range(0, len(mbids), chunk):
        out.update(await acousticbrainz.get_features_bulk(mbids[start : start + chunk]))
        logger.info("acoustic %d/%d", min(start + chunk, len(mbids)), len(mbids))
    return out


async def main() -> None:
    settings.MUSICBRAINZ_RATE_LIMIT_SECONDS = MB_INTERVAL_SECONDS
    musicbrainz.configure()
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    sessions = json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))

    tags = search_tags(corpus, sessions)
    logger.info("%d distinct search tags across %d sessions", len(tags), len(sessions))

    tag_search: dict[str, list[str]] = {}
    new_tracks: dict[str, dict] = {}
    for index, tag in enumerate(tags, 1):
        try:
            results = await musicbrainz.search_by_tag(tag, settings.CANDIDATE_POOL_SIZE)
        except ConnectionError as exc:
            logger.warning("tag search failed for %r: %s", tag, exc)
            continue
        ordered: list[str] = []
        for rec in results:
            mbid = rec.get("mbid")
            if not mbid:
                continue
            ordered.append(mbid)
            if mbid not in corpus["tracks"] and mbid not in new_tracks:
                # Candidates keep exactly the metadata the live pipeline sees: the
                # search response's own tags, with no per-artist tag enrichment (the
                # engine does not spend a lookup per candidate either).
                new_tracks[mbid] = {**rec, "acoustic": None, "source": "tag_search"}
        tag_search[tag] = ordered
        if index % 10 == 0:
            logger.info("searched %d/%d tags (%d new tracks)", index, len(tags), len(new_tracks))

    logger.info("fetching acoustics for %d new candidate tracks", len(new_tracks))
    acoustics = await fetch_acoustics(sorted(new_tracks))
    covered = 0
    for mbid, acoustic in acoustics.items():
        new_tracks[mbid]["acoustic"] = acoustic
        covered += acoustic is not None

    corpus["tracks"].update(new_tracks)
    corpus["tag_search"] = tag_search
    corpus["acoustic_coverage"] = {
        "candidates_with_data": covered,
        "candidates_total": len(new_tracks),
    }
    CORPUS_PATH.write_text(json.dumps(corpus, indent=1), encoding="utf-8")
    logger.info(
        "catalogue now %d tracks (%d added); acoustic coverage on candidates %d/%d",
        len(corpus["tracks"]),
        len(new_tracks),
        covered,
        len(new_tracks),
    )


if __name__ == "__main__":
    asyncio.run(main())
