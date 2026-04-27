const assert = require('assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const test = require('node:test');

const { createPlatformEventBroker } = require('../src/platform-event-broker');

function makeTempDir(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

test('PlatformEventBroker emits newly appended JSONL events', () => {
  const tempDir = makeTempDir('evonexus-platform-broker-');
  const eventsPath = path.join(tempDir, 'events.jsonl');
  fs.writeFileSync(eventsPath, '', 'utf8');

  const seen = [];
  const broker = createPlatformEventBroker({
    eventsPath,
    pollIntervalMs: 0,
    onEvent: (event) => {
      seen.push(event);
    },
  });

  fs.appendFileSync(
    eventsPath,
    `${JSON.stringify({
      ts: new Date().toISOString(),
      topic: 'provider-active-updated',
      source: 'dashboard',
      payload: { provider_id: 'openai' },
    })}\n`,
    'utf8'
  );

  broker.flush();
  broker.stop();

  assert.equal(seen.length, 1);
  assert.equal(seen[0].topic, 'provider-active-updated');
  assert.equal(seen[0].payload.provider_id, 'openai');
});
