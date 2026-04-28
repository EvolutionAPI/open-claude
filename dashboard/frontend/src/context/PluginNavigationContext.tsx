/**
 * PluginNavigationProvider — Step 2 (host renderer rewrite).
 *
 * Wraps the React Router useNavigate() hook inside the PluginNavigationContext
 * value so that plugin pages can call usePluginNavigation() from @evonexus/ui
 * without a direct dependency on react-router-dom.
 *
 * Must be rendered inside <BrowserRouter> / <MemoryRouter> (i.e. inside the
 * React Router tree).  App.tsx wraps <Routes> with this provider.
 */

import { useMemo, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { PluginNavigationContext } from '@evonexus/ui'

interface PluginNavigationProviderProps {
  children: ReactNode
}

export function PluginNavigationProvider({
  children,
}: PluginNavigationProviderProps) {
  const navigate = useNavigate()

  const value = useMemo(
    () => ({ navigate: (to: string) => navigate(to) }),
    [navigate]
  )

  return (
    <PluginNavigationContext.Provider value={value}>
      {children}
    </PluginNavigationContext.Provider>
  )
}
