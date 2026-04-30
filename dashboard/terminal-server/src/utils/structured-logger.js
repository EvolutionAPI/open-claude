const util = require('util');

function serializeValue(value) {
  if (value instanceof Error) {
    return {
      name: value.name,
      message: value.message,
      stack: value.stack,
    };
  }

  if (value === null || value === undefined) {
    return value;
  }

  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return value;
  }

  if (Buffer.isBuffer(value)) {
    return {
      type: 'Buffer',
      length: value.length,
    };
  }

  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return util.inspect(value, { depth: 4, breakLength: 120 });
  }
}

function formatLogEntry(level, args, context = {}) {
  const normalizedArgs = args.map(serializeValue);
  const message = normalizedArgs
    .map((arg) => (typeof arg === 'string' ? arg : JSON.stringify(arg)))
    .join(' ');

  return {
    ts: new Date().toISOString(),
    level,
    service: context.service || 'terminal-server',
    component: context.component || 'console',
    pid: process.pid,
    message,
    args: normalizedArgs.length > 1 ? normalizedArgs : undefined,
  };
}

function installStructuredConsole(context = {}) {
  if (process.env.EVONEXUS_STRUCTURED_LOGS === '0') {
    return;
  }
  if (console.__evonexusStructuredInstalled) {
    return;
  }

  const writeEntry = (level, args) => {
    const entry = formatLogEntry(level, args, context);
    const target = level === 'error' || level === 'warn' ? process.stderr : process.stdout;
    target.write(`${JSON.stringify(entry)}\n`);
  };

  console.log = (...args) => writeEntry('info', args);
  console.info = (...args) => writeEntry('info', args);
  console.warn = (...args) => writeEntry('warn', args);
  console.error = (...args) => writeEntry('error', args);
  console.debug = (...args) => writeEntry('debug', args);
  console.__evonexusStructuredInstalled = true;
}

module.exports = {
  formatLogEntry,
  installStructuredConsole,
  serializeValue,
};
