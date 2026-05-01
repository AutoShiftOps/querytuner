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
});
