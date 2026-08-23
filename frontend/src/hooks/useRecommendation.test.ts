import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as api from '../api/nexttrack';
import type { HistoryEntry, Preferences, Recommendation } from '../types';
import { useRecommendation } from './useRecommendation';

const PREFS: Preferences = {
  tempo_range: [80, 140],
  exclude_artists: [],
  auto_advance: true,
};

const MBID_A = '6fd45825-5e07-48b7-801c-433c48d3262e';
const MBID_B = 'dec86327-b468-4250-a36e-7c906786da84';

const entry = (id: string, title = 'T'): HistoryEntry => ({
  track_id: id,
  title,
  artist: 'A',
  youtube_video_id: 'vid',
});

const rec = (id: string): Recommendation => ({
  track_id: id,
  title: `Track ${id}`,
  artist: 'Artist',
  youtube_video_id: 'vid',
  score: 0.8,
  rationale: 'because',
  features: { tempo: 120, key: 'C major', energy: 0.5, genres: ['rock'] },
  limited_acoustic_data: false,
});

describe('useRecommendation', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('fetches and exposes a recommendation', async () => {
    vi.spyOn(api, 'getRecommendation').mockResolvedValue(rec('r1'));
    const { result } = renderHook(() => useRecommendation());

    await act(async () => {
      await result.current.fetchNext([entry(MBID_A)], PREFS);
    });

    expect(result.current.recommendation?.track_id).toBe('r1');
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  // Only MBID-shaped ids can seed a recommendation. A track that played but never
  // resolved must produce a clear message, not a malformed request to the server.
  it('does not call the API when no history entry has a valid MBID', async () => {
    const spy = vi.spyOn(api, 'getRecommendation').mockResolvedValue(rec('r1'));
    const { result } = renderHook(() => useRecommendation());

    await act(async () => {
      await result.current.fetchNext([entry('not-an-mbid')], PREFS);
    });

    expect(spy).not.toHaveBeenCalled();
    expect(result.current.recommendation).toBeNull();
    expect(result.current.error).toMatch(/couldn't identify/i);
  });

  it('filters unresolved entries but still uses the resolved ones', async () => {
    const spy = vi.spyOn(api, 'getRecommendation').mockResolvedValue(rec('r1'));
    const { result } = renderHook(() => useRecommendation());

    await act(async () => {
      await result.current.fetchNext([entry(''), entry(MBID_A), entry('bad')], PREFS);
    });

    expect(spy).toHaveBeenCalledWith([MBID_A], expect.anything());
  });

  it('sets no error for an empty history', async () => {
    const { result } = renderHook(() => useRecommendation());
    await act(async () => {
      await result.current.fetchNext([], PREFS);
    });
    expect(result.current.error).toBeNull();
  });

  // The race guard: a slow earlier request must never overwrite a newer result. This
  // is the failure a double-click or a radio-mode auto-advance mid-request produces.
  it('discards a stale response that resolves after a newer one', async () => {
    let resolveSlow: (value: Recommendation) => void = () => {};
    const slow = new Promise<Recommendation>((res) => {
      resolveSlow = res;
    });

    vi.spyOn(api, 'getRecommendation')
      .mockImplementationOnce(() => slow)
      .mockImplementationOnce(() => Promise.resolve(rec('newer')));

    const { result } = renderHook(() => useRecommendation());

    act(() => {
      void result.current.fetchNext([entry(MBID_A)], PREFS);
    });
    await act(async () => {
      await result.current.fetchNext([entry(MBID_B)], PREFS);
    });
    expect(result.current.recommendation?.track_id).toBe('newer');

    // The first request now finishes — its result must be thrown away.
    await act(async () => {
      resolveSlow(rec('stale'));
      await slow;
    });
    expect(result.current.recommendation?.track_id).toBe('newer');
  });

  it('discards a stale *failure* so it cannot clear a newer result', async () => {
    let rejectSlow: (reason: unknown) => void = () => {};
    const slow = new Promise<Recommendation>((_res, rej) => {
      rejectSlow = rej;
    });

    vi.spyOn(api, 'getRecommendation')
      .mockImplementationOnce(() => slow)
      .mockImplementationOnce(() => Promise.resolve(rec('newer')));

    const { result } = renderHook(() => useRecommendation());
    act(() => {
      void result.current.fetchNext([entry(MBID_A)], PREFS);
    });
    await act(async () => {
      await result.current.fetchNext([entry(MBID_B)], PREFS);
    });

    await act(async () => {
      rejectSlow(new Error('boom'));
      await slow.catch(() => undefined);
    });

    expect(result.current.recommendation?.track_id).toBe('newer');
    expect(result.current.error).toBeNull();
  });

  it('nextAlternative excludes the current recommendation', async () => {
    const spy = vi
      .spyOn(api, 'getRecommendation')
      .mockResolvedValueOnce(rec('first'))
      .mockResolvedValueOnce(rec('second'));

    const { result } = renderHook(() => useRecommendation());
    await act(async () => {
      await result.current.fetchNext([entry(MBID_A)], PREFS);
    });
    await act(async () => {
      await result.current.nextAlternative([entry(MBID_A)], PREFS);
    });

    expect(spy.mock.calls[1][1].exclude_tracks).toEqual(['first']);
    expect(result.current.recommendation?.track_id).toBe('second');
  });

  it('fetchNext resets the accumulated exclusions', async () => {
    const spy = vi.spyOn(api, 'getRecommendation').mockResolvedValue(rec('r'));
    const { result } = renderHook(() => useRecommendation());

    await act(async () => {
      await result.current.fetchNext([entry(MBID_A)], PREFS);
    });
    await act(async () => {
      await result.current.nextAlternative([entry(MBID_A)], PREFS);
    });
    await act(async () => {
      await result.current.fetchNext([entry(MBID_A)], PREFS);
    });

    expect(spy.mock.calls[2][1].exclude_tracks).toEqual([]);
  });

  it('surfaces an error and clears the recommendation on failure', async () => {
    vi.spyOn(api, 'getRecommendation').mockRejectedValue(new Error('nope'));
    const { result } = renderHook(() => useRecommendation());

    await act(async () => {
      await result.current.fetchNext([entry(MBID_A)], PREFS);
    });

    expect(result.current.recommendation).toBeNull();
    expect(result.current.error).toBeTruthy();
    expect(result.current.loading).toBe(false);
  });

  it('clear() invalidates an in-flight request', async () => {
    let resolveSlow: (value: Recommendation) => void = () => {};
    const slow = new Promise<Recommendation>((res) => {
      resolveSlow = res;
    });
    vi.spyOn(api, 'getRecommendation').mockImplementation(() => slow);

    const { result } = renderHook(() => useRecommendation());
    act(() => {
      void result.current.fetchNext([entry(MBID_A)], PREFS);
    });
    act(() => result.current.clear());

    await act(async () => {
      resolveSlow(rec('late'));
      await slow;
    });

    await waitFor(() => expect(result.current.recommendation).toBeNull());
    expect(result.current.loading).toBe(false);
  });

  it('passes the user preferences through to the request', async () => {
    const spy = vi.spyOn(api, 'getRecommendation').mockResolvedValue(rec('r'));
    const { result } = renderHook(() => useRecommendation());
    const prefs: Preferences = {
      tempo_range: [100, 130],
      exclude_artists: ['Nickelback'],
      auto_advance: false,
    };

    await act(async () => {
      await result.current.fetchNext([entry(MBID_A)], prefs);
    });

    expect(spy).toHaveBeenCalledWith([MBID_A], {
      tempo_range: [100, 130],
      exclude_artists: ['Nickelback'],
      exclude_tracks: [],
    });
  });
});
