"""Today's Top 5 — a daily-rotating set of popular tracks for the home screen.

Unauthenticated YouTube Music does not expose a reliable songs *chart*, so rather
than scrape a fragile internal endpoint we rotate a hand-curated pool of well-known
hits. The selection is seeded by the calendar date, so it is stable within a day and
changes at midnight (UTC) — "Today's Top 5". Each entry is resolved to its official
track (art, video id) via YouTube Music at request time.
"""
import datetime
import random

# (title, artist) — broad, evergreen popularity so YouTube Music always resolves an
# official track. Order here is irrelevant; the daily seed shuffles it.
TOP_POOL: list[tuple[str, str]] = [
    ("Blinding Lights", "The Weeknd"),
    ("Flowers", "Miley Cyrus"),
    ("As It Was", "Harry Styles"),
    ("Anti-Hero", "Taylor Swift"),
    ("Espresso", "Sabrina Carpenter"),
    ("Levitating", "Dua Lipa"),
    ("Shape of You", "Ed Sheeran"),
    ("Uptown Funk", "Mark Ronson"),
    ("HUMBLE.", "Kendrick Lamar"),
    ("Rolling in the Deep", "Adele"),
    ("Bohemian Rhapsody", "Queen"),
    ("Mr. Brightside", "The Killers"),
    ("Smells Like Teen Spirit", "Nirvana"),
    ("Billie Jean", "Michael Jackson"),
    ("Sunflower", "Post Malone"),
    ("Watermelon Sugar", "Harry Styles"),
    ("Stay", "The Kid LAROI"),
    ("Heat Waves", "Glass Animals"),
    ("good 4 u", "Olivia Rodrigo"),
    ("Bad Guy", "Billie Eilish"),
    ("Believer", "Imagine Dragons"),
    ("Counting Stars", "OneRepublic"),
    ("Shake It Off", "Taylor Swift"),
    ("Royals", "Lorde"),
    ("One More Time", "Daft Punk"),
    ("Take On Me", "a-ha"),
    ("Africa", "Toto"),
    ("Wonderwall", "Oasis"),
    ("Seven Nation Army", "The White Stripes"),
    ("Lose Yourself", "Eminem"),
    ("SICKO MODE", "Travis Scott"),
    ("God's Plan", "Drake"),
    ("Cruel Summer", "Taylor Swift"),
    ("Don't Start Now", "Dua Lipa"),
    ("Hotel California", "Eagles"),
    ("Viva La Vida", "Coldplay"),
]


def todays_picks(n: int = 5) -> list[tuple[str, str]]:
    """Return `n` (title, artist) pairs for today, stable within the UTC day."""
    day_seed = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    rng = random.Random(day_seed)
    return rng.sample(TOP_POOL, min(n, len(TOP_POOL)))
