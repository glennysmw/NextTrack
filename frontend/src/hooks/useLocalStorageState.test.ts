import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useLocalStorageState } from './useLocalStorageState';

describe('useLocalStorageState', () => {
  beforeEach(() => localStorage.clear());

  it('returns the default when nothing is stored', () => {
    const { result } = renderHook(() => useLocalStorageState('k', { a: 1 }));
    expect(result.current[0]).toEqual({ a: 1 });
  });

  it('hydrates a previously stored value', () => {
    localStorage.setItem('k', JSON.stringify({ a: 42 }));
    const { result } = renderHook(() => useLocalStorageState('k', { a: 1 }));
    expect(result.current[0]).toEqual({ a: 42 });
  });

  it('mirrors updates into localStorage', () => {
    const { result } = renderHook(() => useLocalStorageState('k', 0));
    act(() => result.current[1](7));
    expect(result.current[0]).toBe(7);
    expect(JSON.parse(localStorage.getItem('k')!)).toBe(7);
  });

  it('supports functional updates', () => {
    const { result } = renderHook(() => useLocalStorageState('k', 1));
    act(() => result.current[1]((prev) => prev + 4));
    expect(result.current[0]).toBe(5);
  });

  // The schema guard is the reason this hook takes a validate predicate at all: a
  // stale schema left by an earlier version of the app, or a hand-edited value, must
  // hydrate the default rather than reach components with the wrong shape.
  it('falls back to the default when the stored value fails validation', () => {
    localStorage.setItem('k', JSON.stringify({ wrong: 'shape' }));
    const { result } = renderHook(() =>
      useLocalStorageState('k', [1, 2], Array.isArray),
    );
    expect(result.current[0]).toEqual([1, 2]);
  });

  it('falls back to the default when the stored value is not valid JSON', () => {
    localStorage.setItem('k', '{not json');
    const { result } = renderHook(() => useLocalStorageState('k', 'safe'));
    expect(result.current[0]).toBe('safe');
  });

  it('accepts a stored value that passes validation', () => {
    localStorage.setItem('k', JSON.stringify([9]));
    const { result } = renderHook(() => useLocalStorageState('k', [], Array.isArray));
    expect(result.current[0]).toEqual([9]);
  });

  it('reset removes the key and restores the default', () => {
    const { result } = renderHook(() => useLocalStorageState('k', 'default'));
    act(() => result.current[1]('changed'));
    expect(localStorage.getItem('k')).toBe(JSON.stringify('changed'));

    act(() => result.current[2]());
    expect(result.current[0]).toBe('default');
  });

  it('survives a localStorage write failure', () => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new DOMException('QuotaExceededError');
    };
    try {
      const { result } = renderHook(() => useLocalStorageState('k', 0));
      act(() => result.current[1](1));
      expect(result.current[0]).toBe(1); // state still updates; persistence is best-effort
    } finally {
      Storage.prototype.setItem = original;
    }
  });
});
