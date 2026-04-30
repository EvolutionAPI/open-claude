const test = require('node:test');
const assert = require('node:assert/strict');

const {
  parsePositiveNumber,
  resolveTerminalServerConfig,
} = require('../src/runtime-config');

test('parsePositiveNumber falls back on invalid values', () => {
  assert.equal(parsePositiveNumber('12', 1), 12);
  assert.equal(parsePositiveNumber('foo', 1), 1);
  assert.equal(parsePositiveNumber('-1', 1), 1);
});

test('resolveTerminalServerConfig reads env overrides', () => {
  const keys = [
    'TERMINAL_SESSION_TTL_HOURS',
    'TERMINAL_SESSION_GC_INTERVAL_MINUTES',
    'TERMINAL_WS_HEARTBEAT_TIMEOUT_MS',
    'TERMINAL_WS_HEARTBEAT_SWEEP_INTERVAL_MS',
    'TERMINAL_SERVER_BASE_FOLDER',
  ];
  const snapshot = Object.fromEntries(keys.map((key) => [key, process.env[key]]));

  try {
    process.env.TERMINAL_SESSION_TTL_HOURS = '36';
    process.env.TERMINAL_SESSION_GC_INTERVAL_MINUTES = '5';
    process.env.TERMINAL_WS_HEARTBEAT_TIMEOUT_MS = '45000';
    process.env.TERMINAL_WS_HEARTBEAT_SWEEP_INTERVAL_MS = '7000';
    process.env.TERMINAL_SERVER_BASE_FOLDER = 'D:/workspace';

    const config = resolveTerminalServerConfig({ port: 4000, dev: true });

    assert.equal(config.port, 4000);
    assert.equal(config.dev, true);
    assert.equal(config.baseFolder, 'D:/workspace');
    assert.equal(config.sessionTtlMs, 36 * 60 * 60 * 1000);
    assert.equal(config.sessionGcIntervalMs, 5 * 60 * 1000);
    assert.equal(config.wsHeartbeatTimeoutMs, 45000);
    assert.equal(config.wsHeartbeatSweepIntervalMs, 7000);
  } finally {
    for (const key of keys) {
      if (snapshot[key] === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = snapshot[key];
      }
    }
  }
});
