import { useCallback, useRef, useState } from 'react';

import { describeError, getRecommendation } from '../api/nexttrack';
import { isMbid } from '../constants';
import type {
  HistoryEntry,
  Preferences,
  Recommendation,
  RecommendParams,
} from '../types';

export interface UseRecommendation {
  recommendation: Recommendation | null;
  loading: boolean;
  error: string | null;
  fetchNext: (history: HistoryEntry[], prefs: Preferences) => Promise<void>;
  nextAlternative: (history: HistoryEntry[], prefs: Preferences) => Promise<void>;
  clear: () => void;
}

// Owns the recommendation lifecycle: fetching for the current history and tracking
// which candidates the user has rejected via "next alternative".
export function useRecommendation(): UseRecommendation {
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recommendationRef = useRef<Recommendation | null>(null);
  const excludedRef = useRef<string[]>([]);
  // Monotonic id of the latest request; results from superseded requests are
  // discarded so a slow earlier fetch can't overwrite a newer one (double-click /
  // auto-advance races).
  const requestIdRef = useRef(0);

  const applyRecommendation = useCallback((rec: Recommendation | null) => {
    recommendationRef.current = rec;
    setRecommendation(rec);
  }, []);

  const run = useCallback(
    async (history: HistoryEntry[], prefs: Preferences) => {
      // Only tracks resolved to a MusicBrainz id can seed a recommendation; a played
      // track that wasn't found there still plays, it just can't be a basis here.
      const ids = history.map((entry) => entry.track_id).filter(isMbid);
      if (ids.length === 0) {
        if (history.length > 0) {
          setError(
            "We couldn't identify that track well enough to recommend a next one.",
          );
        }
        applyRecommendation(null);
        return;
      }
      const requestId = (requestIdRef.current += 1);
      setLoading(true);
      setError(null);
      try {
        const params: RecommendParams = {
          tempo_range: prefs.tempo_range,
          exclude_artists: prefs.exclude_artists,
          exclude_tracks: excludedRef.current,
        };
        const rec = await getRecommendation(ids, params);
        if (requestId !== requestIdRef.current) {
          return; // a newer request superseded this one
        }
        applyRecommendation(rec);
      } catch (err) {
        if (requestId !== requestIdRef.current) {
          return;
        }
        setError(describeError(err));
        applyRecommendation(null);
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [applyRecommendation],
  );

  const fetchNext = useCallback(
    (history: HistoryEntry[], prefs: Preferences) => {
      excludedRef.current = [];
      return run(history, prefs);
    },
    [run],
  );

  const nextAlternative = useCallback(
    (history: HistoryEntry[], prefs: Preferences) => {
      const current = recommendationRef.current;
      if (current) {
        excludedRef.current = [...excludedRef.current, current.track_id];
      }
      return run(history, prefs);
    },
    [run],
  );

  const clear = useCallback(() => {
    excludedRef.current = [];
    // Invalidate any in-flight request so its result can't land after a reset.
    requestIdRef.current += 1;
    setLoading(false);
    applyRecommendation(null);
    setError(null);
  }, [applyRecommendation]);

  return { recommendation, loading, error, fetchNext, nextAlternative, clear };
}
