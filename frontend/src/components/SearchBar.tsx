import { Search, X } from 'lucide-react';
import { useState, type FormEvent } from 'react';

interface SearchBarProps {
  onSearch: (query: string) => void;
  onClear: () => void;
  loading: boolean;
}

export function SearchBar({ onSearch, onClear, loading }: SearchBarProps) {
  const [query, setQuery] = useState('');

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed) {
      onSearch(trimmed);
    }
  };

  const handleChange = (value: string) => {
    setQuery(value);
    // Empty the box → dismiss the results and return to Today's Top 5.
    if (value.trim() === '') {
      onClear();
    }
  };

  const clear = () => {
    setQuery('');
    onClear();
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-stretch gap-4">
      <span className="panel-label hidden shrink-0 self-end pb-3 sm:block">Find</span>
      <div className="relative flex flex-1 items-center border-b border-rule-strong transition-colors focus-within:border-amber">
        <input
          value={query}
          onChange={(event) => handleChange(event.target.value)}
          placeholder="search a track…"
          aria-label="Search for a song"
          className="w-full bg-transparent py-2.5 pr-8 font-mono text-body text-ink placeholder:text-ink-faint"
        />
        {query && (
          <button
            type="button"
            onClick={clear}
            aria-label="Clear search"
            className="absolute right-0 p-1 text-ink-faint transition-colors hover:text-ink"
          >
            <X size={15} strokeWidth={1.25} />
          </button>
        )}
      </div>
      <button
        type="submit"
        disabled={loading}
        aria-label="Search"
        className="flex h-10 w-10 shrink-0 items-center justify-center self-end border border-ink bg-amber text-on-accent shadow-hard-sm transition-[transform,box-shadow] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none disabled:opacity-50"
      >
        {loading ? (
          <span className="h-3 w-3 animate-tape-tick bg-on-accent" />
        ) : (
          <Search size={16} strokeWidth={1.25} />
        )}
      </button>
    </form>
  );
}
