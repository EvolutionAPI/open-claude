/**
 * PluginErrorBoundary — Step 2 (host renderer rewrite), D3 from ADR.
 *
 * Wraps each plugin route.  Catches render and lifecycle errors thrown by the
 * plugin component so a crashed plugin does not tear down the whole dashboard.
 *
 * Plugins cannot opt out.  The boundary is applied by PluginPageHost per route.
 *
 * Fallback UI shows:
 *   - the plugin slug
 *   - the error message
 *   - a "Reload" button that resets the boundary (in-place retry without full
 *     page refresh)
 *   - a link to /plugins/<slug> for diagnosis / uninstall
 */

import { ErrorBoundary } from '@evonexus/ui'
import type { ReactNode } from 'react'

interface PluginErrorBoundaryProps {
  slug: string
  children: ReactNode
}

export function PluginErrorBoundary({ slug, children }: PluginErrorBoundaryProps) {
  return (
    <ErrorBoundary
      fallback={(error, reset) => (
        <div className="flex items-center justify-center h-full p-8">
          <div className="bg-[#161b22] border border-red-500/30 rounded-2xl p-6 max-w-lg w-full">
            <p className="text-red-400 text-sm font-semibold mb-1">
              Plugin <code className="font-mono">{slug}</code> crashed
            </p>
            <p className="text-[#5a6b7f] text-xs font-mono mb-4 break-words">
              {error.message}
            </p>
            <div className="flex gap-3">
              <button
                onClick={reset}
                className="text-xs bg-[#21262d] hover:bg-[#30363d] text-[#c9d1d9] border border-[#30363d] px-3 py-1.5 rounded-lg transition-colors"
              >
                Reload plugin
              </button>
              <a
                href={`/plugins/${slug}`}
                className="text-xs text-[#00FFA7] hover:underline flex items-center"
              >
                Plugin settings
              </a>
            </div>
          </div>
        </div>
      )}
    >
      {children}
    </ErrorBoundary>
  )
}
