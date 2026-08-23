import type { HistoryEntry } from '../types';

interface HistoryListProps {
  history: HistoryEntry[];
}

// The setlist — a mixtape side, written down in order. The most recent entry sits
// slightly proud of the others: warm inset panel, amber index bar down its edge.
export function HistoryList({ history }: HistoryListProps) {
  return (
    <div className="panel">
      <h2 className="panel-label flex items-baseline gap-2 border-b border-rule pb-3">
        Setlist
        {history.length > 0 && (
          <span className="text-ink-faint">
            / {String(history.length).padStart(2, '0')}
          </span>
        )}
      </h2>
      {history.length === 0 ? (
        <p className="pt-4 text-ink-muted">Nothing played yet.</p>
      ) : (
        <ol className="-mx-2">
          {history.map((entry, index) => {
            const isCurrent = index === history.length - 1;
            return (
              <li
                key={`${entry.track_id}-${index}`}
                className={`relative flex items-center gap-4 border-b border-rule px-2 py-2.5 last:border-b-0 ${
                  isCurrent ? 'bg-deck' : ''
                }`}
              >
                {isCurrent && (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-0 h-full w-[3px] bg-amber"
                  />
                )}
                <span
                  className={`w-6 shrink-0 text-right font-mono text-micro ${
                    isCurrent ? 'text-amber-ink' : 'text-ink-faint'
                  }`}
                >
                  {String(index + 1).padStart(2, '0')}
                </span>
                <span className="min-w-0 truncate">
                  <span className="text-ink">{entry.title}</span>
                  <span className="font-mono text-micro text-ink-muted">
                    {' '}
                    — {entry.artist}
                  </span>
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
