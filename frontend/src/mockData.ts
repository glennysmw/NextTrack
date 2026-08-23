// Deterministic offline data used when VITE_DEMO_MODE=true.
// YouTube IDs are real so playback still works without the backend.
//
// The track ids are *real MusicBrainz identifiers*, not placeholder strings. That is
// load-bearing, not cosmetic: the app routes a played track through `isMbid()` before
// it can seed a recommendation, so the earlier `mock-0001-teen-spirit` style ids
// failed that check and demo mode silently degraded to "we couldn't identify that
// track" for every search or Top-5 play. Using genuine MBIDs keeps demo mode on
// exactly the same code path as live mode.
import type { HealthStatus, Recommendation, SearchResult } from './types';

export const MOCK_SEARCH_RESULTS: SearchResult[] = [
  {
    track_id: '6fd45825-5e07-48b7-801c-433c48d3262e',
    title: 'Smells Like Teen Spirit',
    artist: 'Nirvana',
    album: 'Nevermind',
    youtube_video_id: 'hTWKbfoikeg',
    duration_seconds: 301,
  },
  {
    track_id: 'dec86327-b468-4250-a36e-7c906786da84',
    title: 'Come As You Are',
    artist: 'Nirvana',
    album: 'Nevermind',
    youtube_video_id: 'vabnZ9-ex7o',
    duration_seconds: 219,
  },
  {
    track_id: 'cdd611f4-f270-405b-910b-fddf60dff322',
    title: 'Mr. Brightside',
    artist: 'The Killers',
    album: 'Hot Fuss',
    youtube_video_id: 'gGdGFtwCNBE',
    duration_seconds: 222,
  },
  {
    track_id: '5cf87954-1402-45f0-bbcf-e957eb332da7',
    title: 'Bohemian Rhapsody',
    artist: 'Queen',
    album: 'A Night at the Opera',
    youtube_video_id: 'fJ9rUzIMcZQ',
    duration_seconds: 354,
  },
  {
    track_id: 'ee3facfc-969c-4157-920d-e9af39e65406',
    title: 'Billie Jean',
    artist: 'Michael Jackson',
    album: 'Thriller',
    youtube_video_id: 'Zi_XLOBDo_Y',
    duration_seconds: 294,
  },
];

// A fixed sequence the demo cycles through so runs are reproducible.
export const MOCK_RECOMMENDATIONS: Recommendation[] = [
  {
    track_id: 'dec86327-b468-4250-a36e-7c906786da84',
    title: 'Come As You Are',
    artist: 'Nirvana',
    youtube_video_id: 'vabnZ9-ex7o',
    score: 0.873,
    rationale:
      'Recommended based on shared genre tags (grunge, alternative rock), ' +
      'similar tempo (120 BPM vs history average 117 BPM), and matching energy level.',
    features: { tempo: 120, key: 'F# minor', energy: 0.68, genres: ['grunge', 'alternative rock'] },
    limited_acoustic_data: false,
  },
  {
    track_id: 'cdd611f4-f270-405b-910b-fddf60dff322',
    title: 'Mr. Brightside',
    artist: 'The Killers',
    youtube_video_id: 'gGdGFtwCNBE',
    score: 0.791,
    rationale:
      'Recommended based on listeners of these artists also listening to this one, ' +
      'shared genre tags (alternative rock, indie rock), and similar tempo ' +
      '(148 BPM vs history average 132 BPM).',
    features: { tempo: 148, key: 'D major', energy: 0.82, genres: ['alternative rock', 'indie rock'] },
    limited_acoustic_data: false,
  },
  {
    track_id: 'aae0d97b-572e-4598-9b14-977895222794',
    title: 'Seven Nation Army',
    artist: 'The White Stripes',
    youtube_video_id: '0J2QdDbelmY',
    score: 0.742,
    rationale:
      'Note: limited acoustic data for this track; recommendation primarily based on ' +
      'metadata. Recommended based on shared genre tags (alternative rock, garage rock).',
    features: { tempo: 124, key: 'E minor', energy: 0.71, genres: ['alternative rock', 'garage rock'] },
    limited_acoustic_data: true,
  },
];

export const MOCK_HEALTH: HealthStatus = {
  status: 'ok',
  version: '0.1.0',
  cache: { feature_size: 12, youtube_size: 8, candidate_pools: 3, hits: 5, misses: 12 },
  sources: {
    musicbrainz: 'ok',
    acousticbrainz: 'degraded',
    youtube: 'ok',
    listenbrainz: 'ok',
  },
};

// Demo-mode stand-in for POST /resolve. Search and Top-5 results already carry a real
// MBID here, so resolution is a lookup by title/artist rather than a network call;
// an unknown track returns null, mirroring the live endpoint's contract.
export function resolveMockTrack(title: string, artist: string): string | null {
  const match = MOCK_SEARCH_RESULTS.find(
    (track) =>
      track.title.toLowerCase() === title.toLowerCase() &&
      track.artist.toLowerCase() === artist.toLowerCase(),
  );
  return match ? match.track_id : null;
}

// Pick the next recommendation not already played or excluded; cycle deterministically.
export function nextMockRecommendation(
  playedTrackIds: string[],
  excludeTrackIds: string[],
): Recommendation {
  const blocked = new Set([...playedTrackIds, ...excludeTrackIds]);
  const available = MOCK_RECOMMENDATIONS.filter((rec) => !blocked.has(rec.track_id));
  const pool = available.length > 0 ? available : MOCK_RECOMMENDATIONS;
  const index = playedTrackIds.length % pool.length;
  return pool[index];
}
