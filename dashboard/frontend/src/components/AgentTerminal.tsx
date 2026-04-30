import { useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { TS_HTTP, TS_WS } from '../lib/terminal-url'

interface AgentTerminalProps {
  agent: string
  sessionId?: string
  workingDir?: string
  accentColor?: string
}

const CC_WEB_HTTP = TS_HTTP
const CC_WEB_WS = TS_WS

type Status = 'connecting' | 'ready' | 'starting' | 'running' | 'error' | 'exited'

export default function AgentTerminal({ agent, sessionId: externalSessionId, workingDir, accentColor = '#00FFA7' }: AgentTerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const sessionIdRef = useRef<string | null>(null)
  const pingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const processEndedRef = useRef(false)
  const [status, setStatus] = useState<Status>('connecting')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Mount xterm once
  useEffect(() => {
    if (!containerRef.current) return
    const term = new Terminal({
      cursorBlink: true,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      fontSize: 13,
      theme: {
        background: '#0C111D',
        foreground: '#e6edf3',
        cursor: accentColor,
        cursorAccent: '#0C111D',
        black: '#484f58',
        red: '#ff7b72',
        green: '#7ee787',
        yellow: '#d29922',
        blue: '#79c0ff',
        magenta: '#d2a8ff',
        cyan: '#a5d6ff',
        white: '#b1bac4',
      },
      scrollback: 5000,
      allowProposedApi: true,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.loadAddon(new WebLinksAddon())
    term.open(containerRef.current)
    try { fit.fit() } catch {}
    termRef.current = term
    fitRef.current = fit

    // Silence terminal query replies at the parser level — before
    // xterm.js gets a chance to generate them. The pty already knows
    // its own capabilities; forwarding emulator-side replies made
    // claude see them as keyboard input and print bytes like "0?1;2c"
    // or "000000" into the prompt on startup.
    //
    // Registering a handler that returns `true` marks the CSI as
    // "handled" and prevents the default sendDeviceAttributesPrimary /
    // sendDeviceAttributesSecondary / deviceStatus / reportWindow*
    // paths from firing. No reply is emitted at all.
    //
    // - final 'c'            → DA1 (\x1b[c) and DA2 (\x1b[>c)
    // - final 'n'            → DSR status (\x1b[5n) and cursor pos (\x1b[6n)
    // - final 't'            → window manipulation reports (xterm
    //                          CSI Ps ; Ps ; Ps t)
    const noReply = () => true
    term.parser.registerCsiHandler({ final: 'c' }, noReply)
    term.parser.registerCsiHandler({ final: 'c', prefix: '>' }, noReply)
    term.parser.registerCsiHandler({ final: 'n' }, noReply)
    term.parser.registerCsiHandler({ final: 'n', prefix: '?' }, noReply)
    term.parser.registerCsiHandler({ final: 't' }, noReply)

    const onResize = () => {
      try {
        fit.fit()
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            type: 'resize',
            cols: term.cols,
            rows: term.rows,
          }))
        }
      } catch {}
    }
    window.addEventListener('resize', onResize)

    // Second line of defense: even though the parser-level handlers
    // above should prevent every known query reply, drop any onData
    // payload that still looks like a terminal auto-reply. Real user
    // keyboard input (arrows \x1b[A-D, Home/End \x1b[H/F, function
    // keys \x1b[<n>~, modified arrows \x1b[1;2A) don't match either
    // alternative.
    const AUTO_REPLY_RE = /^\x1b\[(\?|>)[0-9;]*[a-zA-Z]$|^\x1b\[[0-9;]*[nRct]$/
    term.onData((data) => {
      // TEMP DEBUG: log every onData payload so we can see what's being
      // sent to the pty on startup
      const hex = Array.from(data).map((c) => (c as unknown as string).charCodeAt(0).toString(16).padStart(2, '0')).join('')
      // eslint-disable-next-line no-console
      console.log('[xterm onData]', data.length, 'B  hex:', hex, '  match:', AUTO_REPLY_RE.test(data))
      if (AUTO_REPLY_RE.test(data)) return
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'input', data }))
      }
    })

    return () => {
      window.removeEventListener('resize', onResize)
      term.dispose()
      termRef.current = null
      fitRef.current = null
    }
  }, [])

  // Connect / start session for this agent
  useEffect(() => {
    let cancelled = false
    const term = termRef.current
    if (!term) return

    function clearReconnectTimer() {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    }

    function scheduleReconnect() {
      if (cancelled || processEndedRef.current || reconnectTimerRef.current) return
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null
        if (!cancelled && !processEndedRef.current) {
          run(false)
        }
      }, 1000)
    }

    async function run(clearTerminal = true) {
      clearReconnectTimer()
      processEndedRef.current = false
      setStatus('connecting')
      setErrorMsg(null)
      if (clearTerminal) term!.clear()

      // 1) Use provided sessionId or find-or-create for this agent
      let sessionId: string
      let alreadyActive = false
      try {
        if (externalSessionId) {
          // Use the specific session provided by the parent (multi-tab mode)
          sessionId = externalSessionId
          const infoRes = await fetch(`${CC_WEB_HTTP}/api/sessions/${externalSessionId}`)
          if (infoRes.ok) {
            const info = await infoRes.json()
            alreadyActive = !!info.active
          }
        } else {
          // Default: find-or-create session for this agent
          const res = await fetch(`${CC_WEB_HTTP}/api/sessions/for-agent`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agentName: agent, workingDir }),
          })
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          const data = await res.json()
          sessionId = data.sessionId
          alreadyActive = !!data.session?.active
        }
      } catch (e: any) {
        if (cancelled) return
        setStatus('error')
        setErrorMsg(`Could not reach terminal-server at ${CC_WEB_HTTP}. Is it running?`)
        return
      }

      if (cancelled) return
      sessionIdRef.current = sessionId

      // 2) Open WS
      const ws = new WebSocket(`${CC_WEB_WS}/ws`)
      wsRef.current = ws
      let opened = false

      const isCurrentSocket = () => !cancelled && wsRef.current === ws

      ws.onopen = () => {
        if (!isCurrentSocket()) return
        opened = true
        setErrorMsg(null)
        ws.send(JSON.stringify({ type: 'join_session', sessionId }))
      }

      ws.onmessage = (ev) => {
        if (!isCurrentSocket()) return
        let msg: any
        try { msg = JSON.parse(ev.data) } catch { return }

        switch (msg.type) {
          case 'session_joined': {
            setErrorMsg(null)
            // Replay any buffered output
            if (Array.isArray(msg.outputBuffer)) {
              msg.outputBuffer.forEach((chunk: string) => term!.write(chunk))
            }
            // If an agent is already running in this session, just attach
            if (msg.active || alreadyActive) {
              setStatus('running')
              // Nudge a resize so the pty matches the current terminal size
              const fit = fitRef.current
              if (fit) {
                try { fit.fit() } catch {}
                ws.send(JSON.stringify({ type: 'resize', cols: term!.cols, rows: term!.rows }))
              }
            } else {
              // Start Claude with --agent <agent>
              // Pass cols/rows up-front so the pty is born at the right
              // size — otherwise claude's DA1 (\x1b[c) / cursor-position
              // queries during startup can echo back into the prompt as
              // literal text ("0?1;2c0?1;2c") before the first resize
              // message arrives.
              setStatus('starting')
              const fit = fitRef.current
              if (fit) {
                try { fit.fit() } catch {}
              }
              ws.send(JSON.stringify({
                type: 'start_claude',
                options: {
                  dangerouslySkipPermissions: true,
                  agent,
                  cols: term!.cols,
                  rows: term!.rows,
                },
              }))
            }
            break
          }
          case 'output':
            setErrorMsg(null)
            term!.write(msg.data)
            break
          case 'claude_started':
            setErrorMsg(null)
            setStatus('running')
            // resize after start
            {
              const fit = fitRef.current
              if (fit) {
                try { fit.fit() } catch {}
                ws.send(JSON.stringify({ type: 'resize', cols: term!.cols, rows: term!.rows }))
              }
            }
            break
          case 'exit':
            processEndedRef.current = true
            setStatus('exited')
            term!.write(`\r\n\x1b[33m[Process exited${msg.code != null ? ` with code ${msg.code}` : ''}]\x1b[0m\r\n`)
            break
          case 'error':
            setStatus('error')
            setErrorMsg(msg.message || 'Unknown error')
            term!.write(`\r\n\x1b[31m[Error] ${msg.message || ''}\x1b[0m\r\n`)
            break
          case 'pong':
            break
        }
      }

      ws.onerror = () => {
        if (!isCurrentSocket()) return
        if (!opened) {
          setStatus('error')
          setErrorMsg(`Could not open WebSocket at ${CC_WEB_WS}/ws`)
        }
      }

      ws.onclose = () => {
        if (pingRef.current) {
          clearInterval(pingRef.current)
          pingRef.current = null
        }
        if (wsRef.current === ws) {
          wsRef.current = null
        } else {
          return
        }
        if (!cancelled && !processEndedRef.current) {
          setStatus('connecting')
          setErrorMsg(opened ? 'WebSocket disconnected. Reconnecting...' : `Could not open WebSocket at ${CC_WEB_WS}/ws`)
          scheduleReconnect()
        }
      }

      // Keepalive
      pingRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }))
        }
      }, 25000)
    }

    run()

    return () => {
      cancelled = true
      clearReconnectTimer()
      if (pingRef.current) {
        clearInterval(pingRef.current)
        pingRef.current = null
      }
      if (wsRef.current) {
        try { wsRef.current.close() } catch {}
        wsRef.current = null
      }
    }
  }, [agent, externalSessionId, workingDir])

  const statusDotColor =
    status === 'running'
      ? accentColor
      : status === 'starting' || status === 'connecting'
      ? '#F59E0B'
      : status === 'error'
      ? '#ef4444'
      : '#4b5563'

  const statusLabel =
    status === 'connecting' ? 'connecting…' :
    status === 'starting'   ? 'starting…' :
    status === 'running'    ? 'live' :
    status === 'error'      ? 'error' :
    status === 'exited'     ? 'exited' : ''

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden">
      {/* Status bar */}
      <div className="flex-shrink-0 h-8 flex items-center gap-3 px-4 border-b border-[#21262d] bg-[#0d1117]">
        <span
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{
            backgroundColor: statusDotColor,
            boxShadow: status === 'running' ? `0 0 6px ${accentColor}aa` : 'none',
          }}
        />
        <code className="font-mono text-[10.5px] text-[#8b949e] truncate">
          @{agent}
        </code>
        <span className="text-[#21262d]">·</span>
        <span className="text-[10px] uppercase tracking-[0.12em] text-[#667085]">
          {statusLabel}
        </span>
        {errorMsg && (
          <span
            className="ml-auto text-[10px] text-[#ef4444] truncate max-w-[50%]"
            title={errorMsg}
          >
            {errorMsg}
          </span>
        )}
      </div>

      {/* xterm */}
      <div ref={containerRef} className="flex-1 min-h-0 px-4 py-3 bg-[#0C111D]" />
    </div>
  )
}
