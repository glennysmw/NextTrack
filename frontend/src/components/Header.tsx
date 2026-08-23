import { Moon, RotateCcw, Sun } from 'lucide-react';
import { useEffect } from 'react';

import { useLocalStorageState } from '../hooks/useLocalStorageState';
import { Equalizer } from './Equalizer';
import { PrivacyBadge } from './PrivacyBadge';

interface HeaderProps {
  onReset: () => void;
}

type Stock = 'dark' | 'light';

const isStock = (value: unknown): boolean => value === 'dark' || value === 'light';

// The top edge of the deck: VU meter behind glass, wordmark, and the faceplate
// controls. The lip below carries index ticks, like a tuning scale.
export function Header({ onReset }: HeaderProps) {
  const [stock, setStock] = useLocalStorageState<Stock>(
    'nexttrack_theme',
    'dark',
    isStock,
  );

  // Single class flip on <html>; index.html applies the same value before paint.
  useEffect(() => {
    document.documentElement.classList.toggle('dark', stock === 'dark');
  }, [stock]);

  const segment = (active: boolean) =>
    `flex items-center gap-1.5 px-2.5 py-2 transition-colors ${
      active ? 'bg-amber text-on-accent' : 'text-ink-faint hover:text-ink'
    }`;

  return (
    <header className="sticky top-0 z-30 border-b border-rule-strong bg-paper">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-6 py-4 sm:px-8">
        <div className="flex items-center gap-4">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center border border-rule-strong bg-deck">
            <Equalizer bars={4} className="h-4" />
          </span>
          <div>
            <h1 className="font-display text-title font-semibold text-ink [font-variation-settings:'opsz'_144]">
              NextTrack
            </h1>
            <p className="panel-label mt-0.5 hidden sm:block">Radio that forgets you</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden sm:block">
            <PrivacyBadge />
          </div>

          {/* Two-position stock switch — labelled ticks, not a rocker. */}
          <div
            role="group"
            aria-label="Colour stock"
            className="flex border border-rule-strong font-mono text-label font-medium uppercase"
          >
            <button
              type="button"
              onClick={() => setStock('light')}
              aria-pressed={stock === 'light'}
              className={segment(stock === 'light')}
            >
              <Sun size={12} strokeWidth={1.25} />
              <span className="hidden md:inline">Day</span>
            </button>
            <button
              type="button"
              onClick={() => setStock('dark')}
              aria-pressed={stock === 'dark'}
              className={`${segment(stock === 'dark')} border-l border-rule-strong`}
            >
              <Moon size={12} strokeWidth={1.25} />
              <span className="hidden md:inline">Night</span>
            </button>
          </div>

          <button type="button" onClick={onReset} className="btn-ghost px-2.5">
            <RotateCcw size={13} strokeWidth={1.25} />
            <span className="hidden md:inline">Reset</span>
          </button>
        </div>
      </div>

      {/* Deck lip: index ticks across the full width. */}
      <div
        aria-hidden="true"
        className="h-1.5 border-t border-rule bg-[repeating-linear-gradient(to_right,rgb(var(--rule-strong))_0_1px,transparent_1px_10px)]"
      />
    </header>
  );
}
