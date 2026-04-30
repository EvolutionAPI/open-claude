import { defineConfig } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: 'http://127.0.0.1:8080',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'node scripts/start-e2e-server.mjs',
    cwd: frontendRoot,
    url: 'http://127.0.0.1:8080',
    timeout: 180_000,
    reuseExistingServer: false,
    env: {
      ...process.env,
      EVONEXUS_PORT: '8080',
    },
  },
})
