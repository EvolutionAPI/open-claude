/**
 * Shared terminal-server URL constants.
 * Exported here so AgentDetail, AgentTerminal, AgentChat,
 * useGlobalNotifications, and any future consumer all resolve the same base
 * URL without duplication.
 *
 * The dashboard backend mounts an HTTP+WebSocket proxy at /terminal that
 * forwards to the local terminal-server. Going through it keeps terminal
 * access on the same origin as the dashboard, which works behind SSH
 * tunnels, Tailscale Funnel, and reverse proxies that expose only the
 * dashboard port.
 *
 * Escape hatch: VITE_TERMINAL_URL can point at a separate terminal-server
 * base URL. It accepts http(s):// or ws(s):// and maps to both schemes.
 *
 * The Vite dev server (port 5173) does not proxy /terminal, so in DEV mode
 * we fall back to a direct connection to terminal-server.
 */
const isViteDev = import.meta.env.DEV
const rawOverride = (import.meta.env.VITE_TERMINAL_URL as string | undefined)?.trim()
const terminalOverride = rawOverride ? rawOverride.replace(/\/+$/, '') : null

function resolveOverride(raw: string): { http: string; ws: string } | null {
  try {
    const url = new URL(raw)
    const isSecure = url.protocol === 'https:' || url.protocol === 'wss:'
    const httpProtocol = isSecure ? 'https:' : 'http:'
    const wsProtocol = isSecure ? 'wss:' : 'ws:'
    const path = url.pathname.replace(/\/+$/, '') + url.search

    return {
      http: `${httpProtocol}//${url.host}${path}`,
      ws: `${wsProtocol}//${url.host}${path}`,
    }
  } catch {
    return null
  }
}

const override = terminalOverride ? resolveOverride(terminalOverride) : null

export const TS_HTTP = override
  ? override.http
  : isViteDev
    ? `http://${window.location.hostname}:32352`
    : `${window.location.protocol}//${window.location.host}/terminal`

export const TS_WS = override
  ? override.ws
  : isViteDev
    ? `ws://${window.location.hostname}:32352`
    : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/terminal`
