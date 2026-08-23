import { Music2 } from 'lucide-react';

interface AlbumArtProps {
  src?: string | null;
  alt: string;
  /** Tailwind size classes, e.g. "h-12 w-12". */
  size?: string;
}

// Album cover mounted like a slide: hairline frame, a few px of matte, art inside.
// Falls back to a centred glyph on a warm surface when no artwork is available.
export function AlbumArt({ src, alt, size = 'h-12 w-12' }: AlbumArtProps) {
  if (!src) {
    return (
      <div className={`${size} shrink-0 border border-rule bg-deck p-[3px]`}>
        <span className="flex h-full w-full items-center justify-center bg-sleeve text-ink-faint">
          <Music2 className="h-1/2 w-1/2" strokeWidth={1.25} />
        </span>
      </div>
    );
  }
  return (
    <div className={`${size} shrink-0 border border-rule bg-deck p-[3px]`}>
      <img
        src={src}
        alt={alt}
        loading="lazy"
        className="h-full w-full object-cover"
      />
    </div>
  );
}
