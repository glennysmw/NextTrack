import { Lock } from 'lucide-react';

// A typeset stamp rather than a pill — hairline rule, mono caps, glyph flush to the
// cap-height. The explanation is a plain bordered note on hover.
export function PrivacyBadge() {
  return (
    <div className="group relative">
      <span className="stamp cursor-default text-ink-muted">
        <Lock size={11} strokeWidth={1.25} />
        <span className="hidden sm:inline">Stateless · No tracking</span>
        <span className="sm:hidden">Private</span>
      </span>
      <div className="pointer-events-none absolute right-0 top-full z-40 mt-2 w-64 border border-rule-strong bg-sleeve p-3 text-micro leading-relaxed text-ink-muted opacity-0 shadow-hard transition-opacity duration-150 group-hover:opacity-100">
        NextTrack stores nothing about you on the server. Your session lives only in
        this browser tab. Close it and your data is gone.
      </div>
    </div>
  );
}
