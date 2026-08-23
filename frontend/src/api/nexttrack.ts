// Thin API client. In demo mode every call resolves from local mock data so the
// app runs offline and without burning YouTube quota.
import axios from 'axios';

import { API_URL, DEMO_MODE } from '../constants';
import {
  MOCK_HEALTH,
  MOCK_SEARCH_RESULTS,
  nextMockRecommendation,
  resolveMockTrack,
} from '../mockData';
import type {
  HealthStatus,
  Recommendation,
  RecommendParams,
  SearchResult,
} from '../types';

const client = axios.create({ baseURL: API_URL, timeout: 15000 });

// Recommendations fan out to MusicBrainz (rate-limited to 1 req/sec), so a cold-cache
// request can run well past the default timeout. Give it dedicated headroom.
const RECOMMEND_TIMEOUT_MS = 45000;

export async function searchTracks(
  query: string,
  limit = 10,
  artist?: string,
): Promise<SearchResult[]> {
  if (DEMO_MODE) {
    return MOCK_SEARCH_RESULTS;
  }
  const { data } = await client.post('/search', { query, limit, artist });
  return data.results;
}

// Today's Top 5 — a daily-rotating set of popular tracks for the home screen.
export async function getTopTracks(): Promise<SearchResult[]> {
  if (DEMO_MODE) {
    return MOCK_SEARCH_RESULTS;
  }
  const { data } = await client.get('/top');
  return data.results;
}

// Map a played track (title + artist) to its MusicBrainz id, needed before we can
// ask for a recommendation. Returns null when the track isn't in MusicBrainz.
export async function resolveTrack(
  title: string,
  artist: string,
): Promise<string | null> {
  if (DEMO_MODE) {
    return resolveMockTrack(title, artist);
  }
  const { data } = await client.post('/resolve', { title, artist });
  return data.track_id ?? null;
}

export async function getRecommendation(
  trackHistory: string[],
  params: RecommendParams,
): Promise<Recommendation> {
  if (DEMO_MODE) {
    return nextMockRecommendation(trackHistory, params.exclude_tracks);
  }
  const { data } = await client.post(
    '/recommend',
    { track_history: trackHistory, params },
    { timeout: RECOMMEND_TIMEOUT_MS },
  );
  return data;
}

export async function getHealth(): Promise<HealthStatus> {
  if (DEMO_MODE) {
    return MOCK_HEALTH;
  }
  const { data } = await client.get('/health');
  return data;
}

// Maps a backend `reason` code (from a failed /recommend) to user-facing guidance.
// Falls back to the server's `detail` string for codes we don't special-case.
const REASON_MESSAGES: Record<string, string> = {
  no_history_resolved:
    "We couldn't identify any of your played tracks. Try searching and playing a different song.",
  no_genres_for_history:
    "We don't have enough genre information about what you've played to recommend a next track.",
  no_candidates_found:
    'No related tracks were found for this listening history. Try a different song or relax your exclusions.',
  no_candidates_after_filters:
    'No tracks matched your tempo range. Widen the tempo slider and try again.',
  no_youtube_match:
    'We found a recommendation but no playable video for it. Try the next alternative.',
};

// Turn any thrown error into a short, user-facing message.
export function describeError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const reason = error.response?.data?.reason;
    if (typeof reason === 'string' && reason in REASON_MESSAGES) {
      return REASON_MESSAGES[reason];
    }
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    if (error.code === 'ERR_NETWORK') {
      return 'Cannot reach the NextTrack server. Is the backend running?';
    }
    return error.message;
  }
  return 'Something went wrong.';
}
