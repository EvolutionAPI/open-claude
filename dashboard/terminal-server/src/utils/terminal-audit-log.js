const fs = require('fs');
const path = require('path');

class TerminalAuditLog {
  constructor(workspaceRoot) {
    this.logsDir = path.join(workspaceRoot || process.cwd(), 'workspace', 'ADWs', 'logs');
    this.logFile = path.join(this.logsDir, 'terminal-audit.jsonl');
    this._ensureDir();
  }

  _ensureDir() {
    try {
      fs.mkdirSync(this.logsDir, { recursive: true });
    } catch {}
  }

  append(entry) {
    try {
      const payload = {
        ts: new Date().toISOString(),
        ...entry,
      };
      fs.appendFileSync(this.logFile, JSON.stringify(payload) + '\n', 'utf8');
      return payload;
    } catch (err) {
      console.error(`[terminal-audit] Failed to append: ${err.message}`);
      return null;
    }
  }
}

module.exports = TerminalAuditLog;
