const express = require('express');
const http = require('http');
const path = require('path');
const fs = require('fs');
const WebSocket = require('ws');
const cors = require('cors');
const { v4: uuidv4 } = require('uuid');
const ClaudeBridge = require('./claude-bridge');
const { ChatBridge } = require('./chat-bridge');
const { registerTerminalHttpRoutes } = require('./http-routes');
const { resolveTerminalServerConfig } = require('./runtime-config');
const SessionStore = require('./utils/session-store');
const ChatLogger = require('./utils/chat-logger');
const TerminalAuditLog = require('./utils/terminal-audit-log');
const { createPlatformEventBroker } = require('./platform-event-broker');
const { loadProviderConfig, getProviderMode } = require('./provider-config');

class TerminalServer {
  constructor(options = {}) {
    const runtimeConfig = resolveTerminalServerConfig(options);
    this.port = runtimeConfig.port;
    this.dev = runtimeConfig.dev;
    this.baseFolder = runtimeConfig.baseFolder;
    this.sessionTtlMs = runtimeConfig.sessionTtlMs;
    this.sessionGcIntervalMs = runtimeConfig.sessionGcIntervalMs;
    this.autoSaveIntervalMs = runtimeConfig.autoSaveIntervalMs;
    this.sessionSaveDebounceMs = runtimeConfig.sessionSaveDebounceMs;
    this.wsHeartbeatTimeoutMs = runtimeConfig.wsHeartbeatTimeoutMs;
    this.wsHeartbeatSweepIntervalMs = runtimeConfig.wsHeartbeatSweepIntervalMs;

    this.app = express();
    this.claudeSessions = new Map();
    this.webSocketConnections = new Map();
    this.globalSubscribers = new Set(); // wsIds subscribed to global notifications
    this.claudeBridge = new ClaudeBridge();
    this.chatBridge = new ChatBridge();
    this.sessionStore = new SessionStore({ sessionTtlMs: this.sessionTtlMs });
    this.chatLogger = new ChatLogger(this.baseFolder);
    this.auditLogger = new TerminalAuditLog(this.baseFolder);
    this.platformEvents = [];
    this.platformEventBroker = createPlatformEventBroker({
      onEvent: (event) => this.handlePlatformEvent(event),
      dev: this.dev,
    });
    this.autoSaveInterval = null;
    this.sessionGcInterval = null;
    this.wsHeartbeatInterval = null;
    this._sessionSaveTimer = null;
    this._sessionSavePromise = null;
    this._sessionSaveResolve = null;
    this.isShuttingDown = false;
    this._beforeExitSaved = false;
    this._handleSigint = () => this.handleShutdown();
    this._handleSigterm = () => this.handleShutdown();
    this._handleBeforeExit = () => {
      if (this._beforeExitSaved) return;
      this._beforeExitSaved = true;
      void this.saveSessionsToDisk();
    };
    this.ready = this.loadPersistedSessions();

    this.setupExpress();
    this.setupAutoSave();
    this.setupSessionGc();
    this.setupHeartbeatMonitor();
  }

  async loadPersistedSessions() {
    try {
      const sessions = await this.sessionStore.loadSessions();
      this.claudeSessions = sessions;
      if (sessions.size > 0) {
        console.log(`Loaded ${sessions.size} persisted sessions`);
      }
    } catch (error) {
      console.error('Failed to load persisted sessions:', error);
    }
  }

  setupAutoSave() {
    if (this.autoSaveIntervalMs > 0) {
      this.autoSaveInterval = setInterval(() => {
        this.requestSessionSave();
      }, this.autoSaveIntervalMs);
    }

    process.on('SIGINT', this._handleSigint);
    process.on('SIGTERM', this._handleSigterm);
    process.on('beforeExit', this._handleBeforeExit);
  }

  setupSessionGc() {
    if (this.sessionGcIntervalMs <= 0) {
      return;
    }

    this.sessionGcInterval = setInterval(() => {
      void this.purgeStaleSessions();
    }, this.sessionGcIntervalMs);
  }

  setupHeartbeatMonitor() {
    if (this.wsHeartbeatSweepIntervalMs <= 0 || this.wsHeartbeatTimeoutMs <= 0) {
      return;
    }

    this.wsHeartbeatInterval = setInterval(() => {
      void this.purgeStaleWebSocketConnections();
    }, this.wsHeartbeatSweepIntervalMs);
  }

  async saveSessionsToDisk() {
    if (this._sessionSaveTimer) {
      clearTimeout(this._sessionSaveTimer);
      this._sessionSaveTimer = null;
      this._sessionSaveResolve = null;
      this._sessionSavePromise = null;
    }
    if (this.claudeSessions.size === 0 && !fs.existsSync(this.sessionStore.sessionsFile)) {
      return true;
    }
    return await this.sessionStore.saveSessions(this.claudeSessions);
  }

  requestSessionSave() {
    if (this._sessionSaveTimer) {
      return this._sessionSavePromise || Promise.resolve(false);
    }

    this._sessionSavePromise = new Promise((resolve) => {
      this._sessionSaveResolve = resolve;
    });

    this._sessionSaveTimer = setTimeout(async () => {
      this._sessionSaveTimer = null;
      try {
        const result = await this.saveSessionsToDisk();
        this._sessionSaveResolve?.(result);
      } catch (error) {
        this._sessionSaveResolve?.(false);
        if (this.dev) console.error('Failed to save sessions after debounce:', error);
      } finally {
        this._sessionSaveResolve = null;
        this._sessionSavePromise = null;
      }
    }, this.sessionSaveDebounceMs);

    if (typeof this._sessionSaveTimer.unref === 'function') {
      this._sessionSaveTimer.unref();
    }

    return this._sessionSavePromise;
  }

  recordAuditEvent(action, wsInfo, target, extra = {}) {
    if (!this.auditLogger) return;
    this.auditLogger.append({
      action,
      actor: {
        wsId: wsInfo?.id || null,
        remoteAddress: wsInfo?.remoteAddress || null,
      },
      target,
      ...extra,
    });
  }

  handlePlatformEvent(event) {
    if (!event || typeof event !== 'object') {
      return;
    }

    this.platformEvents.push(event);
    if (this.platformEvents.length > 100) {
      this.platformEvents.shift();
    }

    if (this.dev) {
      console.log(`[platform-event] ${event.topic || 'unknown'} from ${event.source || 'unknown'}`);
    }

    this.broadcastToGlobalSubscribers({
      type: 'platform_event',
      event,
    });
  }

  async purgeStaleWebSocketConnections() {
    const now = Date.now();
    let closed = 0;

    for (const [wsId, wsInfo] of this.webSocketConnections.entries()) {
      const lastHeartbeatAt = Number(wsInfo.lastHeartbeatAt || 0);
      if (!lastHeartbeatAt || (now - lastHeartbeatAt) <= this.wsHeartbeatTimeoutMs) {
        continue;
      }

      if (this.dev) {
        console.warn(`Closing stale WebSocket ${wsId} after ${now - lastHeartbeatAt}ms without heartbeat`);
      }

      this.recordAuditEvent(
        'ws_timeout',
        wsInfo,
        { wsId, sessionId: wsInfo.claudeSessionId || null },
        { elapsedMs: now - lastHeartbeatAt },
      );

      try {
        if (typeof wsInfo.ws.terminate === 'function') {
          wsInfo.ws.terminate();
        } else if (typeof wsInfo.ws.close === 'function') {
          wsInfo.ws.close(4000, 'Heartbeat timeout');
        }
      } catch {}

      this.cleanupWebSocketConnection(wsId);
      closed += 1;
    }

    return { closed };
  }

  _checkPathAccess(targetPath, requireWrite = false) {
    try {
      const mode = requireWrite ? fs.constants.R_OK | fs.constants.W_OK : fs.constants.R_OK;
      fs.accessSync(targetPath, mode);
      return { status: 'ok', path: targetPath };
    } catch (error) {
      return {
        status: 'error',
        path: targetPath,
        detail: error.message,
      };
    }
  }

  _getProviderHealth() {
    try {
      const providerConfig = loadProviderConfig() || {};
      const providerMode = getProviderMode(providerConfig);
      const active = providerConfig.active || 'none';
      const routing = providerConfig.routing || { enabled: true, failover_order: [active] };
      if (!active || active === 'none') {
        return { status: 'warning', active, routing, detail: 'No provider configured' };
      }
      if (active !== 'anthropic' && providerMode !== 'code') {
        return {
          status: 'warning',
          active,
          mode: providerMode,
          routing,
          detail: `Provider ${active} is not in code mode`,
        };
      }
      return {
        status: 'ok',
        active,
        mode: providerMode,
        routing,
      };
    } catch (error) {
      return {
        status: 'error',
        detail: error.message,
      };
    }
  }

  getHealthSnapshot(deep = false) {
    const now = Date.now();
    let staleSessions = 0;
    for (const session of this.claudeSessions.values()) {
      if (this.sessionStore.isSessionStale(session, now)) {
        staleSessions += 1;
      }
    }

    const checks = {
      storage: this._checkPathAccess(this.sessionStore.storageDir, true),
      sessions_file: fs.existsSync(this.sessionStore.sessionsFile)
        ? this._checkPathAccess(this.sessionStore.sessionsFile, false)
        : { status: 'warning', path: this.sessionStore.sessionsFile, detail: 'Sessions file not created yet' },
      workspace: this._checkPathAccess(this.baseFolder, false),
    };

    if (deep) {
      checks.providers = this._getProviderHealth();
    }

    const statuses = Object.values(checks).map((check) => check.status);
    const status = statuses.includes('error')
      ? 'error'
      : (statuses.includes('warning') ? 'warning' : 'ok');

    return {
      status,
      timestamp: new Date().toISOString(),
      uptime_seconds: Math.round(process.uptime()),
      counts: {
        claudeSessions: this.claudeSessions.size,
        activeSessions: Array.from(this.claudeSessions.values()).filter((s) => s.active).length,
        staleSessions,
        webSocketConnections: this.webSocketConnections.size,
        globalSubscribers: this.globalSubscribers.size,
      claudeBridgeSessions: this.claudeBridge.sessions.size,
      chatBridgeSessions: this.chatBridge.sessions.size,
      platformEvents: this.platformEvents.length,
    },
    memory: process.memoryUsage(),
    checks,
  };
  }

  async purgeStaleSessions() {
    const now = Date.now();
    const staleEntries = [];
    for (const [sessionId, session] of this.claudeSessions.entries()) {
      if (this.sessionStore.isSessionStale(session, now)) {
        staleEntries.push([sessionId, session]);
      }
    }

    if (staleEntries.length === 0) {
      return { removed: 0 };
    }

    let removed = 0;
    for (const [sessionId, session] of staleEntries) {
      if (session.active) {
        continue;
      }

      const claudeSession = this.claudeBridge.getSession(sessionId);
      if (claudeSession && claudeSession.active) {
        continue;
      }
      const chatSession = this.chatBridge.getSession(sessionId);
      if (chatSession && chatSession.active) {
        continue;
      }

      this.claudeSessions.delete(sessionId);
      removed += 1;

      try {
        await Promise.allSettled([
          this.claudeBridge.stopSession(sessionId),
          this.chatBridge.stopSession(sessionId),
        ]);
      } catch (error) {
        if (this.dev) console.warn(`Failed to clean stale session ${sessionId}:`, error.message);
      }
    }

    await this.saveSessionsToDisk();
    return { removed };
  }

  async handleShutdown() {
    if (this.isShuttingDown) return;
    this.isShuttingDown = true;
    console.log('\nGracefully shutting down...');
    if (this._sessionSaveTimer) {
      clearTimeout(this._sessionSaveTimer);
      this._sessionSaveTimer = null;
      this._sessionSaveResolve = null;
      this._sessionSavePromise = null;
    }
    process.removeListener('SIGINT', this._handleSigint);
    process.removeListener('SIGTERM', this._handleSigterm);
    process.removeListener('beforeExit', this._handleBeforeExit);
    this._beforeExitSaved = true;
    await this.saveSessionsToDisk();
    if (this.autoSaveInterval) clearInterval(this.autoSaveInterval);
    if (this.sessionGcInterval) clearInterval(this.sessionGcInterval);
    if (this.wsHeartbeatInterval) clearInterval(this.wsHeartbeatInterval);
    if (this.platformEventBroker) this.platformEventBroker.stop();
    this.close();
    process.exit(0);
  }

  isPathWithinBase(targetPath) {
    try {
      const resolvedTarget = path.resolve(targetPath);
      const resolvedBase = path.resolve(this.baseFolder);
      return resolvedTarget.startsWith(resolvedBase);
    } catch {
      return false;
    }
  }

  validatePath(targetPath) {
    if (!targetPath) return { valid: false, error: 'Path is required' };
    const resolvedPath = path.resolve(targetPath);
    if (!this.isPathWithinBase(resolvedPath)) {
      return { valid: false, error: 'Access denied: Path is outside the allowed directory' };
    }
    return { valid: true, path: resolvedPath };
  }

  setupExpress() {
    this.app.use(cors());
    this.app.use(express.json());
    registerTerminalHttpRoutes(this.app, this);
  }

  async start() {
    await this.ready;
    const server = http.createServer(this.app);

    this.wss = new WebSocket.Server({ server });
    this.wss.on('connection', (ws, req) => this.handleWebSocketConnection(ws, req));

    return new Promise((resolve, reject) => {
      server.listen(this.port, '0.0.0.0', (err) => {
        if (err) return reject(err);
        this.server = server;
        resolve(server);
      });
    });
  }

  handleWebSocketConnection(ws, req) {
    const wsId = uuidv4();
    const url = new URL(req.url, 'ws://localhost');
    const claudeSessionId = url.searchParams.get('sessionId');
    const remoteAddress = req.socket?.remoteAddress || req.headers['x-forwarded-for'] || 'unknown';

    if (this.dev) console.log(`New WebSocket connection: ${wsId}`);

    const wsInfo = {
      id: wsId,
      ws,
      claudeSessionId: null,
      created: new Date(),
      lastHeartbeatAt: Date.now(),
      remoteAddress,
      userAgent: req.headers['user-agent'] || null,
    };
    this.webSocketConnections.set(wsId, wsInfo);
    this.recordAuditEvent('ws_connected', wsInfo, { wsId }, { sessionId: claudeSessionId || null });

    // Send pending chat history if session is in chat mode
    if (claudeSessionId) {
      const sess = this.claudeSessions.get(claudeSessionId);
      if (sess?.chatHistory?.length > 0) {
        this.sendToWebSocket(ws, { type: 'chat_history', messages: sess.chatHistory });
      }
    }

    ws.on('message', async (message) => {
      try {
        const data = JSON.parse(message);
        await this.handleMessage(wsId, data);
      } catch (error) {
        if (this.dev) console.error('Error handling message:', error);
        this.sendToWebSocket(ws, { type: 'error', message: 'Failed to process message' });
      }
    });

    ws.on('close', () => {
      if (this.dev) console.log(`WebSocket connection closed: ${wsId}`);
      this.recordAuditEvent('ws_closed', wsInfo, { wsId, sessionId: wsInfo.claudeSessionId || null });
      this.cleanupWebSocketConnection(wsId);
    });

    ws.on('error', (error) => {
      if (this.dev) console.error(`WebSocket error for connection ${wsId}:`, error);
      this.cleanupWebSocketConnection(wsId);
    });

    this.sendToWebSocket(ws, { type: 'connected', connectionId: wsId });

    if (claudeSessionId && this.claudeSessions.has(claudeSessionId)) {
      this.joinClaudeSession(wsId, claudeSessionId);
    }
  }

  async handleMessage(wsId, data) {
    const wsInfo = this.webSocketConnections.get(wsId);
    if (!wsInfo) return;

    switch (data.type) {
      case 'subscribe_global':
        this.globalSubscribers.add(wsId);
        break;

      case 'unsubscribe_global':
        this.globalSubscribers.delete(wsId);
        break;

      case 'join_session':
        await this.joinClaudeSession(wsId, data.sessionId);
        break;

      case 'leave_session':
        await this.leaveClaudeSession(wsId);
        break;

      case 'start_claude':
        await this.startClaude(wsId, data.options || {});
        break;

      case 'input':
        if (wsInfo.claudeSessionId) {
          const session = this.claudeSessions.get(wsInfo.claudeSessionId);
          if (session && session.connections.has(wsId) && session.active && session.agent === 'claude') {
            try {
              await this.claudeBridge.sendInput(wsInfo.claudeSessionId, data.data);
            } catch (error) {
              if (this.dev) console.error(`Failed to send input to session ${wsInfo.claudeSessionId}:`, error.message);
              this.sendToWebSocket(wsInfo.ws, {
                type: 'error',
                message: 'Agent is not running in this session. Please start an agent first.',
              });
            }
          }
        }
        break;

      case 'chat_send':
        // Send a chat message via Agent SDK
        if (wsInfo.claudeSessionId) {
          const chatSession = this.claudeSessions.get(wsInfo.claudeSessionId);
          if (chatSession && data.prompt) {
            chatSession.mode = 'chat';
            chatSession.active = true;
            chatSession.lastActivity = new Date();
            if (!chatSession.chatHistory) chatSession.chatHistory = [];

            // --- Rewind handling ---
            if (data.rewindFromUuid) {
              const rewindUuid = data.rewindFromUuid;

              // Find uuid in in-memory cache
              let cutIdx = chatSession.chatHistory.findIndex(m => m.uuid === rewindUuid);

              // Fall back to JSONL scan if cache is cold or uuid not found
              if (cutIdx === -1 && chatSession.agentName) {
                const fromLog = this.chatLogger.read(chatSession.agentName, wsInfo.claudeSessionId);
                cutIdx = fromLog.findIndex(m => m.uuid === rewindUuid);
                if (cutIdx !== -1) {
                  // Sync cache from JSONL
                  chatSession.chatHistory = fromLog;
                  cutIdx = chatSession.chatHistory.findIndex(m => m.uuid === rewindUuid);
                }
              }

              if (cutIdx === -1) {
                // uuid not found — error out without mutating state
                this.sendToWebSocket(wsInfo.ws, {
                  type: 'chat_error',
                  message: `Rewind target not found: ${rewindUuid}`,
                });
                chatSession.active = false;
                break;
              }

              // 1. If a turn is streaming, stop it first
              if (this.chatBridge.isActive(wsInfo.claudeSessionId)) {
                await this.chatBridge.stopSession(wsInfo.claudeSessionId);
              }

              // 2. Null out sdkSessionId so the next turn starts fresh
              chatSession.sdkSessionId = null;
              await this.saveSessionsToDisk();

              // 3. Truncate in-memory cache to everything strictly before rewindUuid
              chatSession.chatHistory = chatSession.chatHistory.slice(0, cutIdx);

              // 4. Append rewind marker to JSONL
              this.chatLogger.appendRewindMarker(chatSession.agentName, wsInfo.claudeSessionId, rewindUuid);
            }
            // --- End rewind handling ---

            // Store user message in history
            const userMsg = {
              role: 'user',
              text: data.prompt,
              files: data.files || undefined,
              ts: Date.now(),
            };
            chatSession.chatHistory.push(userMsg);
            this.chatLogger.append(chatSession.agentName, wsInfo.claudeSessionId, userMsg);
            this.recordAuditEvent(
              'chat_send',
              wsInfo,
              { wsId, sessionId: wsInfo.claudeSessionId },
              {
                promptChars: String(data.prompt).length,
                filesCount: Array.isArray(data.files) ? data.files.length : 0,
                rewindFromUuid: data.rewindFromUuid || null,
              },
            );

            // Accumulate assistant response for history
            let assistantBlocks = [];
            let isStreaming = false;

            try {
              await this.chatBridge.startSession(wsInfo.claudeSessionId, {
                agentName: chatSession.agentName,
                workingDir: chatSession.workingDir,
                prompt: data.prompt,
                files: data.files,
                sdkSessionId: chatSession.sdkSessionId || undefined,
                systemPromptExtras: chatSession.systemPromptExtras || undefined,
                onMessage: (msg) => {
                  // Track SDK session ID
                  if (msg.type === 'session_id' && msg.sdkSessionId) {
                    chatSession.sdkSessionId = msg.sdkSessionId;
                    return; // Don't forward internal event
                  }

                  // Forward permission requests to the WebSocket client.
                  if (msg.type === 'permission_request') {
                    const permPayload = {
                      type: 'permission_request',
                      sessionId: wsInfo.claudeSessionId,
                      requestId: msg.requestId,
                      toolName: msg.toolName,
                      input: msg.input,
                      title: msg.title || null,
                      description: msg.description || null,
                    };
                    this.broadcastToSession(wsInfo.claudeSessionId, permPayload);
                    // Global notification
                    const createdAt = Date.now();
                    const inputPreview = msg.input
                      ? (typeof msg.input === 'string' ? msg.input : JSON.stringify(msg.input)).slice(0, 80)
                      : undefined;
                    this.broadcastToGlobalSubscribers({
                      type: 'notification',
                      id: `agent_awaiting-${wsInfo.claudeSessionId}-${msg.requestId}`,
                      event: 'agent_awaiting',
                      sessionId: wsInfo.claudeSessionId,
                      agentName: chatSession.agentName || '',
                      toolName: msg.toolName,
                      inputPreview,
                      createdAt,
                    }, wsInfo.claudeSessionId);
                    return;
                  }

                  // Auto-bind session to a ticket when the agent creates one.
                  // Only binds if not already bound — doesn't overwrite user's manual pick.
                  if (msg.type === 'ticket_detected' && msg.ticketId) {
                    if (!chatSession.ticketId) {
                      chatSession.ticketId = msg.ticketId;
                      this.broadcastToSession(wsInfo.claudeSessionId, {
                        type: 'ticket_bound',
                        ticketId: msg.ticketId,
                        auto: true,
                      });
                    }
                    return;
                  }

                  // Build assistant blocks for history
                  if (msg.type === 'text_start' || msg.type === 'message_start') {
                    if (!isStreaming) {
                      isStreaming = true;
                      assistantBlocks = [];
                    }
                  }
                  if (msg.type === 'text_delta') {
                    const last = assistantBlocks[assistantBlocks.length - 1];
                    if (last?.type === 'text') {
                      last.text += msg.text || '';
                    } else {
                      assistantBlocks.push({ type: 'text', text: msg.text || '' });
                    }
                  }
                  if (msg.type === 'tool_use_start') {
                    assistantBlocks.push({
                      type: 'tool_use',
                      toolName: msg.toolName,
                      toolId: msg.toolId,
                      input: '',
                      done: false,
                    });
                  }
                  if (msg.type === 'tool_input_delta') {
                    const last = assistantBlocks[assistantBlocks.length - 1];
                    if (last?.type === 'tool_use') {
                      last.input += msg.json || '';
                    }
                  }
                  if (msg.type === 'block_stop') {
                    const last = assistantBlocks[assistantBlocks.length - 1];
                    if (last?.type === 'tool_use') last.done = true;
                  }

                  // Also broadcast the current assistant blocks for live history
                  this.broadcastToSession(wsInfo.claudeSessionId, { type: 'chat_event', event: msg });
                },
                onError: (err) => {
                  chatSession.active = false;
                  this.broadcastToSession(wsInfo.claudeSessionId, {
                    type: 'chat_error',
                    message: err.message || 'Unknown error',
                  });
                },
                onComplete: (info) => {
                  chatSession.active = false;
                  // Store SDK session ID for future resume
                  if (info?.sdkSessionId) {
                    chatSession.sdkSessionId = info.sdkSessionId;
                  }
                  // Save assistant message to history
                  if (assistantBlocks.length > 0) {
                    const assistantMsg = {
                      role: 'assistant',
                      blocks: assistantBlocks,
                      ts: Date.now(),
                      streaming: false,
                    };
                    chatSession.chatHistory.push(assistantMsg);
                    this.chatLogger.append(chatSession.agentName, wsInfo.claudeSessionId, assistantMsg);
                  }
                  this.requestSessionSave();
                  this.broadcastToSession(wsInfo.claudeSessionId, { type: 'chat_complete' });
                  // Global notification — skip if a client is already watching this session
                  const hasWatcher = chatSession.connections && chatSession.connections.size > 0;
                  if (!hasWatcher) {
                    this.broadcastToGlobalSubscribers({
                      type: 'notification',
                      id: `agent_finished-${wsInfo.claudeSessionId}-${Date.now()}`,
                      event: 'agent_finished',
                      sessionId: wsInfo.claudeSessionId,
                      agentName: chatSession.agentName || '',
                      createdAt: Date.now(),
                    }, wsInfo.claudeSessionId);
                  }
                },
              });
            } catch (err) {
              console.error('[chat_send] Error starting chat session:', err);
              chatSession.active = false;
              this.sendToWebSocket(wsInfo.ws, { type: 'chat_error', message: err.message || String(err) });
            }
          }
        }
        break;

      case 'chat_stop':
        if (wsInfo.claudeSessionId) {
          this.recordAuditEvent('chat_stop', wsInfo, { wsId, sessionId: wsInfo.claudeSessionId });
          await this.chatBridge.stopSession(wsInfo.claudeSessionId);
          const s = this.claudeSessions.get(wsInfo.claudeSessionId);
          if (s) s.active = false;
          this.requestSessionSave();
        }
        break;

      case 'permission_response':
        if (wsInfo.claudeSessionId && data.requestId !== undefined) {
          this.recordAuditEvent(
            'permission_response',
            wsInfo,
            { wsId, sessionId: wsInfo.claudeSessionId, requestId: data.requestId },
            { approved: !!data.approved },
          );
          this.chatBridge.respondToApproval(wsInfo.claudeSessionId, data.requestId, !!data.approved);
        }
        break;

      case 'resize':
        if (wsInfo.claudeSessionId) {
          const session = this.claudeSessions.get(wsInfo.claudeSessionId);
          if (session && session.connections.has(wsId) && session.active && session.agent === 'claude') {
            try {
              await this.claudeBridge.resize(wsInfo.claudeSessionId, data.cols, data.rows);
            } catch {
              if (this.dev) console.log(`Resize ignored - agent not active in session ${wsInfo.claudeSessionId}`);
            }
          }
        }
        break;

      case 'stop':
        if (wsInfo.claudeSessionId) {
          this.recordAuditEvent('stop_request', wsInfo, { wsId, sessionId: wsInfo.claudeSessionId });
          await this.stopClaude(wsInfo.claudeSessionId);
        }
        break;

      case 'ping':
        wsInfo.lastHeartbeatAt = Date.now();
        this.sendToWebSocket(wsInfo.ws, { type: 'pong' });
        break;

      default:
        if (this.dev) console.log(`Unknown message type: ${data.type}`);
    }
  }

  async joinClaudeSession(wsId, claudeSessionId) {
    const wsInfo = this.webSocketConnections.get(wsId);
    if (!wsInfo) return;

    const session = this.claudeSessions.get(claudeSessionId);
    if (!session) {
      this.sendToWebSocket(wsInfo.ws, { type: 'error', message: 'Session not found' });
      return;
    }

    if (wsInfo.claudeSessionId) await this.leaveClaudeSession(wsId);

    wsInfo.claudeSessionId = claudeSessionId;
    this.recordAuditEvent('join_session', wsInfo, { wsId, sessionId: claudeSessionId });
    session.connections.add(wsId);
    session.lastActivity = new Date();
    session.lastAccessed = Date.now();

    // Restore chat history from JSONL logs if session cache is empty
    let chatHistory = session.chatHistory || [];
    if (chatHistory.length === 0 && session.agentName && session.mode === 'chat') {
      const restored = this.chatLogger.read(session.agentName, claudeSessionId);
      if (restored.length > 0) {
        session.chatHistory = restored;
        chatHistory = restored;
        if (this.dev) console.log(`[chat-logger] Restored ${restored.length} messages for session ${claudeSessionId}`);
      }
    }

    this.sendToWebSocket(wsInfo.ws, {
      type: 'session_joined',
      sessionId: claudeSessionId,
      sessionName: session.name,
      workingDir: session.workingDir,
      active: session.active,
      outputBuffer: session.outputBuffer.slice(-200),
      chatHistory,
      ticketId: session.ticketId || null,
    });

    if (this.dev) console.log(`WebSocket ${wsId} joined session ${claudeSessionId}`);
  }

  async leaveClaudeSession(wsId) {
    const wsInfo = this.webSocketConnections.get(wsId);
    if (!wsInfo || !wsInfo.claudeSessionId) return;

    this.recordAuditEvent('leave_session', wsInfo, { wsId, sessionId: wsInfo.claudeSessionId });
    const session = this.claudeSessions.get(wsInfo.claudeSessionId);
    if (session) {
      session.connections.delete(wsId);
      session.lastActivity = new Date();
    }

    wsInfo.claudeSessionId = null;
    this.sendToWebSocket(wsInfo.ws, { type: 'session_left' });
  }

  async startClaude(wsId, options) {
    const wsInfo = this.webSocketConnections.get(wsId);
    if (!wsInfo || !wsInfo.claudeSessionId) {
      this.sendToWebSocket(wsInfo?.ws, { type: 'error', message: 'No session joined' });
      return;
    }

    const session = this.claudeSessions.get(wsInfo.claudeSessionId);
    if (!session) return;

    if (session.active) {
      // Frontend may re-send start_claude on WebSocket reconnect (common
      // through reverse proxies like Traefik). The session is already
      // running — replay the buffer and tell the client it's attached
      // instead of surfacing a misleading error toast.
      this.sendToWebSocket(wsInfo.ws, { type: 'claude_started', sessionId: wsInfo.claudeSessionId });
      return;
    }

    const sessionId = wsInfo.claudeSessionId;

    try {
      // Ensure agent name from session is passed even if options don't include it
      const agentForSession = (options && options.agent) || session.agentName || null;
      if (this.dev) console.log(`Starting agent: ${agentForSession} for session ${sessionId}`);

      console.log(`[startClaude] Agent for session: ${agentForSession}, options.agent: ${options?.agent}`);
      await this.claudeBridge.startSession(sessionId, {
        ...options,
        workingDir: session.workingDir,
        agent: agentForSession,
        onOutput: (data) => {
          const currentSession = this.claudeSessions.get(sessionId);
          if (!currentSession) return;
          currentSession.outputBuffer.push(data);
          if (currentSession.outputBuffer.length > currentSession.maxBufferSize) {
            currentSession.outputBuffer.shift();
          }
          this.broadcastToSession(sessionId, { type: 'output', data });
        },
        onExit: (code, signal) => {
          const currentSession = this.claudeSessions.get(sessionId);
          if (currentSession) currentSession.active = false;
          this.broadcastToSession(sessionId, { type: 'exit', code, signal });
        },
        onError: (error) => {
          const currentSession = this.claudeSessions.get(sessionId);
          if (currentSession) currentSession.active = false;
          this.broadcastToSession(sessionId, { type: 'error', message: error.message });
        },
      });

      session.active = true;
      session.agent = 'claude';
      if (options && options.agent) session.agentName = options.agent;
      session.lastActivity = new Date();
      if (!session.sessionStartTime) session.sessionStartTime = new Date();
      this.recordAuditEvent('start_claude', wsInfo, { wsId, sessionId }, { agent: agentForSession || null });

      this.broadcastToSession(sessionId, { type: 'claude_started', sessionId });
    } catch (error) {
      if (this.dev) console.error(`Error starting Claude in session ${wsInfo.claudeSessionId}:`, error);
      this.sendToWebSocket(wsInfo.ws, { type: 'error', message: `Failed to start Claude Code: ${error.message}` });
    }
  }

  async stopClaude(claudeSessionId) {
    const session = this.claudeSessions.get(claudeSessionId);
    if (!session || !session.active) return;

    await this.claudeBridge.stopSession(claudeSessionId);
    session.active = false;
    session.agent = null;
    session.lastActivity = new Date();
    const wsInfo = [...this.webSocketConnections.values()].find((item) => item.claudeSessionId === claudeSessionId) || null;
    this.recordAuditEvent('stop_claude', wsInfo, { sessionId: claudeSessionId });
    this.requestSessionSave();

    this.broadcastToSession(claudeSessionId, { type: 'claude_stopped' });
  }

  sendToWebSocket(ws, data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  }

  broadcastToSession(claudeSessionId, data) {
    const session = this.claudeSessions.get(claudeSessionId);
    if (!session) return;

    session.connections.forEach(wsId => {
      const wsInfo = this.webSocketConnections.get(wsId);
      if (wsInfo && wsInfo.claudeSessionId === claudeSessionId && wsInfo.ws.readyState === WebSocket.OPEN) {
        this.sendToWebSocket(wsInfo.ws, data);
      }
    });
  }

  /**
   * Broadcast a notification to all global subscribers.
   * Skips subscribers that are already watching the originating session
   * (they see events inline and don't need a global notification).
   *
   * @param {object} data - Notification payload
   * @param {string} [originSessionId] - Session that generated the event (used for suppression)
   */
  broadcastToGlobalSubscribers(data, originSessionId) {
    for (const wsId of this.globalSubscribers) {
      const wsInfo = this.webSocketConnections.get(wsId);
      if (!wsInfo || wsInfo.ws.readyState !== WebSocket.OPEN) continue;
      // Suppress if this subscriber is already watching the origin session
      if (originSessionId && wsInfo.claudeSessionId === originSessionId) continue;
      this.sendToWebSocket(wsInfo.ws, data);
    }
  }

  cleanupWebSocketConnection(wsId) {
    const wsInfo = this.webSocketConnections.get(wsId);
    if (!wsInfo) return;

    if (wsInfo.claudeSessionId) {
      const session = this.claudeSessions.get(wsInfo.claudeSessionId);
      if (session) {
        session.connections.delete(wsId);
        session.lastActivity = new Date();
        if (session.connections.size === 0 && this.dev) {
          console.log(`No more connections to session ${wsInfo.claudeSessionId}`);
        }
      }
    }

    this.globalSubscribers.delete(wsId);
    this.webSocketConnections.delete(wsId);
  }

  close() {
    if (this._sessionSaveTimer) {
      clearTimeout(this._sessionSaveTimer);
      this._sessionSaveTimer = null;
      this._sessionSaveResolve = null;
      this._sessionSavePromise = null;
    }
    process.removeListener('SIGINT', this._handleSigint);
    process.removeListener('SIGTERM', this._handleSigterm);
    process.removeListener('beforeExit', this._handleBeforeExit);
    this._beforeExitSaved = true;
    if (this.autoSaveInterval) clearInterval(this.autoSaveInterval);
    if (this.sessionGcInterval) clearInterval(this.sessionGcInterval);
    if (this.wsHeartbeatInterval) clearInterval(this.wsHeartbeatInterval);
    if (this.platformEventBroker) this.platformEventBroker.stop();
    if (this.wss) this.wss.close();
    if (this.server) this.server.close();

    for (const [sessionId, session] of this.claudeSessions.entries()) {
      if (session.active) this.claudeBridge.stopSession(sessionId);
    }

    this.claudeSessions.clear();
    this.webSocketConnections.clear();
  }
}

async function startServer(options) {
  const server = new TerminalServer(options);
  return await server.start();
}

module.exports = { startServer, TerminalServer };
