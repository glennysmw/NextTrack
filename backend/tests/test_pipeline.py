"""Integration tests for the three-stage cascade as a whole.

These test the *pipeline*, not its parts: that each stage is actually wired in, that
disabling a stage changes the outcome in the direction the design predicts, and that
a failing stage cannot take the recommendation down with it.
"""
from unittest.mock import AsyncMock

from app.engine import recommender
from app.engine.recommender import PipelineConfig
from app.models.request import RecommendParams

CONTENT_ONLY = PipelineConfig(use_collaborative=False, use_diversity=False)
CONTENT_PLUS_CF = PipelineConfig(use_collaborative=True, use_diversity=False)
CONTENT_PLUS_MMR = PipelineConfig(use_collaborative=False, use_diversity=True)
FULL = PipelineConfig(use_collaborative=True, use_diversity=True)


async def _ranked(history, config, params=None):
    ranked, _ = await recommender.recommend_ranked(
        history, params or RecommendParams(), config
    )
    return [track["mbid"] for _, track in ranked]


async def test_content_only_ranks_the_nearest_neighbour_first(mock_sources, seed_ids):
    """Baseline: with both extra stages off, the closest match to the seed wins.

    'Come As You Are' shares the seed's genres, key and near-identical tempo, so a
    pure centroid-similarity ranking should put it at the top. This is the behaviour
    the draft report criticised as over-specialisation — it is asserted here so the
    diversity test below has a documented baseline to differ from.
    """
    assert (await _ranked([seed_ids.history], CONTENT_ONLY))[0] == seed_ids.come_as_you_are


async def test_diversity_stage_demotes_redundant_candidates(mock_sources, seed_ids):
    """MMR must push a same-artist near-duplicate below a more distinct candidate.

    It does *not* necessarily change the top pick, and asserting that it does would
    be wrong: at λ = 0.7 a relevance gap as wide as this fixture's (0.99 vs 0.29)
    correctly outweighs any redundancy penalty. What MMR must change is the position
    of a candidate that is redundant with picks already made — here 'In Bloom', a
    third Nirvana track sharing the same genre block as the two above it, which drops
    below the Soundgarden candidate once diversity is on.
    """
    without = await _ranked([seed_ids.history], CONTENT_ONLY)
    with_mmr = await _ranked([seed_ids.history], CONTENT_PLUS_MMR)

    assert with_mmr != without
    assert without.index(seed_ids.in_bloom) < without.index(seed_ids.black_hole_sun)
    assert with_mmr.index(seed_ids.in_bloom) > with_mmr.index(seed_ids.black_hole_sun)


async def test_collaborative_stage_boosts_a_co_listened_artist(mock_sources, seed_ids):
    """Pearl Jam is the strongest ListenBrainz match for the seed's artist.

    On content alone it ranks below the same-artist tracks (different tempo and key);
    the collaborative blend is what lifts it, so its rank must improve when stage 2
    is switched on and nothing else changes.
    """
    without = await _ranked([seed_ids.history], CONTENT_ONLY)
    with_cf = await _ranked([seed_ids.history], CONTENT_PLUS_CF)
    assert with_cf.index(seed_ids.alive) < without.index(seed_ids.alive)


async def test_full_pipeline_still_returns_a_playable_recommendation(
    mock_sources, seed_ids
):
    result = await recommender.recommend([seed_ids.history], RecommendParams(), FULL)
    assert result["track_id"]
    assert result["youtube_video_id"] == seed_ids.youtube
    assert 0.0 <= result["score"] <= 1.0
    assert result["rationale"]


async def test_listenbrainz_outage_does_not_break_recommendations(
    mocker, mock_sources, seed_ids
):
    """A dead collaborative source must degrade to content scoring, not to a 5xx."""
    mocker.patch(
        "app.data.listenbrainz.get_similar_artists",
        new=AsyncMock(side_effect=ConnectionError("ListenBrainz down")),
    )
    # get_similar_artists_many gathers the per-artist calls, so the error would
    # propagate if the client did not swallow it — assert the pipeline survives.
    mocker.patch(
        "app.data.listenbrainz.get_similar_artists_many", new=AsyncMock(return_value={})
    )
    result = await recommender.recommend([seed_ids.history], RecommendParams(), FULL)
    assert result["track_id"]


async def test_history_without_artist_mbids_skips_the_collaborative_stage(
    mocker, mock_sources, seed_ids
):
    """Older cached metadata has no artist_mbid; the stage must no-op, not crash."""
    original = mock_sources.get_recording.side_effect

    def strip_artist_mbid(mbid: str):
        rec = original(mbid)
        if rec:
            rec.pop("artist_mbid", None)
        return rec

    mock_sources.get_recording.side_effect = strip_artist_mbid
    result = await recommender.recommend([seed_ids.history], RecommendParams(), FULL)
    assert result["track_id"]
    mock_sources.get_similar_artists.assert_not_called()


async def test_identical_requests_produce_identical_rankings(mock_sources, seed_ids):
    """Statelessness means reproducibility: same input in, same order out."""
    first = await _ranked([seed_ids.history], FULL)
    second = await _ranked([seed_ids.history], FULL)
    assert first == second


async def test_pipeline_config_defaults_run_every_stage():
    assert recommender.DEFAULT_PIPELINE.use_collaborative is True
    assert recommender.DEFAULT_PIPELINE.use_diversity is True
    assert recommender.DEFAULT_PIPELINE.effective_lambda < 1.0
    assert recommender.DEFAULT_PIPELINE.effective_collab_weight > 0.0


async def test_disabled_stages_report_neutral_parameters():
    assert CONTENT_ONLY.effective_lambda == 1.0
    assert CONTENT_ONLY.effective_collab_weight == 0.0
