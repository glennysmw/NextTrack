/** @type {import('tailwindcss').Config} */

// Every colour is a CSS custom property holding an "R G B" triplet, so the theme
// switch is a single class flip on <html> and Tailwind's /alpha modifiers still work.
const tone = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    // Full replacement, not extend: the palette is materials, not a SaaS ramp.
    // Anything outside this list simply won't compile, which is the point.
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      inherit: 'inherit',

      paper: tone('paper'), // page stock
      sleeve: tone('sleeve'), // panel surface
      deck: tone('deck'), // inset / raised surface

      ink: tone('ink'), // primary type
      'ink-muted': tone('ink-muted'), // secondary type
      'ink-faint': tone('ink-faint'), // labels, tick marks

      rule: tone('rule'), // decorative hairline
      'rule-strong': tone('rule-strong'), // interactive borders (>=3:1)

      amber: tone('amber'), // tungsten accent — fills
      'amber-ink': tone('amber-ink'), // tungsten accent — type
      moss: tone('moss'), // signal: playing
      'moss-ink': tone('moss-ink'),
      rust: tone('rust'), // signal: skip / warn
      'rust-ink': tone('rust-ink'),

      'on-accent': tone('on-accent'), // type on an amber fill
    },

    // Perfect-fourth-ish scale. No ad-hoc text-xs/text-sm anywhere.
    fontSize: {
      label: ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.06em' }],
      micro: ['0.75rem', { lineHeight: '1.125rem', letterSpacing: '0.02em' }],
      body: ['0.9375rem', { lineHeight: '1.5rem' }],
      'body-lg': ['1.125rem', { lineHeight: '1.6rem', letterSpacing: '-0.005em' }],
      title: ['1.625rem', { lineHeight: '1.85rem', letterSpacing: '-0.015em' }],
      display: ['2.5rem', { lineHeight: '2.55rem', letterSpacing: '-0.02em' }],
      hero: ['3.75rem', { lineHeight: '3.75rem', letterSpacing: '-0.022em' }],
    },

    // Hard geometry. 2px on the few things that need softening, round only for
    // genuinely round objects (reels, the record button, the dial).
    borderRadius: {
      none: '0',
      DEFAULT: '2px',
      full: '9999px',
    },

    // No floating glass. A printed card sits on the page and casts one hard offset.
    boxShadow: {
      none: 'none',
      hard: '3px 3px 0 rgb(var(--rule-strong))',
      'hard-sm': '2px 2px 0 rgb(var(--rule-strong))',
      'hard-amber': '2px 2px 0 rgb(var(--amber))',
    },

    extend: {
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        sans: ['"Instrument Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      keyframes: {
        // The play head. Discrete, one beat per second — never a smooth fade.
        'tape-tick': {
          '0%': { opacity: '1' },
          '100%': { opacity: '0.2' },
        },
        // An analog needle jumping between marks, not a pulsing gradient.
        'vu-meter': {
          '0%, 100%': { transform: 'scaleY(0.25)' },
          '50%': { transform: 'scaleY(1)' },
        },
      },
      animation: {
        'tape-tick': 'tape-tick 1s steps(2, jump-none) infinite alternate',
        'vu-meter': 'vu-meter 1.2s steps(4, jump-none) infinite',
      },
    },
  },
  plugins: [],
};
