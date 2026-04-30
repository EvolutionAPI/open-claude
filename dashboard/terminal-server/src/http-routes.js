const WebSocket = require('ws');
const { v4: uuidv4 } = require('uuid');

function registerTerminalHttpRoutes(app, server) {
  app.get('/api/health', (req, res) => {
    const snapshot = server.getHealthSnapshot(false);
    res.status(snapshot.status === 'error' ? 503 : 200).json(snapshot);
  });

  app.get('/api/health/deep', (req, res) => {
    const snapshot = server.getHealthSnapshot(true);
    res.status(snapshot.status === 'error' ? 503 : 200).json(snapshot);
  });

  // Find-or-create a session for a specific subagent (e.g. 'oracle')
  app.post('/api/sessions/for-agent', (req, res) => {
    const { agentName, workingDir, ticketId, systemPromptExtras } = req.body;
    if (!agentName) {
      return res.status(400).json({ error: 'agentName is required' });
    }

    // Scope reuse by (agentName, ticketId) when ticketId is provided.
    // Without ticketId the old behaviour is preserved (reuse by agentName alone).
    for (const [id, s] of server.claudeSessions.entries()) {
      const agentMatch = s.agentName === agentName;
      const ticketMatch = ticketId ? s.ticketId === ticketId : !s.ticketId;
      if (agentMatch && ticketMatch) {
        return res.json({
          success: true,
          sessionId: id,
          reused: true,
          session: {
            id,
            name: s.name,
            workingDir: s.workingDir,
            active: s.active,
            agentName: s.agentName,
            ticketId: s.ticketId || null,
          },
        });
      }
    }

    let validWorkingDir = server.baseFolder;
    if (workingDir) {
      const validation = server.validatePath(workingDir);
      if (!validation.valid) {
        return res.status(403).json({
          error: validation.error,
          message: 'Cannot create session with working directory outside the allowed area',
        });
      }
      validWorkingDir = validation.path;
    }

    const sessionId = uuidv4();
    const session = {
      id: sessionId,
      name: `${agentName} — ${new Date().toLocaleString()}`,
      created: new Date(),
      lastActivity: new Date(),
      active: false,
      agent: null,
      agentName,
      ticketId: ticketId || null,
      systemPromptExtras: systemPromptExtras || null,
      workingDir: validWorkingDir,
      connections: new Set(),
      outputBuffer: [],
      maxBufferSize: 1000,
    };
    server.claudeSessions.set(sessionId, session);
    server.requestSessionSave();

    res.json({
      success: true,
      sessionId,
      reused: false,
      session: {
        id: sessionId,
        name: session.name,
        workingDir: session.workingDir,
        active: false,
        agentName,
        ticketId: ticketId || null,
      },
    });
  });

  // List all sessions for a given agent
  app.get('/api/sessions/by-agent/:agentName', (req, res) => {
    const { agentName } = req.params;
    const sessions = [];
    for (const [id, s] of server.claudeSessions.entries()) {
      if (s.agentName === agentName) {
        // Build preview and find last message timestamp
        let preview = '';
        let lastMessageTs = 0;
        if (Array.isArray(s.chatHistory) && s.chatHistory.length > 0) {
          // Last message timestamp for sorting
          const lastMsg = s.chatHistory[s.chatHistory.length - 1];
          lastMessageTs = lastMsg.ts || 0;
          // Preview from last user message
          for (let i = s.chatHistory.length - 1; i >= 0; i--) {
            if (s.chatHistory[i].role === 'user' && s.chatHistory[i].text) {
              preview = s.chatHistory[i].text.slice(0, 80);
              break;
            }
          }
        }
        sessions.push({
          id,
          name: s.name,
          created: s.created,
          active: s.active,
          agentName: s.agentName,
          ticketId: s.ticketId || null,
          archived: s.archived || false,
          lastActivity: lastMessageTs || (s.lastActivity ? new Date(s.lastActivity).getTime() : 0),
          preview,
          messageCount: Array.isArray(s.chatHistory) ? s.chatHistory.length : 0,
        });
      }
    }
    // Sort by lastActivity descending (most recent first)
    sessions.sort((a, b) => (b.lastActivity || 0) - (a.lastActivity || 0));
    res.json({ sessions });
  });

  // Create a NEW session for an agent (always creates, never reuses)
  app.post('/api/sessions/create', (req, res) => {
    const { agentName, workingDir } = req.body;
    if (!agentName) {
      return res.status(400).json({ error: 'agentName is required' });
    }

    let validWorkingDir = server.baseFolder;
    if (workingDir) {
      const validation = server.validatePath(workingDir);
      if (!validation.valid) {
        return res.status(403).json({ error: validation.error });
      }
      validWorkingDir = validation.path;
    }

    // Count existing sessions for this agent to number them
    let count = 0;
    for (const s of server.claudeSessions.values()) {
      if (s.agentName === agentName) count++;
    }

    const sessionId = uuidv4();
    const session = {
      id: sessionId,
      name: `${agentName} #${count + 1}`,
      created: new Date(),
      lastActivity: new Date(),
      active: false,
      agent: null,
      agentName,
      workingDir: validWorkingDir,
      connections: new Set(),
      outputBuffer: [],
      maxBufferSize: 1000,
    };
    server.claudeSessions.set(sessionId, session);
    server.requestSessionSave();

    res.json({
      success: true,
      sessionId,
      session: {
        id: sessionId,
        name: session.name,
        workingDir: session.workingDir,
        active: false,
        agentName,
      },
    });
  });

  app.get('/api/sessions/:sessionId', (req, res) => {
    const session = server.claudeSessions.get(req.params.sessionId);
    if (!session) return res.status(404).json({ error: 'Session not found' });
    res.json({
      id: session.id,
      name: session.name,
      created: session.created,
      active: session.active,
      workingDir: session.workingDir,
      connectedClients: session.connections.size,
      lastActivity: session.lastActivity,
      ticketId: session.ticketId || null,
    });
  });

  // Bind a session to a ticket (Feature 1.3 — session binding)
  app.post('/api/sessions/:sessionId/ticket', (req, res) => {
    const session = server.claudeSessions.get(req.params.sessionId);
    if (!session) return res.status(404).json({ error: 'Session not found' });
    const { ticketId } = req.body || {};
    // ticketId can be null to unbind
    session.ticketId = ticketId || null;
    session.lastActivity = new Date();
    server.requestSessionSave();
    res.json({ success: true, sessionId: session.id, ticketId: session.ticketId });
  });

  // Rename or archive a session
  app.patch('/api/sessions/:sessionId', (req, res) => {
    const session = server.claudeSessions.get(req.params.sessionId);
    if (!session) return res.status(404).json({ error: 'Session not found' });
    const { name, archived } = req.body || {};
    if (name !== undefined) {
      if (typeof name !== 'string' || !name.trim()) {
        return res.status(400).json({ error: 'name must be a non-empty string' });
      }
      session.name = name.trim();
    }
    if (archived !== undefined) {
      session.archived = Boolean(archived);
    }
    session.lastActivity = new Date();
    server.requestSessionSave();
    res.json({
      id: session.id,
      name: session.name,
      archived: session.archived || false,
      lastActivity: session.lastActivity,
    });
  });

  app.delete('/api/sessions/:sessionId', (req, res) => {
    const sessionId = req.params.sessionId;
    const session = server.claudeSessions.get(sessionId);
    if (!session) return res.status(404).json({ error: 'Session not found' });

    if (session.active) server.claudeBridge.stopSession(sessionId);

    session.connections.forEach((wsId) => {
      const wsInfo = server.webSocketConnections.get(wsId);
      if (wsInfo && wsInfo.ws.readyState === WebSocket.OPEN) {
        wsInfo.ws.send(JSON.stringify({ type: 'session_deleted', message: 'Session has been deleted' }));
        wsInfo.ws.close();
      }
    });

    server.claudeSessions.delete(sessionId);
    server.requestSessionSave();
    res.json({ success: true, message: 'Session deleted' });
  });

  // Return all unresolved permission requests across all active sessions
  app.get('/api/notifications/pending', (req, res) => {
    const notifications = [];
    for (const [sessionId, session] of server.claudeSessions.entries()) {
      const bridgeSession = server.chatBridge.sessions.get(sessionId);
      if (!bridgeSession?.pendingApprovals) continue;
      for (const [requestId] of bridgeSession.pendingApprovals.entries()) {
        notifications.push({
          id: `agent_awaiting-${sessionId}-${requestId}`,
          event: 'agent_awaiting',
          sessionId,
          agentName: session.agentName || '',
          toolName: undefined,
          createdAt: Date.now(),
        });
      }
    }
    res.json({ notifications });
  });

  // ── Provider change notification ───────────────────────────
  // Called by the Flask backend when the user switches the active provider.
  // Triggers immediate invalidation of all PTY sessions.
  app.post('/api/provider-changed', async (req, res) => {
    const { new_provider, old_provider } = req.body || {};
    console.log(`[http] POST /api/provider-changed: ${old_provider} -> ${new_provider}`);

    try {
      // Invalidate all active PTY sessions
      const invalidated = await server.claudeBridge.invalidateAllSessions('provider_changed_api');

      // Mark tracked sessions as inactive
      for (const [sessionId, session] of server.claudeSessions.entries()) {
        if (session.active && session.agent === 'claude') {
          session.active = false;
          session.agent = null;
          session.lastActivity = new Date();
        }
      }

      await server.saveSessionsToDisk();

      // Broadcast to all WebSocket clients
      const payload = {
        type: 'provider_changed',
        newProvider: new_provider,
        oldProvider: old_provider,
        invalidatedSessions: invalidated,
        message: `Provedor alterado para ${new_provider}. ${invalidated.length} sessao(oes) reiniciada(s).`,
      };
      for (const [wsId, wsInfo] of server.webSocketConnections.entries()) {
        if (wsInfo.ws && wsInfo.ws.readyState === 1) {
          server.sendToWebSocket(wsInfo.ws, payload);
        }
      }

      res.json({
        success: true,
        invalidated_sessions: invalidated.length,
        new_provider,
      });
    } catch (err) {
      console.error('[http] Error handling provider-changed:', err);
      res.status(500).json({ error: err.message });
    }
  });

  // Current active provider info
  app.get('/api/provider/active', (req, res) => {
    try {
      const { loadProviderConfig, getProviderMode } = require('./provider-config');
      const config = loadProviderConfig();
      res.json({
        active: config.active,
        provider_id: config.provider_id,
        cli_command: config.cli_command,
        mode: getProviderMode(config),
        provider_name: config.provider_name,
      });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });
}

module.exports = {
  registerTerminalHttpRoutes,
};
