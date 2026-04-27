function parsePositiveNumber(raw, fallback) {
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) {
    return fallback;
  }
  return value;
}

function resolveTerminalServerConfig(options = {}) {
  const envPort = parsePositiveNumber(process.env.TERMINAL_SERVER_PORT, null);
  const ttlHours = parsePositiveNumber(process.env.TERMINAL_SESSION_TTL_HOURS, null);
  const gcMinutes = parsePositiveNumber(process.env.TERMINAL_SESSION_GC_INTERVAL_MINUTES, null);
  const heartbeatTimeout = parsePositiveNumber(process.env.TERMINAL_WS_HEARTBEAT_TIMEOUT_MS, null);
  const heartbeatSweep = parsePositiveNumber(process.env.TERMINAL_WS_HEARTBEAT_SWEEP_INTERVAL_MS, null);
  const envBaseFolder = process.env.TERMINAL_SERVER_BASE_FOLDER?.trim();

  return {
    port: options.port || envPort || 32352,
    dev: options.dev || false,
    baseFolder: options.baseFolder || envBaseFolder || process.cwd(),
    sessionTtlMs: options.sessionTtlMs ?? (
      ttlHours && ttlHours > 0 ? ttlHours * 60 * 60 * 1000 : (24 * 60 * 60 * 1000)
    ),
    sessionGcIntervalMs: options.sessionGcIntervalMs ?? (
      gcMinutes !== null && gcMinutes >= 0 ? gcMinutes * 60 * 1000 : (15 * 60 * 1000)
    ),
    autoSaveIntervalMs: options.autoSaveIntervalMs ?? 30000,
    sessionSaveDebounceMs: options.sessionSaveDebounceMs ?? 2000,
    wsHeartbeatTimeoutMs: options.wsHeartbeatTimeoutMs ?? (
      heartbeatTimeout && heartbeatTimeout > 0 ? heartbeatTimeout : (60 * 1000)
    ),
    wsHeartbeatSweepIntervalMs: options.wsHeartbeatSweepIntervalMs ?? (
      heartbeatSweep && heartbeatSweep > 0 ? heartbeatSweep : (15 * 1000)
    ),
  };
}

module.exports = {
  parsePositiveNumber,
  resolveTerminalServerConfig,
};
