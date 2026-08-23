// Shared domain types for the NextTrack frontend.

// A playable track from search or Today's Top 5. `track_id` is the YouTube video
// id; the MusicBrainz id used for recommendations is resolved lazily on play.
export interface SearchResult {
  track_id: string;
  title: string;
  artist: string;
  album?: string | null;
  thumbnail?: string | null;
  youtube_video_id: string;
  duration_seconds?: number | null;
}

// A track the user has actually played; the minimal shape kept in session history.
export interface HistoryEntry {
  track_id: string;
  title: string;
  artist: string;
  youtube_video_id: string;
}

export interface RecommendationFeatures {
  tempo: number;
  key: string;
  energy: number;
  genres: string[];
}

export interface Recommendation {
  track_id: string;
  title: string;
  artist: string;
  youtube_video_id: string;
  score: number;
  rationale: string;
  features: RecommendationFeatures;
  limited_acoustic_data: boolean;
}

export interface Preferences {
  tempo_range: [number, number];
  exclude_artists: string[];
  auto_advance: boolean;
}

// Parameters sent to POST /recommend.
export interface RecommendParams {
  tempo_range: [number, number];
  exclude_artists: string[];
  exclude_tracks: string[];
}

export type FeedbackRating = 'up' | 'down';

// Recorded locally for the planned user study; never sent to the server.
export interface FeedbackEvent {
  track_id: string;
  recommended_at: string;
  rating: FeedbackRating;
  history_snapshot: string[];
}

export interface HealthStatus {
  status: string;
  version: string;
  cache: {
    feature_size: number;
    youtube_size: number;
    candidate_pools: number;
    hits: number;
    misses: number;
  };
  sources: {
    musicbrainz: string;
    acousticbrainz: string;
    youtube: string;
    listenbrainz: string;
  };
}
