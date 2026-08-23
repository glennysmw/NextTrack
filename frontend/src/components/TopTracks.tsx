import { Play } from 'lucide-react';

import type { SearchResult } from '../types';
import { AlbumArt } from './AlbumArt';

interface TopTracksProps {
  tracks: SearchResult[];
  loading: boolean;
  onPlay: (track: SearchResult) => void;
}

// The house chart, set as a printed listing. Same row language as search results.
export function TopTracks({ tracks, loading, onPlay }: TopTracksProps) {
  return (
    <section className="panel">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-rule pb-3">
        <h2 className="panel-label">Today&rsquo;s Top 5</h2>
        <p className="font-mono text-micro text-ink-muted">
          Fresh daily — pick one and NextTrack takes it from there.
        </p>
      </div>

      {loading ? (
        <ol className="-mx-2" aria-hidden="true">
          {Array.from({ length: 5 }).map((_, i) => (
            <li key={i} className="flex items-center gap-4 border-b border-rule px-2 py-3">
              <span className="w-6 shrink-0 text-right font-mono text-micro text-ink-faint">
                {String(i + 1).padStart(2, '0')}
              </span>
              <span className="h-12 w-12 shrink-0 border border-rule bg-deck" />
              <span className="h-3 w-40 max-w-full bg-deck" />
            </li>
          ))}
        </ol>
      ) : (
        <ol className="-mx-2">
          {tracks.map((track, index) => (
            <li key={track.track_id}>
              <button
                type="button"
                onClick={() => onPlay(track)}
                className="track-row group relative"
              >
                <span className="absolute left-0 top-0 h-full w-[3px] bg-amber opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
                <span className="w-6 shrink-0 text-right font-mono text-micro text-ink-faint transition-colors group-hover:text-amber-ink">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <AlbumArt src={track.thumbnail} alt={`${track.title} cover`} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-display text-body-lg font-semibold text-ink">
                    {track.title}
                  </span>
                  <span className="block truncate font-mono text-micro text-ink-muted">
                    {track.artist}
                  </span>
                </span>
                <span className="flex h-9 w-9 shrink-0 items-center justify-center border border-rule text-ink-faint transition-colors group-hover:border-ink group-hover:bg-amber group-hover:text-on-accent">
                  <Play size={14} strokeWidth={1.25} fill="currentColor" />
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
