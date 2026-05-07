/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        /*
         * Setting 'sans' here overrides Tailwind's default font-sans stack
         * for EVERY component that uses font-sans, text-*, or the default body font.
         * This is the single source of truth — no more mixed fonts.
         */
        sans: [
          'IBM Plex Sans',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'sans-serif',
        ],
        mono: [
          'JetBrains Mono',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'monospace',
        ],
      },
      colors: {
        /*
         * QueryTuner design tokens — use these in Tailwind classes
         * e.g. bg-qt-surface, text-qt-accent, border-qt-border
         */
        qt: {
          bg: '#0f172a',
          surface: '#1e293b',
          'surface-hi': '#263347',
          border: '#2d3f55',
          'border-hi': '#3b5268',
          text: '#e2e8f0',
          muted: '#7fa3c4',
          dim: '#4a6480',
          accent: '#38bdf8',
          green: '#34d399',
          yellow: '#fbbf24',
          orange: '#f97316',
          red: '#f87171',
        },
      },
    },
  },
  plugins: [],
}
