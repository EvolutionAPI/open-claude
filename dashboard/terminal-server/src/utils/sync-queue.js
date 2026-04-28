'use strict';

/**
 * ChatSyncQueue — async WAL-replay queue for chat messages.
 *
 * Guarantees:
 *   1. JSONL is the primary durable store (written synchronously by chat-logger.js).
 *   2. This queue delivers each message to POST /api/chat-messages at least once.
 *   3. Duplicate deliveries are safe — the endpoint is idempotent (ON CONFLICT uuid).
 *   4. A .synced sidecar file tracks delivered UUIDs so retries skip already-sent messages.
 *   5. On queue overflow (> maxQueueSize bytes), pending items are spilled to a .pending sidecar.
 *
 * Recovery on boot:
 *   Call recoverPending(agentName, sessionId) after construction to replay
 *   any items from the .pending sidecar that were not yet delivered.
 */

const fs = require('fs');
const path = require('path');
const http = require('http');
const https = require('https');

class ChatSyncQueue {
  /**
   * @param {string} workspaceRoot  - Absolute path to workspace root
   * @param {object} opts
   * @param {number} [opts.retryIntervalMs=5000]  - Retry delay when queue still has items
   * @param {number} [opts.maxQueueSize=52428800] - Max in-memory queue size in bytes (default 50 MB)
   */
  constructor(workspaceRoot, opts = {}) {
    this.logsDir = path.join(
      workspaceRoot || process.cwd(),
      'workspace', 'ADWs', 'logs', 'chat',
    );
    this.apiBase = process.env.EVONEXUS_API_URL || 'http://localhost:8080';
    this.token = process.env.DASHBOARD_API_TOKEN || '';
    this.retryIntervalMs = opts.retryIntervalMs || 5000;
    this.maxQueueSizeBytes = opts.maxQueueSize || 50 * 1024 * 1024;

    /** @type {Array<{agentName: string, sessionId: string, message: object}>} */
    this.queue = [];
    this.running = false;
    this.timer = null;
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Enqueue a message for async delivery to the backend.
   * Spills to .pending sidecar if queue exceeds maxQueueSizeBytes.
   */
  enqueue(agentName, sessionId, message) {
    if (this._queueSizeBytes() > this.maxQueueSizeBytes) {
      this._spillToPending(agentName, sessionId, message);
      return;
    }
    this.queue.push({ agentName, sessionId, message });
    if (!this.running) {
      this.start();
    }
  }

  /**
   * Recover .pending sidecar messages on boot.
   * Only works if the caller provides the agentName + sessionId pair.
   * (The sidecar stores each line as {agentName, sessionId, message} JSON.)
   */
  recoverPending(agentName, sessionId) {
    const p = this._pendingPath(agentName, sessionId);
    if (!fs.existsSync(p)) return;
    try {
      const lines = fs.readFileSync(p, 'utf8').split('\n').filter(l => l.trim());
      for (const line of lines) {
        try {
          const item = JSON.parse(line);
          if (item.message && item.message.uuid) {
            this.queue.push({
              agentName: item.agentName || agentName,
              sessionId: item.sessionId || sessionId,
              message: item.message,
            });
          }
        } catch { /* skip malformed */ }
      }
      fs.unlinkSync(p);
      if (this.queue.length > 0 && !this.running) {
        this.start();
      }
    } catch (err) {
      console.error(`[chat-sync] recovery error for ${agentName}/${sessionId}: ${err.message}`);
    }
  }

  /** Start the drain loop (called automatically by enqueue). */
  start() {
    if (this.running) return;
    this.running = true;
    const tick = async () => {
      await this._drain();
      if (this.queue.length > 0) {
        this.timer = setTimeout(tick, this.retryIntervalMs);
      } else {
        this.running = false;
      }
    };
    tick();
  }

  /** Stop the drain loop (call on process exit). */
  stop() {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.running = false;
  }

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  _queueSizeBytes() {
    return this.queue.reduce((acc, item) => acc + JSON.stringify(item.message).length, 0);
  }

  /**
   * Returns the .synced sidecar path for a given agent + session.
   * Format: {logsDir}/{safe_agent}_{shortId}.synced
   */
  _syncedPath(agentName, sessionId) {
    const safe = (agentName || 'unknown').replace(/[^a-zA-Z0-9_-]/g, '_');
    const shortId = (sessionId || '').slice(0, 8);
    return path.join(this.logsDir, `${safe}_${shortId}.synced`);
  }

  /**
   * Returns the .pending sidecar path for overflow spill.
   * Format: {logsDir}/{safe_agent}_{shortId}.pending
   */
  _pendingPath(agentName, sessionId) {
    const safe = (agentName || 'unknown').replace(/[^a-zA-Z0-9_-]/g, '_');
    const shortId = (sessionId || '').slice(0, 8);
    return path.join(this.logsDir, `${safe}_${shortId}.pending`);
  }

  _markSynced(agentName, sessionId, uuid) {
    try {
      fs.appendFileSync(this._syncedPath(agentName, sessionId), uuid + '\n', 'utf8');
    } catch (err) {
      console.error(`[chat-sync] mark-synced failed: ${err.message}`);
    }
  }

  _isSynced(agentName, sessionId, uuid) {
    const p = this._syncedPath(agentName, sessionId);
    if (!fs.existsSync(p)) return false;
    try {
      return fs.readFileSync(p, 'utf8').split('\n').includes(uuid);
    } catch {
      return false;
    }
  }

  _spillToPending(agentName, sessionId, message) {
    const p = this._pendingPath(agentName, sessionId);
    try {
      // Store full context so recoverPending can reconstruct the item
      const entry = JSON.stringify({ agentName, sessionId, message }) + '\n';
      fs.appendFileSync(p, entry, 'utf8');
    } catch (err) {
      console.error(`[chat-sync] spill failed: ${err.message}`);
    }
  }

  /**
   * Attempt to POST one message to the backend.
   * Returns true on success (201) or if the message is already marked synced.
   * Returns false on network error or non-201 response (will retry).
   */
  async _trySync(item) {
    const { agentName, sessionId, message } = item;
    if (this._isSynced(agentName, sessionId, message.uuid)) return true;

    return new Promise((resolve) => {
      const body = JSON.stringify({
        agent_name: agentName,
        session_id: sessionId,
        role: message.role,
        text: message.text || null,
        blocks: message.blocks || null,
        files: message.files || null,
        uuid: message.uuid,
        ts: new Date(message.ts || Date.now()).toISOString(),
      });

      let url;
      try {
        url = new URL('/api/chat-messages', this.apiBase);
      } catch {
        resolve(false);
        return;
      }

      const transport = url.protocol === 'https:' ? https : http;
      const req = transport.request(
        {
          hostname: url.hostname,
          port: url.port || (url.protocol === 'https:' ? 443 : 80),
          path: url.pathname,
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(body),
            ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
          },
          timeout: 5000,
        },
        (res) => {
          if (res.statusCode === 201) {
            this._markSynced(agentName, sessionId, message.uuid);
            resolve(true);
          } else {
            resolve(false);
          }
          res.resume(); // drain response body
        },
      );

      req.on('error', () => resolve(false));
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
      req.write(body);
      req.end();
    });
  }

  /**
   * POST rewind marker to backend (best-effort, no retry).
   */
  async _tryRewind(agentName, sessionId, atUuid) {
    return new Promise((resolve) => {
      const body = JSON.stringify({ session_id: sessionId, at_uuid: atUuid });
      let url;
      try {
        url = new URL('/api/chat-messages/rewind', this.apiBase);
      } catch {
        resolve(false);
        return;
      }

      const transport = url.protocol === 'https:' ? https : http;
      const req = transport.request(
        {
          hostname: url.hostname,
          port: url.port || (url.protocol === 'https:' ? 443 : 80),
          path: url.pathname,
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(body),
            ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
          },
          timeout: 5000,
        },
        (res) => {
          resolve(res.statusCode === 200);
          res.resume();
        },
      );

      req.on('error', () => resolve(false));
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
      req.write(body);
      req.end();
    });
  }

  /** Process all queued items; leave failed ones for next retry cycle. */
  async _drain() {
    const stillPending = [];
    for (const item of this.queue) {
      const ok = await this._trySync(item);
      if (!ok) stillPending.push(item);
    }
    this.queue = stillPending;
  }
}

module.exports = ChatSyncQueue;
