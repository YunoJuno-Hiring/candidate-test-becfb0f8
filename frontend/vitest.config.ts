import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Kept separate from vite.config.ts so the dev server config stays as it was.
// jsdom gives components a browser-like DOM to render into.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
  },
})
