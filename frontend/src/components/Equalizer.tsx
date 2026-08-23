interface EqualizerProps {
  /** Bar count; defaults to 4. */
  bars?: number;
  className?: string;
}

// A VU meter, not a pulse. The bars step between four discrete marks like a needle
// jumping, and each is offset so they read as separate channels. Decorative, so it
// is hidden from assistive tech; prefers-reduced-motion (index.css) freezes it.
export function Equalizer({ bars = 4, className = '' }: EqualizerProps) {
  return (
    <span
      aria-hidden="true"
      className={`inline-flex items-end gap-px text-amber ${className}`}
    >
      {Array.from({ length: bars }).map((_, i) => (
        <span
          key={i}
          className="w-[3px] origin-bottom animate-vu-meter bg-current"
          style={{ height: '100%', animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}
