import YouTube, { type YouTubeProps } from 'react-youtube';

import type { HistoryEntry } from '../types';

interface PlayerProps {
  track: HistoryEntry;
  onEnd: () => void;
}

const PLAYER_OPTS: YouTubeProps['opts'] = {
  width: '100%',
  height: '260',
  playerVars: { autoplay: 1 },
};

// A cassette-deck surround: hissed head rail with the mono readout and side ticks,
// the transport window, then the printed title plate. The status lamp and the A/B
// ticks are diegetic — they describe the deck, they do not drive the player.
export function Player({ track, onEnd }: PlayerProps) {
  return (
    <div className="panel p-0">
      <div className="tape-hiss flex items-center gap-3 border-b border-rule px-4 py-2.5">
        <span
          aria-hidden="true"
          className="h-2.5 w-2.5 shrink-0 animate-tape-tick bg-moss"
        />
        <span className="min-w-0 flex-1 truncate font-mono text-label uppercase text-ink">
          {track.title}
        </span>
        <span
          aria-hidden="true"
          className="flex shrink-0 items-center gap-2 font-mono text-label text-ink"
        >
          A
          <span className="h-3 w-px bg-rule-strong" />
          <span className="text-ink-faint">B</span>
        </span>
      </div>

      <div className="border-b border-rule bg-paper">
        <YouTube
          key={track.youtube_video_id}
          videoId={track.youtube_video_id}
          opts={PLAYER_OPTS}
          onEnd={() => onEnd()}
          className="aspect-video"
          iframeClassName="h-full w-full"
        />
      </div>

      <div className="tape-hiss px-4 py-3">
        <h2 className="panel-label">Now Playing</h2>
        <p className="mt-1 truncate">
          <span className="font-display text-body-lg font-semibold text-ink">
            {track.title}
          </span>
          <span className="font-mono text-micro text-ink-muted"> — {track.artist}</span>
        </p>
      </div>
    </div>
  );
}
