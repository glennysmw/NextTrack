import { describe, expect, it } from 'vitest';

import { isMbid } from './constants';
import {
  MOCK_RECOMMENDATIONS,
  MOCK_SEARCH_RESULTS,
  nextMockRecommendation,
  resolveMockTrack,
} from './mockData';

// Regression tests for the demo-mode defect found while producing the draft report's
// screenshots: mock track ids were placeholder strings like 'mock-0001-teen-spirit',
// which fail isMbid(), so playing a search or Top-5 result in demo mode never reached
// nextMockRecommendation and the card showed "we couldn't identify that track".
describe('demo-mode identifiers', () => {
  it('every mock search result carries an MBID-shaped track id', () => {
    for (const track of MOCK_SEARCH_RESULTS) {
      expect(isMbid(track.track_id), `${track.title} has a non-MBID id`).toBe(true);
    }
  });

  it('every mock recommendation carries an MBID-shaped track id', () => {
    for (const track of MOCK_RECOMMENDATIONS) {
      expect(isMbid(track.track_id), `${track.title} has a non-MBID id`).toBe(true);
    }
  });

  it('resolveMockTrack returns an MBID for a known track', () => {
    const id = resolveMockTrack('Smells Like Teen Spirit', 'Nirvana');
    expect(id).not.toBeNull();
    expect(isMbid(id!)).toBe(true);
  });

  it('resolveMockTrack is case-insensitive', () => {
    expect(resolveMockTrack('billie jean', 'MICHAEL JACKSON')).toBe(
      resolveMockTrack('Billie Jean', 'Michael Jackson'),
    );
  });

  it('resolveMockTrack returns null for an unknown track, like the live endpoint', () => {
    expect(resolveMockTrack('Not A Real Song', 'Nobody')).toBeNull();
  });
});

describe('nextMockRecommendation', () => {
  it('never returns a track already played', () => {
    const played = [MOCK_RECOMMENDATIONS[0].track_id];
    const next = nextMockRecommendation(played, []);
    expect(next.track_id).not.toBe(played[0]);
  });

  it('respects the exclusion list', () => {
    const excluded = [MOCK_RECOMMENDATIONS[0].track_id, MOCK_RECOMMENDATIONS[1].track_id];
    expect(excluded).not.toContain(nextMockRecommendation([], excluded).track_id);
  });

  it('is deterministic for identical inputs', () => {
    const a = nextMockRecommendation(['x'], []);
    const b = nextMockRecommendation(['x'], []);
    expect(a.track_id).toBe(b.track_id);
  });

  it('still returns a track when everything is blocked', () => {
    const all = MOCK_RECOMMENDATIONS.map((r) => r.track_id);
    expect(nextMockRecommendation(all, all).track_id).toBeTruthy();
  });
});
