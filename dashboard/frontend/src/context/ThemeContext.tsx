import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { applyTheme, persistTheme, resolveInitialTheme, type ThemeMode } from '../lib/theme'

interface ThemeContextValue {
  theme: ThemeMode
  isDark: boolean
  isLight: boolean
  setTheme: (theme: ThemeMode) => void
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>(() => resolveInitialTheme())

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const setTheme = useCallback((nextTheme: ThemeMode) => {
    persistTheme(nextTheme)
    setThemeState(nextTheme)
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'dark' ? 'light' : 'dark')
  }, [setTheme, theme])

  return (
    <ThemeContext.Provider
      value={{
        theme,
        isDark: theme === 'dark',
        isLight: theme === 'light',
        setTheme,
        toggleTheme,
      }}
    >
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) {
    throw new Error('useTheme must be used within <ThemeProvider>')
  }
  return ctx
}

