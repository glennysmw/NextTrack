"""Endpoint tests for search, recommend, and health."""


def test_recommend_valid_request_returns_200(client, mock_sources, seed_ids):
    resp = client.post("/api/v1/recommend", json={"track_history": [seed_ids.history]})
    assert resp.status_code == 200

    body = resp.json()
    assert body["track_id"]
    assert 0.0 <= body["score"] <= 1.0
    assert body["rationale"]
    assert body["youtube_video_id"] == seed_ids.youtube
    assert set(body["features"]) == {"tempo", "key", "energy", "genres"}


def test_recommend_empty_history_returns_400(client, mock_sources):
    resp = client.post("/api/v1/recommend", json={"track_history": []})
    assert resp.status_code == 400


def test_recommend_too_many_tracks_returns_400(client, mock_sources, seed_ids):
    resp = client.post(
        "/api/v1/recommend", json={"track_history": [seed_ids.history] * 21}
    )
    assert resp.status_code == 400


def test_recommend_invalid_mbid_returns_400(client, mock_sources):
    resp = client.post("/api/v1/recommend", json={"track_history": ["not-a-real-mbid"]})
    assert resp.status_code == 400


def test_recommend_exclude_tracks_param_works(client, mock_sources, seed_ids):
    resp = client.post(
        "/api/v1/recommend",
        json={
            "track_history": [seed_ids.history],
            "params": {"exclude_tracks": [seed_ids.come_as_you_are]},
        },
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["track_id"] != seed_ids.come_as_you_are
    assert body["track_id"] in {seed_ids.lithium, seed_ids.in_bloom}


def test_search_returns_results(client, mock_sources, seed_ids):
    resp = client.post("/api/v1/search", json={"query": "smells like teen spirit"})
    assert resp.status_code == 200

    results = resp.json()["results"]
    assert len(results) >= 1
    assert results[0]["youtube_video_id"] == seed_ids.youtube


def test_search_empty_query_returns_400(client, mock_sources):
    resp = client.post("/api/v1/search", json={"query": "   "})
    assert resp.status_code == 400


def test_search_results_carry_album_art(client, mock_sources, seed_ids):
    resp = client.post("/api/v1/search", json={"query": "test"})
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["thumbnail"]
    # track_id is the YouTube video id (MBID is resolved lazily on play).
    assert result["track_id"] == seed_ids.youtube


def test_top_returns_five_tracks_with_art(client, mock_sources):
    resp = client.get("/api/v1/top")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 5
    assert all(r["thumbnail"] and r["youtube_video_id"] for r in results)


def test_resolve_maps_title_artist_to_mbid(client, mock_sources):
    resp = client.post(
        "/api/v1/resolve", json={"title": "Smells Like Teen Spirit", "artist": "Nirvana"}
    )
    assert resp.status_code == 200
    # The mocked MusicBrainz search yields a recording, so an MBID comes back.
    assert resp.json()["track_id"]


def test_health_returns_ok(client, mock_sources):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["sources"]["musicbrainz"] == "ok"
    assert "feature_size" in body["cache"]


# --- Regression: validated value vs. used value ----------------------------------
# `is_valid_mbid` strips before matching, so a padded identifier passed validation —
# but the *unstripped* value was then handed to the MusicBrainz client, which retried
# eight times and failed with "URL can't contain control characters", surfacing as a
# 503 "MusicBrainz unavailable". A client input problem reported slowly, as a server
# fault. Found by an adversarial input sweep against the live API.


def test_padded_mbid_is_normalised_rather_than_reaching_the_client(
    client, mock_sources, seed_ids
):
    resp = client.post(
        "/api/v1/recommend", json={"track_history": [f"  {seed_ids.history}  "]}
    )
    assert resp.status_code == 200
    mock_sources.get_recording.assert_any_call(seed_ids.history)


def test_uppercase_mbid_is_normalised_to_lower_case(client, mock_sources, seed_ids):
    resp = client.post(
        "/api/v1/recommend", json={"track_history": [seed_ids.history.upper()]}
    )
    assert resp.status_code == 200
    mock_sources.get_recording.assert_any_call(seed_ids.history)


def test_genuinely_malformed_mbid_is_still_rejected(client, mock_sources):
    resp = client.post("/api/v1/recommend", json={"track_history": ["  not-an-mbid  "]})
    assert resp.status_code == 400
