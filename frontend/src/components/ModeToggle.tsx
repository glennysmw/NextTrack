import { Hand } from 'lucide-react';

import { TapeReel } from './icons/TapeReel';

interface ModeToggleProps {
  autoAdvance: boolean;
  onChange: (autoAdvance: boolean) => void;
}

// Toggles between radio mode (auto-advance) and manual playback. A two-position
// mechanical switch: two square segments, the engaged one filled. Still one button
// with switch semantics, so the whole control stays clickable and readable to AT.
export function ModeToggle({ autoAdvance, onChange }: ModeToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={autoAdvance}
      onClick={() => onChange(!autoAdvance)}
      className="flex shrink-0 select-none border border-rule-strong font-mono text-label font-medium uppercase"
    >
      <span
        className={`flex items-center gap-1.5 px-3 py-2 transition-colors ${
          autoAdvance ? 'bg-amber text-on-accent' : 'text-ink-faint'
        }`}
      >
        <TapeReel size={13} />
        Radio
      </span>
      <span
        className={`flex items-center gap-1.5 border-l border-rule-strong px-3 py-2 transition-colors ${
          autoAdvance ? 'text-ink-faint' : 'bg-amber text-on-accent'
        }`}
      >
        <Hand size={13} strokeWidth={1.25} />
        Manual
      </span>
    </button>
  );
}
