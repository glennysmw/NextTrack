import { useCallback, useEffect, useRef, useState } from 'react';

type SetState<T> = (value: T | ((prev: T) => T)) => void;

// Declarative state that mirrors itself into localStorage. `reset` removes the key
// and restores the default — used by the session reset button. An optional
// `validate` predicate rejects structurally wrong persisted data (stale schema or
// manual tampering) so we hydrate the default instead of crashing downstream.
export function useLocalStorageState<T>(
  key: string,
  defaultValue: T,
  validate?: (value: unknown) => boolean,
): readonly [T, SetState<T>, () => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) {
        return defaultValue;
      }
      const parsed: unknown = JSON.parse(raw);
      if (validate && !validate(parsed)) {
        return defaultValue;
      }
      return parsed as T;
    } catch {
      return defaultValue;
    }
  });

  const defaultRef = useRef(defaultValue);
  defaultRef.current = defaultValue;

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Ignore quota or serialization failures — persistence is best-effort.
    }
  }, [key, value]);

  const reset = useCallback(() => {
    localStorage.removeItem(key);
    setValue(defaultRef.current);
  }, [key]);

  return [value, setValue, reset] as const;
}
