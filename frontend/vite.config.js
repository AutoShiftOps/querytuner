import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    open: true,
  },
  build: {
    outDir: 'build',        // keeps Vercel config compatible (same as CRA)
    sourcemap: false,
  },
  define: {
    // CRA used process.env.REACT_APP_* — Vite uses import.meta.env.VITE_*
    // This shim lets old REACT_APP_ references keep working during migration
    'process.env': {},
  },
  test: {
    // Was unset (vitest's default "node" environment — no document/window
    // at all) until this pass added a component-render test harness. Every
    // pre-existing test is a pure-function test on plain JS (formatRelativeTime,
    // the sanitizer, quiz logic, ...) and is unaffected by jsdom being a
    // superset environment; this only *adds* the ability to render a real
    // .jsx component into a fake DOM, which nothing here could do before.
    environment: 'jsdom',
    // Runs before every test file — registers the shared @clerk/clerk-react
    // mock (src/test/setup.js) globally so individual test files don't each
    // need their own vi.mock('@clerk/clerk-react', ...) boilerplate.
    setupFiles: ['./src/test/setup.js'],
  },
});
