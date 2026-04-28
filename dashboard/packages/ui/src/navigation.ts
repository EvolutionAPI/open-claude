/**
 * Plugin navigation — Step 2 (host renderer rewrite).
 *
 * The host mounts a PluginNavigationProvider (in dashboard/frontend) that
 * wraps the React Router context.  Plugin pages call usePluginNavigation()
 * to navigate without touching window globals.
 *
 * The context value and hook live here so that plugin bundles can import them
 * from @evonexus/ui without a direct dependency on react-router-dom.
 */

import { createContext, useContext } from 'react'

// ─── Context value ────────────────────────────────────────────────────────────

export interface PluginNavigationContextValue {
  /** Navigate to any dashboard route, e.g. navigate('/plugins/my-plugin') */
  navigate: (to: string) => void
}

// Default is a no-op so that plugins rendered outside the provider don't crash.
const defaultValue: PluginNavigationContextValue = {
  navigate: () => {
    if (typeof console !== 'undefined') {
      console.warn(
        '[evonexus/ui] usePluginNavigation() called outside PluginNavigationProvider'
      )
    }
  },
}

export const PluginNavigationContext =
  createContext<PluginNavigationContextValue>(defaultValue)

// ─── Hook ─────────────────────────────────────────────────────────────────────

/**
 * Returns `{ navigate }` — call navigate(to) from a plugin page to trigger
 * React Router navigation on the host without accessing window globals.
 *
 * Must be used inside a component tree wrapped by PluginNavigationProvider
 * (mounted by the host in App.tsx).
 *
 * @example
 * ```tsx
 * import { usePluginNavigation } from '@evonexus/ui'
 *
 * function MyPluginPage() {
 *   const { navigate } = usePluginNavigation()
 *   return <button onClick={() => navigate('/plugins/my-plugin')}>Back</button>
 * }
 * ```
 */
export function usePluginNavigation(): PluginNavigationContextValue {
  return useContext(PluginNavigationContext)
}
