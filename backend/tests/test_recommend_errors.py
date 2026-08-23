"""Regression tests for the machine-readable `reason` on failed recommendations.

Each /recommend failure path must return a 404 whose body carries both a string
`detail` (unchanged contract) and a specific `reason` code the frontend maps to
guidance. These guard against the original opaque "no recommendation could be
produced" message regressing.
"""

# A syntactically valid MBID that the mocked data layer does not know about.
UNKNOWN_MBID = "00000000-0000-0000-0000-000000000000"


def _assert_reason(resp, reason: str) -> None:
    assert resp.status_code == 404
    body = resp.json()
    assert body["reason"] == reason
    assert isinstance(body["detail"], str) and body["detail"]  # contract preserved


def test_no_history_resolved(client, mock_sources):
    """None of the supplied MBIDs resolve -> no_history_resolved."""
    resp = client.post("/api/v1/recommend", json={"track_history": [UNKNOWN_MBID]})
    _assert_reason(resp, "no_history_resolved")


def test_no_genres_for_history(client, mock_sources, seed_ids):
    """History resolves but carries no genres -> no_genres_for_history."""
    mock_sources.get_recording.side_effect = lambda mbid: {
        "mbid": mbid,
        "title": "Untagged",
        "artist": "Nobody",
        "album": None,
        "duration_seconds": 200,
        "genres": [],
    }
    resp = client.post("/api/v1/recommend", json={"track_history": [seed_ids.history]})
    _assert_reason(resp, "no_genres_for_history")


def test_no_candidates_found(client, mock_sources, seed_ids):
    """Every candidate is excluded by artist -> no_candidates_found.

    The fixture catalogue holds three artists (it gained Pearl Jam and Soundgarden
    when the collaborative stage was added, since artist-level co-listening cannot be
    exercised on a single-artist catalogue), so emptying the candidate pool means
    excluding all three.
    """
    resp = client.post(
        "/api/v1/recommend",
        json={
            "track_history": [seed_ids.history],
            "params": {"exclude_artists": ["Nirvana", "Pearl Jam", "Soundgarden"]},
        },
    )
    _assert_reason(resp, "no_candidates_found")


def test_no_candidates_after_filters(client, mock_sources, seed_ids):
    """All candidates fall outside the tempo range -> no_candidates_after_filters."""
    resp = client.post(
        "/api/v1/recommend",
        json={
            "track_history": [seed_ids.history],
            "params": {"tempo_range": [130, 200]},
        },
    )
    _assert_reason(resp, "no_candidates_after_filters")


def test_no_youtube_match(client, mock_sources, seed_ids):
    """Candidates found but none resolve to a video -> no_youtube_match."""
    mock_sources.search_video_id.side_effect = lambda _query: None
    resp = client.post("/api/v1/recommend", json={"track_history": [seed_ids.history]})
    _assert_reason(resp, "no_youtube_match")


def test_successful_recommend_has_no_reason(client, mock_sources, seed_ids):
    """The happy path returns 200 with a track and no error reason."""
    resp = client.post("/api/v1/recommend", json={"track_history": [seed_ids.history]})
    assert resp.status_code == 200
    assert "reason" not in resp.json()
