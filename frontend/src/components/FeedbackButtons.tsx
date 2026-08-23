import { ThumbsDown, ThumbsUp } from 'lucide-react';
import { useState } from 'react';

import type { FeedbackRating } from '../types';

interface FeedbackButtonsProps {
  onFeedback: (rating: FeedbackRating) => void;
}

// Both buttons share a dismissed state; the parent remounts this on each new
// recommendation (via key) so feedback can be given once per recommendation.
export function FeedbackButtons({ onFeedback }: FeedbackButtonsProps) {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) {
    return (
      <p className="border-t border-rule pt-3 font-mono text-label uppercase text-ink-faint">
        Logged for this session
      </p>
    );
  }

  const handle = (rating: FeedbackRating) => {
    onFeedback(rating);
    setDismissed(true);
  };

  return (
    <div className="flex items-center gap-3 border-t border-rule pt-3">
      <span className="panel-label">Good pick?</span>
      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          aria-label="Thumbs up"
          onClick={() => handle('up')}
          className="inline-flex items-center gap-1 border border-rule px-2 py-1 font-mono text-label text-ink-muted transition-colors hover:border-moss hover:text-moss-ink active:translate-x-px active:translate-y-px"
        >
          <ThumbsUp size={12} strokeWidth={1.25} />+
        </button>
        <button
          type="button"
          aria-label="Thumbs down"
          onClick={() => handle('down')}
          className="inline-flex items-center gap-1 border border-rule px-2 py-1 font-mono text-label text-ink-muted transition-colors hover:border-rust hover:text-rust-ink active:translate-x-px active:translate-y-px"
        >
          <ThumbsDown size={12} strokeWidth={1.25} />&minus;
        </button>
      </div>
    </div>
  );
}
