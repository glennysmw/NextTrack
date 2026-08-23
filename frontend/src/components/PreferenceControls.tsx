import { Gauge } from 'lucide-react';
import type { CSSProperties } from 'react';

import { TEMPO_LIMITS } from '../constants';
import type { Preferences } from '../types';
import { ModeToggle } from './ModeToggle';

interface PreferenceControlsProps {
  preferences: Preferences;
  onChange: (preferences: Preferences) => void;
}

const SPAN = TEMPO_LIMITS.max - TEMPO_LIMITS.min;

// Drives the amber fill on the fader track (index.css reads --fill). Presentation
// only — the value itself still comes straight from the input's onChange.
const fillTo = (value: number): CSSProperties =>
  ({ '--fill': `${((value - TEMPO_LIMITS.min) / SPAN) * 100}%` }) as CSSProperties;

export function PreferenceControls({ preferences, onChange }: PreferenceControlsProps) {
  const [min, max] = preferences.tempo_range;

  const setMin = (value: number) =>
    onChange({ ...preferences, tempo_range: [Math.min(value, max), max] });

  const setMax = (value: number) =>
    onChange({ ...preferences, tempo_range: [min, Math.max(value, min)] });

  return (
    <div className="panel">
      <div className="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-4 border-b border-rule pb-2">
            <h2 className="panel-label flex items-center gap-2">
              <Gauge size={13} strokeWidth={1.25} />
              Tempo window
            </h2>
            <span className="font-mono text-micro text-ink">
              {min}&ndash;{max} <span className="text-ink-faint">BPM</span>
            </span>
          </div>

          <div className="mt-4 space-y-2">
            <div className="flex items-center gap-4">
              <span className="w-8 shrink-0 font-mono text-label uppercase text-ink-faint">
                Min
              </span>
              <input
                type="range"
                min={TEMPO_LIMITS.min}
                max={TEMPO_LIMITS.max}
                value={min}
                style={fillTo(min)}
                onChange={(event) => setMin(Number(event.target.value))}
                aria-label="Minimum tempo"
              />
              <span className="w-8 shrink-0 text-right font-mono text-micro text-ink">
                {min}
              </span>
            </div>

            <div className="flex items-center gap-4">
              <span className="w-8 shrink-0 font-mono text-label uppercase text-ink-faint">
                Max
              </span>
              <input
                type="range"
                min={TEMPO_LIMITS.min}
                max={TEMPO_LIMITS.max}
                value={max}
                style={fillTo(max)}
                onChange={(event) => setMax(Number(event.target.value))}
                aria-label="Maximum tempo"
              />
              <span className="w-8 shrink-0 text-right font-mono text-micro text-ink">
                {max}
              </span>
            </div>
          </div>

          {/* Scale plate: the ends of the range and its unit, aligned to the track. */}
          <div className="mx-12 flex justify-between border-t border-rule pt-1 font-mono text-label text-ink-faint">
            <span>{TEMPO_LIMITS.min}</span>
            <span>BPM</span>
            <span>{TEMPO_LIMITS.max}</span>
          </div>
        </div>

        <ModeToggle
          autoAdvance={preferences.auto_advance}
          onChange={(autoAdvance) => onChange({ ...preferences, auto_advance: autoAdvance })}
        />
      </div>
    </div>
  );
}
