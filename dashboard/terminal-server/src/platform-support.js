const fs = require('fs');
const path = require('path');

const WORKSPACE_ROOT = path.resolve(__dirname, '..', '..', '..');
const PLATFORM_DATA_DIR = path.join(WORKSPACE_ROOT, 'dashboard', 'data', 'platform');
const PROVIDER_METRICS_PATH = path.join(PLATFORM_DATA_DIR, 'provider-metrics.jsonl');
const PLATFORM_EVENTS_PATH = path.join(PLATFORM_DATA_DIR, 'events.jsonl');

function ensurePlatformDataDir() {
  fs.mkdirSync(PLATFORM_DATA_DIR, { recursive: true });
  return PLATFORM_DATA_DIR;
}

function appendJsonl(filePath, payload) {
  ensurePlatformDataDir();
  const event = {
    ts: new Date().toISOString(),
    ...payload,
  };
  fs.appendFileSync(filePath, `${JSON.stringify(event)}\n`, 'utf8');
  return event;
}

function readJson(filePath, fallback) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return fallback;
  }
}

module.exports = {
  WORKSPACE_ROOT,
  PLATFORM_DATA_DIR,
  PROVIDER_METRICS_PATH,
  PLATFORM_EVENTS_PATH,
  ensurePlatformDataDir,
  appendJsonl,
  readJson,
};
