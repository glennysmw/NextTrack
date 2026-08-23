// Colours, defaults, and other tunables. No magic numbers in business logic.
import type { Preferences } from './types';

export const API_URL: string =
  import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1';

export const DEMO_MODE: boolean = import.meta.env.VITE_DEMO_MODE === 'true';

// MusicBrainz Identifier shape. Search/Top tracks carry a YouTube video id as their
// track_id until it's resolved to a real MBID on play; this tells the two apart.
const MBID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const isMbid = (id: string): boolean => MBID_RE.test(id);

// localStorage keys (section 14). The reset button clears all of these.
export const STORAGE_KEYS = {
  history: 'nexttrack_session_history',
  currentTrack: 'nexttrack_current_track',
  preferences: 'nexttrack_preferences',
  feedback: 'nexttrack_feedback',
} as const;

export const DEFAULT_PREFERENCES: Preferences = {
  tempo_range: [80, 140],
  exclude_artists: [],
  auto_advance: true,
};

export const TEMPO_LIMITS = { min: 40, max: 200 } as const;

// Cap the locally-stored feedback log so a long session can't exhaust the
// localStorage quota; only the most recent events are kept.
export const MAX_FEEDBACK_EVENTS = 200;

// Reusable class fragments for a consistent visual language. `panel`, `btn-play`,
// and `btn-ghost` are defined in index.css (@layer components).
export const CARD_CLASS = 'panel';

export const ACCENT_TEXT = 'text-play-400';
