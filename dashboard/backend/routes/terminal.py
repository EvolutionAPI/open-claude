"""Terminal endpoint — WebSocket PTY for real terminal sessions."""

import os
import sys
import json
import threading
import time
import datetime as _dt
import re
from pathlib import Path
from flask import Blueprint, request as flask_request
from flask_login import current_user, login_required
from flask_sock import Sock
from routes._helpers import WORKSPACE

bp = Blueprint("terminal", __name__)
sock = Sock()

_WINDOWS = sys.platform == "win32"

if _WINDOWS:
    from winpty import PtyProcess
else:
    import pty
    import select
    import signal
    import struct
    import fcntl
    import termios

# Store active sessions: {session_id: {pid, fd}}
sessions = {}
session_counter = 0

# Claude session cache
_claude_sessions_cache = {"data": [], "ts": 0}
_claude_sessions_lock = threading.Lock()
CACHE_TTL = 60


def _get_project_slug():
    """Convert WORKSPACE path to Claude project slug.

    Matches Claude CLI encoding: replace all non-alphanumeric chars with -.
    Result has a leading - (e.g. -Users-foo-bar). This is intentional.
    """
    return re.sub(r"[^a-zA-Z0-9]", "-", str(WORKSPACE.resolve()))


def _parse_session_file(filepath, max_lines=20):
    """Extract metadata from a session JSONL (first N lines only)."""
    session_id = filepath.stem
    try:
        fstat = filepath.stat()
    except OSError:
        return None
    agent = None
    first_prompt = None
    timestamp = None
    try:
        with open(filepath, "r") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                try:
                    d = json.loads(line)
                    t = d.get("type")
                    if t == "agent-setting" and not agent:
                        agent = d.get("agentSetting")
                    if t == "user" and not first_prompt:
                        ts = d.get("timestamp")
                        msg = d.get("message", {})
                        content = msg.get("content", "")
                        if isinstance(content, str) and len(content) > 5:
                            if not content.startswith(("<local-command", "<command")):
                                first_prompt = content[:200]
                                timestamp = ts
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    txt = item.get("text", "")
                                    if txt and not txt.startswith(("<", "[Image")):
                                        first_prompt = txt[:200]
                                        timestamp = ts
                                        break
                except (json.JSONDecodeError, KeyError):
                    continue
    except (OSError, IOError):
        return None
    if not timestamp:
        mtime = fstat.st_mtime
        timestamp = _dt.datetime.fromtimestamp(mtime, tz=_dt.timezone.utc).isoformat()
    return {
        "session_id": session_id,
        "agent": agent,
        "first_prompt": first_prompt,
        "timestamp": timestamp,
        "size": fstat.st_size,
    }


def _spawn_pty(cmd, cwd):
    """Spawn a process in a PTY and return (pid, fd). Unix only."""
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["COLUMNS"] = "120"
    env["LINES"] = "40"

    pid, fd = pty.fork()
    if pid == 0:
        # Child process
        os.chdir(str(cwd))
        os.execvpe(cmd[0], cmd, env)
    return pid, fd


def _set_winsize(fd, rows, cols):
    """Set terminal window size. Unix only."""
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def _spawn_conpty(cmd, cwd):
    """Spawn a process in a Windows ConPTY and return a PtyProcess."""
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    return PtyProcess.spawn(cmd, cwd=str(cwd), env=env, dimensions=(40, 120))


@bp.route("/api/terminal/sessions")
@login_required
def list_sessions():
    """List active terminal sessions."""
    result = []
    for sid, info in sessions.items():
        if _WINDOWS:
            proc = info.get("process")
            alive = proc.isalive() if proc else False
        else:
            try:
                os.kill(info["pid"], 0)
                alive = True
            except OSError:
                alive = False
        result.append({"id": sid, "cmd": info["cmd"], "alive": alive})
    return {"sessions": result}


@bp.route("/api/terminal/claude-sessions")
@login_required
def list_claude_sessions():
    """List resumable Claude sessions from disk."""
    now = time.time()
    with _claude_sessions_lock:
        if now - _claude_sessions_cache["ts"] < CACHE_TTL and _claude_sessions_cache["data"]:
            sessions_list = list(_claude_sessions_cache["data"])
        else:
            slug = _get_project_slug()
            sessions_dir = Path.home() / ".claude" / "projects" / slug
            if not sessions_dir.exists():
                return {"sessions": []}
            jsonl_files = sorted(
                sessions_dir.glob("*.jsonl"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )[:50]
            sessions_list = []
            for f in jsonl_files:
                meta = _parse_session_file(f)
                if meta:
                    sessions_list.append(meta)
            _claude_sessions_cache["data"] = list(sessions_list)
            _claude_sessions_cache["ts"] = now
    q = flask_request.args.get("q", "").lower()
    if q:
        sessions_list = [
            s for s in sessions_list
            if q in (s.get("first_prompt") or "").lower()
            or q in (s.get("agent") or "").lower()
            or q in (s.get("session_id") or "").lower()
        ]
    return {"sessions": sessions_list}


@bp.route("/api/terminal/create", methods=["POST"])
@login_required
def create_session():
    """Create a new terminal session."""
    global session_counter
    data = flask_request.get_json(silent=True) or {}

    cmd_type = data.get("type", "claude")
    resume_id = data.get("resume_session_id")
    if cmd_type == "claude":
        cmd = ["claude", "--dangerously-skip-permissions"]
        if resume_id:
            if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', resume_id):
                return {"error": "Invalid session ID format"}, 400
            slug = _get_project_slug()
            session_file = Path.home() / ".claude" / "projects" / slug / f"{resume_id}.jsonl"
            if not session_file.exists():
                return {"error": "Session not found"}, 404
            cmd.extend(["--resume", resume_id])
    elif cmd_type == "shell":
        cmd = ["cmd.exe"] if _WINDOWS else [os.environ.get("SHELL", "/bin/zsh")]
    else:
        cmd = ["claude", "--dangerously-skip-permissions"]

    try:
        session_counter += 1
        sid = f"term-{session_counter}"
        if _WINDOWS:
            proc = _spawn_conpty(cmd, WORKSPACE)
            sessions[sid] = {"process": proc, "cmd": " ".join(cmd)}
        else:
            pid, fd = _spawn_pty(cmd, WORKSPACE)
            sessions[sid] = {"pid": pid, "fd": fd, "cmd": " ".join(cmd)}
        return {"id": sid, "cmd": " ".join(cmd)}
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route("/api/terminal/kill/<session_id>", methods=["POST"])
@login_required
def kill_session(session_id):
    """Kill a terminal session."""
    info = sessions.get(session_id)
    if not info:
        return {"error": "Session not found"}, 404
    try:
        if _WINDOWS:
            info["process"].terminate(force=True)
        else:
            os.kill(info["pid"], signal.SIGTERM)
            os.close(info["fd"])
    except OSError:
        pass
    del sessions[session_id]
    return {"status": "killed"}


def init_websocket(app):
    """Initialize WebSocket on the Flask app."""
    sock.init_app(app)

    @sock.route("/ws/terminal/<session_id>")
    def terminal_ws(ws, session_id):
        """WebSocket handler for terminal I/O."""
        # WebSocket routes bypass before_request, so check auth here
        if not current_user.is_authenticated:
            ws.send(json.dumps({"error": "Authentication required"}))
            return

        info = sessions.get(session_id)
        if not info:
            ws.send(json.dumps({"error": "Session not found"}))
            return

        if _WINDOWS:
            proc = info["process"]

            def read_output():
                """Read from ConPTY and send to WebSocket."""
                while True:
                    try:
                        if not proc.isalive():
                            break
                        data = proc.read(4096)
                        if data:
                            ws.send(data if isinstance(data, str) else data.decode("utf-8", errors="replace"))
                        else:
                            time.sleep(0.01)
                    except Exception:
                        break
                try:
                    ws.send("\r\n[Process exited]\r\n")
                except Exception:
                    pass

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()

            try:
                while True:
                    try:
                        msg = ws.receive(timeout=300)
                    except Exception:
                        break

                    if msg is None:
                        break

                    if isinstance(msg, str) and msg.startswith('{"resize":'):
                        try:
                            data = json.loads(msg)
                            proc.setwinsize(data["resize"]["rows"], data["resize"]["cols"])
                        except Exception:
                            pass
                        continue

                    if isinstance(msg, str) and msg == '{"ping":true}':
                        try:
                            ws.send('{"pong":true}')
                        except Exception:
                            pass
                        continue

                    try:
                        proc.write(msg if isinstance(msg, str) else msg.decode("utf-8"))
                    except Exception:
                        break
            except Exception:
                pass
            finally:
                reader.join(timeout=1)

        else:
            fd = info["fd"]

            # Set non-blocking
            import fcntl
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            def read_output():
                """Read from PTY and send to WebSocket."""
                while True:
                    try:
                        r, _, _ = select.select([fd], [], [], 0.1)
                        if r:
                            data = os.read(fd, 4096)
                            if data:
                                ws.send(data.decode("utf-8", errors="replace"))
                            else:
                                break
                    except (OSError, EOFError):
                        break
                    except Exception:
                        break
                try:
                    ws.send("\r\n[Process exited]\r\n")
                except Exception:
                    pass

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()

            try:
                while True:
                    try:
                        msg = ws.receive(timeout=300)
                    except Exception:
                        break

                    if msg is None:
                        break

                    if isinstance(msg, str) and msg.startswith('{"resize":'):
                        try:
                            data = json.loads(msg)
                            rows = data["resize"]["rows"]
                            cols = data["resize"]["cols"]
                            _set_winsize(fd, rows, cols)
                        except Exception:
                            pass
                        continue

                    if isinstance(msg, str) and msg == '{"ping":true}':
                        try:
                            ws.send('{"pong":true}')
                        except Exception:
                            pass
                        continue

                    try:
                        os.write(fd, msg.encode("utf-8") if isinstance(msg, str) else msg)
                    except OSError:
                        break
            except Exception:
                pass
            finally:
                reader.join(timeout=1)
