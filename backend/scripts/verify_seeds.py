"""Validate every cold-start seed identifier against the live MusicBrainz API.

The seed identifiers in ``app/seeds.py`` were originally written by hand, and an audit
found that most of them did not resolve at all while two resolved to *entirely
different recordings* — the id labelled "Bohemian Rhapsody / Queen" returned Paranoid
Android by Radiohead. Because the runtime skips unresolvable ids gracefully, nothing
ever surfaced the problem; a mislabelled id is worse than a missing one, since it
seeds a session with another track's genre and acoustic profile.

This script makes that check repeatable. ``--check`` reports; ``--fix`` rewrites
``app/seeds.py`` with identifiers resolved from a fielded MusicBrainz query.

Usage:  python scripts/verify_seeds.py [--check | --fix]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import time

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.seeds import SEED_TRACKS  # noqa: E402

SEEDS_PATH = pathlib.Path(__file__).resolve().parents[1] / "app" / "seeds.py"
MB_URL = "https://musicbrainz.org/ws/2/recording"
HEADERS = {"User-Agent": "NextTrack/0.1 ( https://github.com/ )"}
RATE_LIMIT_SECONDS = 1.2


def _request(params: dict) -> dict | None:
    for attempt in range(4):
        time.sleep(RATE_LIMIT_SECONDS)
        try:
            resp = httpx.get(MB_URL, params=params, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
        except Exception as exc:  # noqa: BLE001
            print(f"  request failed ({attempt + 1}/4): {exc}")
        time.sleep(2 * (attempt + 1))
    return None


def lookup(mbid: str) -> tuple[str, str] | None:
    """Return (title, artist) for an MBID, or None if MusicBrainz has no such recording."""
    payload = _request({"query": f"rid:{mbid}", "fmt": "json", "limit": 1})
    recordings = (payload or {}).get("recordings") or []
    if not recordings:
        return None
    rec = recordings[0]
    return rec["title"], rec["artist-credit"][0]["artist"]["name"]


def resolve(title: str, artist: str) -> str | None:
    """Resolve a title/artist pair to the official recording's MBID."""
    query = f'recording:"{title}" AND artist:"{artist}"'
    payload = _request({"query": query, "fmt": "json", "limit": 1})
    recordings = (payload or {}).get("recordings") or []
    return recordings[0]["id"] if recordings else None


def check() -> list[tuple[str, str, str, str]]:
    """Return (mbid, title, artist, verdict) for every seed."""
    rows = []
    for mbid, title, artist in SEED_TRACKS:
        found = lookup(mbid)
        if found is None:
            verdict = "UNRESOLVABLE"
        elif title.lower() in found[0].lower():
            verdict = "OK"
        else:
            verdict = f"MISMATCH -> {found[0]} / {found[1]}"
        rows.append((mbid, title, artist, verdict))
        print(f"  {verdict:<40} {title} — {artist}")
    return rows


def fix() -> None:
    resolved: list[tuple[str, str, str]] = []
    for _mbid, title, artist in SEED_TRACKS:
        new_id = resolve(title, artist)
        print(f"  {new_id or 'NOT FOUND':<38} {title} — {artist}")
        if new_id:
            resolved.append((new_id, title, artist))

    source = SEEDS_PATH.read_text(encoding="utf-8")
    body = "\n".join(f'    ("{m}", "{t}", "{a}"),' for m, t, a in resolved)
    replacement = f"SEED_TRACKS: list[tuple[str, str, str]] = [\n{body}\n]\n"
    updated = re.sub(
        r"SEED_TRACKS: list\[tuple\[str, str, str\]\] = \[.*?\n\]\n",
        replacement,
        source,
        flags=re.DOTALL,
    )
    SEEDS_PATH.write_text(updated, encoding="utf-8")
    print(f"\nwrote {len(resolved)} verified seeds to {SEEDS_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="rewrite seeds.py with resolved ids")
    args = parser.parse_args()
    if args.fix:
        fix()
    else:
        rows = check()
        bad = [r for r in rows if r[3] != "OK"]
        print(f"\n{len(rows) - len(bad)}/{len(rows)} seeds valid")
        sys.exit(1 if bad else 0)
