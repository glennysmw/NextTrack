import { useCallback, useEffect, useRef, useState } from 'react';

import {
  describeError,
  getTopTracks,
  resolveTrack,
  searchTracks,
} from './api/nexttrack';
import { Header } from './components/Header';
import { HistoryList } from './components/HistoryList';
import { Player } from './components/Player';
import { PreferenceControls } from './components/PreferenceControls';
import { RecommendationCard } from './components/RecommendationCard';
import { SearchBar } from './components/SearchBar';
import { SearchResults } from './components/SearchResults';
import { TopTracks } from './components/TopTracks';
import {
  DEFAULT_PREFERENCES,
  DEMO_MODE,
  isMbid,
  MAX_FEEDBACK_EVENTS,
  STORAGE_KEYS,
} from './constants';
import { useLocalStorageState } from './hooks/useLocalStorageState';
import { useRecommendation } from './hooks/useRecommendation';
import type {
  FeedbackEvent,
  FeedbackRating,
  HistoryEntry,
  Preferences,
  Recommendation,
  SearchResult,
} from './types';

function toHistoryEntry(track: SearchResult | Recommendation): HistoryEntry {
  return {
    track_id: track.track_id,
    title: track.title,
    artist: track.artist,
    youtube_video_id: track.youtube_video_id,
  };
}

// Structural guards for persisted state — reject stale-schema or tampered data so
// hydration falls back to defaults instead of crashing on a wrong shape.
const isHistoryEntryLike = (v: unknown): boolean =>
  typeof v === 'object' &&
  v !== null &&
  typeof (v as Record<string, unknown>).track_id === 'string' &&
  typeof (v as Record<string, unknown>).youtube_video_id === 'string';

const isCurrentTrack = (v: unknown): boolean => v === null || isHistoryEntryLike(v);

const isPreferences = (v: unknown): boolean => {
  if (typeof v !== 'object' || v === null) {
    return false;
  }
  const p = v as Record<string, unknown>;
  return (
    Array.isArray(p.tempo_range) &&
    p.tempo_range.length === 2 &&
    p.tempo_range.every((n) => typeof n === 'number') &&
    Array.isArray(p.exclude_artists) &&
    typeof p.auto_advance === 'boolean'
  );
};

export default function App() {
  const [history, setHistory, resetHistory] = useLocalStorageState<HistoryEntry[]>(
    STORAGE_KEYS.history,
    [],
    Array.isArray,
  );
  const [currentTrack, setCurrentTrack, resetCurrent] =
    useLocalStorageState<HistoryEntry | null>(
      STORAGE_KEYS.currentTrack,
      null,
      isCurrentTrack,
    );
  const [preferences, setPreferences, resetPreferences] =
    useLocalStorageState<Preferences>(
      STORAGE_KEYS.preferences,
      DEFAULT_PREFERENCES,
      isPreferences,
    );
  const [feedback, setFeedback, resetFeedback] = useLocalStorageState<FeedbackEvent[]>(
    STORAGE_KEYS.feedback,
    [],
    Array.isArray,
  );

  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [topTracks, setTopTracks] = useState<SearchResult[]>([]);
  const [topLoading, setTopLoading] = useState(true);

  const recommendation = useRecommendation();

  // Load Today's Top 5 once on mount.
  useEffect(() => {
    let active = true;
    getTopTracks()
      .then((tracks) => active && setTopTracks(tracks))
      .catch(() => active && setTopTracks([]))
      .finally(() => active && setTopLoading(false));
    return () => {
      active = false;
    };
  }, []);

  // Play a track: start playback immediately, resolve its MusicBrainz id (search /
  // Top-5 tracks only carry a YouTube id), record it, then fetch the next track.
  //
  // The resolve call is wrapped because it is the one step here that can reject: a
  // MusicBrainz outage surfaces as a 503, and letting that propagate would abandon
  // the whole function — the track would play but never enter the setlist, and the
  // rejection would surface only as an unhandled promise in the console. Treating a
  // failed resolve as "unresolved" keeps playback and history working; the track
  // simply cannot seed a recommendation, which useRecommendation already explains.
  const playTrack = useCallback(
    async (track: HistoryEntry) => {
      setCurrentTrack(track);
      let mbid: string | null = isMbid(track.track_id) ? track.track_id : null;
      if (mbid === null) {
        try {
          mbid = await resolveTrack(track.title, track.artist);
        } catch {
          mbid = null;
        }
      }
      const entry: HistoryEntry = { ...track, track_id: mbid ?? '' };
      const nextHistory = [...history, entry];
      setHistory(nextHistory);
      recommendation.fetchNext(nextHistory, preferences);
    },
    [history, preferences, recommendation, setHistory, setCurrentTrack],
  );

  const playRecommendation = useCallback(() => {
    if (recommendation.recommendation) {
      playTrack(toHistoryEntry(recommendation.recommendation));
    }
  }, [playTrack, recommendation.recommendation]);

  // Radio mode: when a track ends, auto-play the current recommendation. A ref keeps
  // the handler current regardless of the embedded player's handler caching.
  const onEndRef = useRef<() => void>(() => {});
  onEndRef.current = () => {
    if (preferences.auto_advance) {
      playRecommendation();
    }
  };
  const handleTrackEnd = useCallback(() => onEndRef.current(), []);

  // Resume a persisted session once on mount.
  const resumed = useRef(false);
  useEffect(() => {
    if (resumed.current) {
      return;
    }
    resumed.current = true;
    if (history.length > 0) {
      recommendation.fetchNext(history, preferences);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = async (query: string) => {
    setSearchLoading(true);
    setSearchError(null);
    try {
      setSearchResults(await searchTracks(query));
    } catch (err) {
      setSearchError(describeError(err));
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  };

  // Clearing the search box returns the home view to Today's Top 5.
  const clearSearch = useCallback(() => {
    setSearchResults([]);
    setSearchError(null);
  }, []);

  const addFeedback = (rating: FeedbackRating) => {
    if (!recommendation.recommendation) {
      return;
    }
    const event: FeedbackEvent = {
      track_id: recommendation.recommendation.track_id,
      recommended_at: new Date().toISOString(),
      rating,
      history_snapshot: history.map((entry) => entry.track_id),
    };
    // Keep only the most recent events so the log can't grow past the quota.
    setFeedback([...feedback, event].slice(-MAX_FEEDBACK_EVENTS));
  };

  const handleReset = () => {
    resetHistory();
    resetCurrent();
    resetPreferences();
    resetFeedback();
    recommendation.clear();
    setSearchResults([]);
    setSearchError(null);
  };

  return (
    <div className="flex min-h-full flex-col">
      {DEMO_MODE && (
        <div className="border-b border-ink bg-amber py-1 text-center font-mono text-label font-bold uppercase text-on-accent">
          Demo mode — mocked data, no live API calls
        </div>
      )}

      <Header onReset={handleReset} />

      <main className="mx-auto w-full max-w-6xl flex-1 space-y-8 px-6 py-8 sm:px-8">
        <SearchBar
          onSearch={handleSearch}
          onClear={clearSearch}
          loading={searchLoading}
        />

        {searchError && (
          <div className="border border-rust bg-rust/10 p-3 text-rust-ink">
            {searchError}
          </div>
        )}

        {searchResults.length > 0 ? (
          <SearchResults
            results={searchResults}
            onPlay={(result) => playTrack(toHistoryEntry(result))}
          />
        ) : (
          <TopTracks
            tracks={topTracks}
            loading={topLoading}
            onPlay={(track) => playTrack(toHistoryEntry(track))}
          />
        )}

        {/* Editorial split: a wide deck column and a narrower shelf, divided by a
            hairline rather than a gutter of shadow. */}
        {currentTrack && (
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1.35fr_1fr] lg:gap-0">
            <div className="space-y-8 lg:pr-8">
              <Player track={currentTrack} onEnd={handleTrackEnd} />
              <HistoryList history={history} />
            </div>
            <div className="lg:border-l lg:border-rule lg:pl-8">
              <RecommendationCard
                recommendation={recommendation.recommendation}
                loading={recommendation.loading}
                error={recommendation.error}
                onPlayNext={playRecommendation}
                onNextAlternative={() =>
                  recommendation.nextAlternative(history, preferences)
                }
                onFeedback={addFeedback}
              />
            </div>
          </div>
        )}

        <PreferenceControls preferences={preferences} onChange={setPreferences} />
      </main>
    </div>
  );
}
