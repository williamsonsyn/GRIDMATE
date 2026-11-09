import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// In development, /api requests are proxied to the FastAPI backend.
// Override with VITE_API_PROXY if the backend runs elsewhere.
const target = process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': { target, changeOrigin: true } } },
  preview: { port: 4173, proxy: { '/api': { target, changeOrigin: true } } },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
});
