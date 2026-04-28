import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': 'http://localhost:8080' } },
  resolve: {
    // Resolve workspace packages from TypeScript source in dev/build.
    // 'source' maps to ./src/index.ts in @evoapi/evonexus-ui's exports field.
    conditions: ['source', 'import', 'module', 'browser', 'default'],
    alias: {
      // Allow CSS @import "@evoapi/evonexus-ui/tokens.css" to resolve
      '@evoapi/evonexus-ui/tokens.css':
        new URL('../packages/ui/src/tokens.css', import.meta.url).pathname,
    },
  },
})
