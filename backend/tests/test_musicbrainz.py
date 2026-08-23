"""Regression tests for MusicBrainz genre enrichment.

Root-cause coverage for the "no recommendation could be produced" bug: recording-
level folksonomy tags are almost always empty in MusicBrainz, so the recommender
got no genres and bailed out. Genres are now sourced from the *artist*; these tests
exercise the synchronous core directly (mocking the musicbrainzngs library calls),
which the higher-level fixtures deliberately bypass.
"""
from unittest.mock import patch

from app.data import musicbrainz


def _recording(tag_names: list[str]) -> dict:
    return {
        "recording": {
            "id": "rec-1",
            "title": "Some Song",
            "length": "200000",
            "artist-credit": [{"artist": {"id": "artist-1", "name": "Some Band"}}],
            "release-list": [{"title": "Some Album"}],
            "tag-list": [{"name": n} for n in tag_names],
        }
    }


def _artist(tags: list[dict]) -> dict:
    return {"artist": {"id": "artist-1", "name": "Some Band", "tag-list": tags}}


def test_recording_genres_enriched_from_artist_when_recording_has_none():
    """The core fix: empty recording tags -> genres come from the artist (filtered)."""
    musicbrainz.clear_artist_cache()
    artist_tags = [
        {"name": "grunge", "count": "10"},
        {"name": "alternative rock", "count": "8"},
        {"name": "seattle", "count": "5"},  # place -> filtered out
        {"name": "90s", "count": "4"},  # decade -> filtered out
    ]
    with patch("musicbrainzngs.get_recording_by_id", return_value=_recording([])), patch(
        "musicbrainzngs.get_artist_by_id", return_value=_artist(artist_tags)
    ):
        parsed = musicbrainz._get_recording_sync("rec-1")

    # Only real genres survive, ranked by tag count.
    assert parsed["genres"] == ["grunge", "alternative rock"]


def test_recording_tags_take_precedence_then_artist_tags_appended():
    """Recording-level genres lead; artist genres are merged after and de-duplicated."""
    musicbrainz.clear_artist_cache()
    artist_tags = [{"name": "grunge", "count": "10"}, {"name": "indie", "count": "9"}]
    with patch(
        "musicbrainzngs.get_recording_by_id", return_value=_recording(["indie"])
    ), patch("musicbrainzngs.get_artist_by_id", return_value=_artist(artist_tags)):
        parsed = musicbrainz._get_recording_sync("rec-1")

    assert parsed["genres"][0] == "indie"  # recording tag first
    assert "grunge" in parsed["genres"]  # artist tag merged in
    assert parsed["genres"].count("indie") == 1  # no duplicate


def test_artist_genres_are_cached_per_artist():
    """The artist lookup is cached, so repeated tracks don't re-hit the rate limit."""
    musicbrainz.clear_artist_cache()
    artist_tags = [{"name": "grunge", "count": "10"}]
    with patch(
        "musicbrainzngs.get_artist_by_id", return_value=_artist(artist_tags)
    ) as mock_get_artist:
        first = musicbrainz._artist_genres_sync("artist-1")
        second = musicbrainz._artist_genres_sync("artist-1")

    assert first == second == ["grunge"]
    assert mock_get_artist.call_count == 1  # second call served from cache


def test_artist_lookup_failure_degrades_to_no_genres():
    """A failed artist lookup is best-effort: it must not raise, just yield nothing."""
    musicbrainz.clear_artist_cache()
    with patch(
        "musicbrainzngs.get_artist_by_id", side_effect=Exception("boom")
    ):
        assert musicbrainz._artist_genres_sync("artist-1") == []


def test_artist_genre_count_is_capped():
    """No more than _MAX_ARTIST_GENRES genres are kept, highest-count first."""
    musicbrainz.clear_artist_cache()
    artist_tags = [
        {"name": f"genre-{i}", "count": str(20 - i)} for i in range(10)
    ]
    with patch("musicbrainzngs.get_artist_by_id", return_value=_artist(artist_tags)):
        genres = musicbrainz._artist_genres_sync("artist-1")

    assert genres == [f"genre-{i}" for i in range(musicbrainz._MAX_ARTIST_GENRES)]
