import { AlertTriangle, Music2, Play, SkipForward } from 'lucide-react';
import type { ReactNode } from 'react';

import type { FeedbackRating, Recommendation } from '../types';
import { Equalizer } from './Equalizer';
import { FeedbackButtons } from './FeedbackButtons';
import { TapeReel } from './icons/TapeReel';

interface RecommendationCardProps {
  recommendation: Recommendation | null;
  loading: boolean;
  error: string | null;
  onPlayNext: () => void;
  onNextAlternative: () => void;
  onFeedback: (rating: FeedbackRating) => void;
}

// One measurement off the sleeve's spec block: mono term over mono value.
function Spec({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt className="font-mono text-label uppercase text-ink-faint">{term}</dt>
      <dd className="mt-0.5 font-mono text-micro text-ink">{children}</dd>
    </div>
  );
}

// The B-side card. Everything here is printed: the match is a typeset figure, not
// a gauge; the rationale sits under a rule; the transport is two square keys.
export function RecommendationCard({
  recommendation,
  loading,
  error,
  onPlayNext,
  onNextAlternative,
  onFeedback,
}: RecommendationCardProps) {
  return (
    <div className="panel">
      <div className="mb-4 flex items-center gap-2 border-b border-rule pb-3">
        <TapeReel size={14} className="text-amber-ink" />
        <h2 className="panel-label">Recommended Next</h2>
        <span className="ml-auto font-mono text-label uppercase text-ink-faint">
          B-side
        </span>
      </div>

      {loading && (
        <div className="flex items-center gap-3 font-mono text-micro uppercase text-ink-muted">
          <Equalizer bars={4} className="h-4" />
          Cueing next track…
        </div>
      )}

      {error && !loading && (
        <div className="flex items-start gap-2 border border-rust bg-rust/10 p-3 text-rust-ink">
          <AlertTriangle size={15} strokeWidth={1.25} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {!loading && !error && !recommendation && (
        <p className="flex items-center gap-2 text-ink-muted">
          <Music2 size={15} strokeWidth={1.25} />
          Play a track to get a recommendation.
        </p>
      )}

      {!loading && !error && recommendation && (
        <div className="space-y-4">
          <div className="min-w-0">
            <p className="truncate font-display text-title font-semibold text-ink">
              {recommendation.title}
            </p>
            <p className="truncate font-mono text-micro text-ink-muted">
              {recommendation.artist}
            </p>
          </div>

          <p className="font-mono text-label uppercase text-amber-ink">
            Match {String(Math.round(recommendation.score * 100)).padStart(3, '0')} /
            100
          </p>

          {recommendation.limited_acoustic_data && (
            <span className="stamp border-rust text-rust-ink">
              <AlertTriangle size={11} strokeWidth={1.25} />
              Limited acoustic data
            </span>
          )}

          <p className="border-t border-rule pt-3 text-ink-muted">
            {recommendation.rationale}
          </p>

          <dl className="grid grid-cols-3 gap-x-6 gap-y-3 border-t border-rule pt-3">
            <Spec term="Tempo">{Math.round(recommendation.features.tempo)} BPM</Spec>
            <Spec term="Key">{recommendation.features.key}</Spec>
            <Spec term="Energy">{recommendation.features.energy.toFixed(2)}</Spec>
          </dl>

          {recommendation.features.genres.length > 0 && (
            <p className="font-mono text-label uppercase text-ink-faint">
              {recommendation.features.genres.slice(0, 3).join(' · ')}
            </p>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            <button type="button" onClick={onPlayNext} className="btn-play">
              <Play size={13} strokeWidth={1.25} fill="currentColor" />
              Play next
            </button>
            <button
              type="button"
              onClick={onNextAlternative}
              className="btn-ghost bg-sleeve"
            >
              <SkipForward size={13} strokeWidth={1.25} />
              Next option
            </button>
          </div>

          <FeedbackButtons key={recommendation.track_id} onFeedback={onFeedback} />
        </div>
      )}
    </div>
  );
}
