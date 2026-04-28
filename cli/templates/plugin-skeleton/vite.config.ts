import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

/**
 * Plugin build config — ESM library mode.
 *
 * React is EXTERNALIZED: the host provides react/react-dom at runtime.
 * Bundling React here breaks hooks and ErrorBoundary across the host boundary.
 *
 * @evonexus/ui is BUNDLED into the plugin output so the tarball is self-contained.
 * This means tokens.css is not auto-injected — the host injects it once for all plugins.
 *
 * Distribution: build output (dist/) + plugin.yaml + migrations/ + README.md -> tarball.
 */
export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: resolve(__dirname, 'src/index.ts'),
      formats: ['es'],
      fileName: 'index',
    },
    rollupOptions: {
      // Host provides React at runtime — do NOT bundle it
      external: ['react', 'react-dom', 'react/jsx-runtime'],
    },
    sourcemap: false,
    outDir: 'dist',
  },
})
