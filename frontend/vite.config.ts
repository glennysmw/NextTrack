import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // Respect a PORT override (e.g. preview tooling); default to 5173 for dev.
    port: Number(process.env.PORT) || 5173,
  },
});
