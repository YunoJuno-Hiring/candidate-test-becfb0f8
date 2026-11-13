import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Separate from vite.config.ts so the dev server is untouched; jsdom provides a browser-like DOM.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
  },
})
