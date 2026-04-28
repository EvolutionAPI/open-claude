/**
 * ChatLogger — append-only JSONL logs for chat conversations.
 *
 * Stores chat messages in workspace/ADWs/logs/chat/{agentName}_{sessionId}.jsonl
 * Each line is a JSON object: { role, text?, blocks?, files?, ts, uuid? }
 *
 * Special event lines:
 *   { type: "rewind", at: <uuid>, ts }  — marks a rewind point; messages after
 *     the referenced uuid are considered dropped. The reader applies all rewind
 *     markers before returning results (append-only, no destructive truncation).
 *
 * This is the durable source of truth for chat history.
 * sessions.json is a fast-access cache; JSONL survives restarts and cleanups.
 *
 * PG mode (DATABASE_URL starts with "postgresql"):
 *   After every synchronous JSONL write, the message is enqueued to ChatSyncQueue
 *   for async delivery to POST /api/chat-messages.  JSONL is the Write-Ahead Log
 *   (WAL) — messages are never lost even if PG is temporarily unreachable.
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const ChatSyncQueue = require('./sync-queue');

class ChatLogger {
  /**
   * @param {string} workspaceRoot
   * @param {object} [opts]          - Passed through to ChatSyncQueue (retryIntervalMs, maxQueueSize)
   */
  constructor(workspaceRoot, opts = {}) {
    this.logsDir = path.join(workspaceRoot || process.cwd(), 'workspace', 'ADWs', 'logs', 'chat');
    this._ensureDir();

    // Activate PG sync only when DATABASE_URL points to PostgreSQL
    const dbUrl = process.env.DATABASE_URL || '';
    this.syncEnabled = dbUrl.startsWith('postgresql') || dbUrl.startsWith('postgres://');
    if (this.syncEnabled) {
      this.syncQueue = new ChatSyncQueue(workspaceRoot, opts);
    }
  }

  _ensureDir() {
    try {
      fs.mkdirSync(this.logsDir, { recursive: true });
    } catch {}
  }

  _logPath(agentName, sessionId) {
    const safe = (agentName || 'unknown').replace(/[^a-zA-Z0-9_-]/g, '_');
    const shortId = sessionId.slice(0, 8);
    return path.join(this.logsDir, `${safe}_${shortId}.jsonl`);
  }

  /**
   * Append a message to the chat log.
   * Assigns a uuid if the message doesn't already have one.
   * Returns the (possibly assigned) uuid.
   *
   * Write order: JSONL first (synchronous, durable WAL), then async PG sync.
   */
  append(agentName, sessionId, message) {
    try {
      if (!message.uuid) {
        message.uuid = crypto.randomUUID();
      }
      const logPath = this._logPath(agentName, sessionId);
      const line = JSON.stringify(message) + '\n';
      // 1. ALWAYS write to JSONL first — durable WAL
      fs.appendFileSync(logPath, line, 'utf8');
      // 2. If PG mode, enqueue for async sync to Flask
      if (this.syncEnabled) {
        this.syncQueue.enqueue(agentName, sessionId, message);
      }
      return message.uuid;
    } catch (err) {
      console.error(`[chat-logger] Failed to append: ${err.message}`);
      return null;
    }
  }

  /**
   * Append a rewind marker to the JSONL log.
   * The marker records which message uuid was rewound from.
   * In PG mode, also sends a best-effort POST /api/chat-messages/rewind.
   */
  appendRewindMarker(agentName, sessionId, atUuid) {
    try {
      const marker = { type: 'rewind', at: atUuid, ts: Date.now() };
      const logPath = this._logPath(agentName, sessionId);
      // 1. ALWAYS write marker to JSONL
      fs.appendFileSync(logPath, JSON.stringify(marker) + '\n', 'utf8');
      // 2. If PG mode, best-effort rewind via Flask (no retry)
      if (this.syncEnabled && this.syncQueue) {
        this.syncQueue._tryRewind(agentName, sessionId, atUuid).catch(() => {});
      }
    } catch (err) {
      console.error(`[chat-logger] Failed to append rewind marker: ${err.message}`);
    }
  }

  /**
   * Read full chat history from JSONL log, applying rewind markers.
   * Returns array of messages, or empty array if not found.
   *
   * Algorithm: play forward. When a { type:"rewind", at:<uuid> } line is
   * encountered, drop all messages strictly after the message with that uuid.
   * Legacy messages without uuid get synthesized deterministic ids.
   */
  read(agentName, sessionId) {
    try {
      const logPath = this._logPath(agentName, sessionId);
      if (!fs.existsSync(logPath)) return [];

      const content = fs.readFileSync(logPath, 'utf8').trim();
      if (!content) return [];

      const rawLines = [];
      for (const line of content.split('\n')) {
        if (!line.trim()) continue;
        try {
          rawLines.push(JSON.parse(line));
        } catch {
          // Skip malformed lines
        }
      }

      // First pass: assign synthesized uuids to legacy messages (no uuid, not a marker)
      let idx = 0;
      for (const entry of rawLines) {
        if (entry.type !== 'rewind' && !entry.uuid) {
          entry.uuid = `legacy-${sessionId}-${idx}`;
        }
        if (entry.type !== 'rewind') idx++;
      }

      // Second pass: play forward, applying rewind markers
      const messages = [];
      for (const entry of rawLines) {
        if (entry.type === 'rewind') {
          // Drop the message with entry.at uuid AND everything after it
          const cutIdx = messages.findIndex(m => m.uuid === entry.at);
          if (cutIdx !== -1) {
            messages.splice(cutIdx);
          }
          // If uuid not found (e.g. marker for already-rewound content), no-op
        } else {
          messages.push(entry);
        }
      }

      return messages;
    } catch (err) {
      console.error(`[chat-logger] Failed to read: ${err.message}`);
      return [];
    }
  }

  /**
   * Check if a log exists for a session.
   */
  exists(agentName, sessionId) {
    return fs.existsSync(this._logPath(agentName, sessionId));
  }
}

module.exports = ChatLogger;
