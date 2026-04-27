export type ThemeMode = 'dark' | 'light'

export const THEME_STORAGE_KEY = 'evonexus.theme'

function getStoredTheme(): ThemeMode | null {
  if (typeof window === 'undefined') return null
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY)
    if (value === 'dark' || value === 'light') return value
  } catch {}
  return null
}

function getPreferredTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'dark'
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export function resolveInitialTheme(): ThemeMode {
  return getStoredTheme() ?? getPreferredTheme()
}

export function applyTheme(theme: ThemeMode) {
  if (typeof document === 'undefined') return

  const root = document.documentElement
  root.dataset.theme = theme
  root.style.colorScheme = theme

  const body = document.body
  body.dataset.theme = theme

  const themeColor = theme === 'light' ? '#f5f7fb' : '#0C111D'
  const meta = document.querySelector('meta[name="theme-color"]') as HTMLMetaElement | null
  if (meta) meta.content = themeColor
}

export function persistTheme(theme: ThemeMode) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {}
}

