import { execFileSync, spawn } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(scriptDir, '..')
const repoRoot = path.resolve(frontendRoot, '..', '..')

function sqliteUrl(filePath) {
  return `sqlite:///${path.resolve(filePath).replace(/\\/g, '/')}`
}

const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'evonexus-e2e-'))
const databasePath = path.join(tempDir, 'dashboard.db')

execFileSync('npm', ['run', 'build'], {
  cwd: frontendRoot,
  stdio: 'inherit',
  env: process.env,
  shell: true,
})

const child = spawn(process.platform === 'win32' ? 'python' : 'python3', ['dashboard/backend/app.py'], {
  cwd: repoRoot,
  stdio: 'inherit',
  env: {
    ...process.env,
    SQLALCHEMY_DATABASE_URI: sqliteUrl(databasePath),
    EVONEXUS_SECRET_KEY: process.env.EVONEXUS_SECRET_KEY || 'e2e-secret-key',
    EVONEXUS_PORT: process.env.EVONEXUS_PORT || '8080',
    CORS_ALLOWED_ORIGINS: 'http://127.0.0.1:8080',
    EVONEXUS_ENV: 'development',
  },
})

const shutdown = () => {
  if (!child.killed) {
    child.kill('SIGTERM')
  }
}

process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)
child.on('exit', (code, signal) => {
  process.exit(code ?? (signal ? 1 : 0))
})
