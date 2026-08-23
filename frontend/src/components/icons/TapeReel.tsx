interface TapeReelProps {
  /** Edge length in px; the reel is square. */
  size?: number;
  className?: string;
}

// A cassette hub: outer flange, toothed centre, six spokes. Drawn to lucide's
// conventions (24px box, currentColor, 1.25px stroke) so it sits flush beside the
// functional icons. Decorative — the label next to it carries the meaning.
export function TapeReel({ size = 16, className = '' }: TapeReelProps) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="square"
      className={className}
    >
      <circle cx="12" cy="12" r="9.25" />
      <circle cx="12" cy="12" r="3" />
      {/* Six spokes between hub and flange. */}
      {[0, 60, 120, 180, 240, 300].map((deg) => (
        <line
          key={deg}
          x1="12"
          y1="12"
          x2="12"
          y2="2.75"
          transform={`rotate(${deg} 12 12)`}
          strokeDasharray="3.2 3.05"
        />
      ))}
    </svg>
  );
}
