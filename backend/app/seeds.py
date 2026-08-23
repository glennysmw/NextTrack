"""Hand-picked, well-covered MBIDs spanning genres for cold-start.

Every identifier here is resolved from a fielded MusicBrainz query, not written by
hand: ``scripts/verify_seeds.py --check`` re-validates the whole list against the live
API, and ``--fix`` regenerates it. This is not ceremony. The original hand-written list
had ten unresolvable identifiers and two that pointed at *different recordings*
entirely — and because a wrong MBID is skipped gracefully at runtime, nothing ever
surfaced the problem, it just quietly seeded sessions with the wrong track's genre and
acoustic profile.
"""

SEED_TRACKS: list[tuple[str, str, str]] = [
    ("775bd63d-a8ec-4ac5-b6ac-56fa105eac62", "Smells Like Teen Spirit", "Nirvana"),
    ("46fe768c-7b38-4147-9f02-815b9f0759e2", "Bohemian Rhapsody", "Queen"),
    ("831af421-9489-4808-b41f-017dca910001", "Hotel California", "Eagles"),
    ("0dc754dd-9d72-4055-a4da-879e06380172", "Billie Jean", "Michael Jackson"),
    ("9b7e22ed-fa95-41bc-b8b3-decc21ad87ec", "Rolling in the Deep", "Adele"),
    ("ce46f2c8-4f20-4679-bd7b-1d78b544f6fb", "Strobe", "deadmau5"),
    ("d1c944a9-704e-4401-8f4c-c50625cfd3d6", "One More Time", "Daft Punk"),
    ("79090285-645c-4154-8f99-5f367173b3a8", "HUMBLE.", "Kendrick Lamar"),
    ("ad1b7371-089b-4288-b793-c2ed10855386", "So What", "Miles Davis"),
    ("0bcc04d8-e4da-4a7c-a1f5-532d20124bf3", "Clair de Lune", "Claude Debussy"),
    ("4d54703b-ff2f-47df-be33-5f7529b83cfc", "Skinny Love", "Bon Iver"),
    ("cdd611f4-f270-405b-910b-fddf60dff322", "Mr. Brightside", "The Killers"),
]
