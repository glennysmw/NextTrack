import { Play } from 'lucide-react';

import type { SearchResult } from '../types';
import { AlbumArt } from './AlbumArt';

interface SearchResultsProps {
  results: SearchResult[];
  onPlay: (result: SearchResult) => void;
}

// A printed track listing: numbered mono column, hairline between rows, no card
// behind each row. Hover raises a warm band and a leading cue bar.
export function SearchResults({ results, onPlay }: SearchResultsProps) {
  return (
    <section className="panel">
      <h2 className="panel-label border-b border-rule pb-3">Search results</h2>
      {results.length === 0 ? (
        <p className="pt-4 text-ink-muted">No matches with a playable video.</p>
      ) : (
        <ol className="-mx-2">
          {results.map((result, index) => (
            <li key={result.track_id}>
              <button
                type="button"
                onClick={() => onPlay(result)}
                className="track-row group relative"
              >
                <span className="absolute left-0 top-0 h-full w-[3px] bg-amber opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
                <span className="w-6 shrink-0 text-right font-mono text-micro text-ink-faint">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <AlbumArt
                  src={result.thumbnail}
                  alt={`${result.title} cover`}
                  size="h-10 w-10"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-display text-body-lg font-semibold text-ink">
                    {result.title}
                  </span>
                  <span className="block truncate font-mono text-micro text-ink-muted">
                    {result.artist}
                  </span>
                </span>
                <span className="flex h-8 w-8 shrink-0 items-center justify-center border border-rule text-ink-faint transition-colors group-hover:border-ink group-hover:bg-amber group-hover:text-on-accent">
                  <Play size={12} strokeWidth={1.25} fill="currentColor" />
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
