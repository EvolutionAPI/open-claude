const fs = require('fs');

const { PLATFORM_EVENTS_PATH } = require('./platform-support');

function parseJsonl(filePath) {
  if (!fs.existsSync(filePath)) {
    return [];
  }

  const raw = fs.readFileSync(filePath, 'utf8');
  if (!raw.trim()) {
    return [];
  }

  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

function createPlatformEventBroker(options = {}) {
  const eventsPath = options.eventsPath || PLATFORM_EVENTS_PATH;
  const pollIntervalMs = options.pollIntervalMs ?? 2000;
  const onEvent = typeof options.onEvent === 'function' ? options.onEvent : () => {};
  const dev = !!options.dev;
  const logger = options.logger || console;

  let stopped = false;
  let interval = null;
  let cursor = 0;

  const ensureCursor = () => {
    const events = parseJsonl(eventsPath);
    cursor = events.length;
  };

  const flush = () => {
    if (stopped) return;

    const events = parseJsonl(eventsPath);
    if (events.length < cursor) {
      cursor = 0;
    }

    const freshEvents = events.slice(cursor);
    cursor = events.length;

    for (const event of freshEvents) {
      try {
        onEvent(event);
      } catch (error) {
        if (dev) {
          logger.warn?.('[platform-event-broker] handler failed:', error?.message || error);
        }
      }
    }
  };

  ensureCursor();

  if (pollIntervalMs > 0) {
    interval = setInterval(flush, pollIntervalMs);
    if (typeof interval.unref === 'function') {
      interval.unref();
    }
  }

  return {
    eventsPath,
    stop() {
      stopped = true;
      if (interval) {
        clearInterval(interval);
        interval = null;
      }
    },
    flush,
    status() {
      return {
        backend: 'file-poll',
        active: !stopped,
        eventsPath,
        cursor,
      };
    },
  };
}

module.exports = {
  createPlatformEventBroker,
  parseJsonl,
};
