// Shared date/time formatting that respects the workspace timezone setting.
//
// Order of preference for the IANA timezone:
//   1. workspace.timezone from /api/settings/workspace  (the explicit user choice)
//   2. localStorage cache (so the first paint isn't always wrong)
//   3. Browser default (Intl.DateTimeFormat().resolvedOptions().timeZone)
//
// Previously every page hardcoded `America/Sao_Paulo`, which gave a 4h drift
// for users in Europe and a different drift everywhere else.

import { api } from './api'

const STORAGE_KEY = 'evo:workspace-timezone'

let cachedTz: string | null = null
let inflight: Promise<string> | null = null

function browserTz(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

/** Synchronously read whatever timezone we know right now. Never throws. */
export function getTimezoneSync(): string {
  if (cachedTz) return cachedTz
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored) {
      cachedTz = stored
      return stored
    }
  } catch {
    // localStorage unavailable (SSR, private mode) — ignore
  }
  return browserTz()
}

/** Fetch from API and cache. Subsequent callers reuse the in-flight promise.
 *
 * Race-safe with `refreshWorkspaceTimezone`: if the user updates the setting
 * (or any other code path populates the cache) while this fetch is in flight,
 * the resolved value is dropped — we never overwrite a fresher cache value
 * with the stale server response. */
export async function loadWorkspaceTimezone(): Promise<string> {
  if (cachedTz) return cachedTz
  if (inflight) return inflight
  inflight = api
    .get('/settings/workspace')
    .then((data: any) => {
      const tz: string = data?.workspace?.timezone || browserTz()
      // Only write if nothing else claimed the cache in the meantime
      // (e.g. a concurrent refreshWorkspaceTimezone from Settings save).
      if (cachedTz == null) {
        cachedTz = tz
        try { window.localStorage.setItem(STORAGE_KEY, tz) } catch { /* noop */ }
      }
      return cachedTz!
    })
    .catch(() => {
      const fallback = browserTz()
      if (cachedTz == null) {
        cachedTz = fallback
      }
      return cachedTz!
    })
    .finally(() => { inflight = null })
  return inflight
}

/** Invalidate cache after the user updates the setting. */
export function refreshWorkspaceTimezone(tz?: string): void {
  if (tz) {
    cachedTz = tz
    try { window.localStorage.setItem(STORAGE_KEY, tz) } catch { /* noop */ }
  } else {
    cachedTz = null
    try { window.localStorage.removeItem(STORAGE_KEY) } catch { /* noop */ }
  }
}

/** Format an ISO timestamp using the workspace timezone (or fallback). */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '--'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '--'
  return d.toLocaleString('pt-BR', {
    timeZone: getTimezoneSync(),
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

/** Format an ISO timestamp date-only. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '--'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '--'
  return d.toLocaleDateString('pt-BR', {
    timeZone: getTimezoneSync(),
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}
