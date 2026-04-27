import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react'
import { useLocation, useNavigate, type NavigateFunction } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Moon, RefreshCw, Search, Sun, X, type LucideIcon } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { DOCS_NAV_ITEM, getVisibleNavGroups, NAV_GROUPS, type NavItem } from '../lib/navigation'

interface CommandPaletteContextValue {
  isOpen: boolean
  openCommandPalette: () => void
  closeCommandPalette: () => void
  toggleCommandPalette: () => void
}

interface PaletteCommand {
  id: string
  label: string
  description: string
  group: string
  icon: LucideIcon
  action: () => void
  keywords: string[]
}

const CommandPaletteContext = createContext<CommandPaletteContextValue | null>(null)

export function useCommandPalette() {
  const ctx = useContext(CommandPaletteContext)
  if (!ctx) {
    throw new Error('useCommandPalette must be used within <CommandPaletteProvider>')
  }
  return ctx
}

function commandLabel(item: NavItem, t: (key: string) => string) {
  return t(`nav.${item.labelKey}`)
}

function buildRouteCommands(
  hasPermission: (resource: string, action: string) => boolean,
  t: (key: string) => string,
  navigate: NavigateFunction,
  close: () => void,
): PaletteCommand[] {
  const visibleGroups = getVisibleNavGroups(hasPermission)
  const byKey = new Map(visibleGroups.map((group) => [group.key, group]))
  const commands: PaletteCommand[] = []

  for (const group of NAV_GROUPS) {
    const visible = byKey.get(group.key)
    if (!visible) continue

    for (const item of visible.items) {
      commands.push({
        id: `route:${item.to}`,
        label: commandLabel(item, t),
        description: item.to === '/' ? 'Go to the main dashboard' : item.to,
        group: t(`nav.groups.${group.key}`),
        icon: item.icon,
        keywords: [item.to, group.key, commandLabel(item, t), t(`nav.groups.${group.key}`)],
        action: () => {
          close()
          navigate(item.to)
        },
      })
    }
  }

  commands.push({
    id: `route:${DOCS_NAV_ITEM.to}`,
    label: t('nav.docs'),
    description: 'Open the public documentation view',
    group: 'Public',
    icon: DOCS_NAV_ITEM.icon,
    keywords: [DOCS_NAV_ITEM.to, 'docs', 'documentation'],
    action: () => {
      close()
      navigate(DOCS_NAV_ITEM.to)
    },
  })

  return commands
}

export function CommandPaletteProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false)

  const openCommandPalette = useCallback(() => setIsOpen(true), [])
  const closeCommandPalette = useCallback(() => setIsOpen(false), [])
  const toggleCommandPalette = useCallback(() => setIsOpen((prev) => !prev), [])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase()
      if ((event.metaKey || event.ctrlKey) && key === 'k') {
        event.preventDefault()
        setIsOpen(true)
      }
      if (event.key === 'Escape') {
        setIsOpen(false)
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <CommandPaletteContext.Provider
      value={{
        isOpen,
        openCommandPalette,
        closeCommandPalette,
        toggleCommandPalette,
      }}
    >
      {children}
      <CommandPaletteDialog />
    </CommandPaletteContext.Provider>
  )
}

function CommandPaletteDialog() {
  const { isOpen, closeCommandPalette } = useCommandPalette()
  const { theme, toggleTheme } = useTheme()
  const { hasPermission } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const inputRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)

  useEffect(() => {
    if (!isOpen) {
      setQuery('')
      setSelectedIndex(0)
      return
    }

    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const timer = window.setTimeout(() => {
      inputRef.current?.focus()
      inputRef.current?.select()
    }, 0)

    return () => {
      window.clearTimeout(timer)
      document.body.style.overflow = prevOverflow
    }
  }, [isOpen])

  const commands = useMemo(() => {
    const routeCommands = buildRouteCommands(hasPermission, t, navigate, closeCommandPalette)
    const actionCommands: PaletteCommand[] = [
      {
        id: 'action:theme',
        label: theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme',
        description: 'Toggle the dashboard appearance',
        group: 'Shell',
        icon: theme === 'dark' ? Sun : Moon,
        keywords: ['theme', 'dark', 'light', 'appearance'],
        action: () => {
          toggleTheme()
          closeCommandPalette()
        },
      },
      {
        id: 'action:reload',
        label: 'Reload app',
        description: 'Refresh the current page',
        group: 'Shell',
        icon: RefreshCw,
        keywords: ['reload', 'refresh', 'restart'],
        action: () => window.location.reload(),
      },
    ]

    return [...actionCommands, ...routeCommands]
  }, [closeCommandPalette, hasPermission, navigate, t, theme, toggleTheme])

  const filteredCommands = useMemo(() => {
    const term = query.trim().toLowerCase()
    if (!term) return commands
    return commands.filter((command) => {
      const haystack = [command.label, command.description, command.group, ...command.keywords].join(' ').toLowerCase()
      return haystack.includes(term)
    })
  }, [commands, query])

  useEffect(() => {
    setSelectedIndex((current) => {
      if (filteredCommands.length === 0) return 0
      return Math.min(current, filteredCommands.length - 1)
    })
  }, [filteredCommands.length])

  if (!isOpen) return null

  const grouped = filteredCommands.reduce<Record<string, PaletteCommand[]>>((acc, command) => {
    const bucket = acc[command.group] ?? []
    bucket.push(command)
    acc[command.group] = bucket
    return acc
  }, {})

  const groupOrder = Object.keys(grouped)
  const flatCommands = groupOrder.flatMap((group) => grouped[group])

  const runSelected = () => {
    const command = flatCommands[selectedIndex]
    if (!command) return
    command.action()
  }

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setSelectedIndex((current) => (flatCommands.length === 0 ? 0 : (current + 1) % flatCommands.length))
      return
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setSelectedIndex((current) => (flatCommands.length === 0 ? 0 : (current - 1 + flatCommands.length) % flatCommands.length))
      return
    }

    if (event.key === 'Enter') {
      event.preventDefault()
      runSelected()
      return
    }

    if (event.key === 'Escape') {
      event.preventDefault()
      closeCommandPalette()
    }
  }

  return (
    <div className="fixed inset-0 z-[120] flex items-start justify-center bg-black/55 px-4 py-10 backdrop-blur-sm">
      <button
        type="button"
        aria-label="Close command palette"
        className="absolute inset-0 cursor-default"
        onClick={closeCommandPalette}
      />

      <div className="relative z-[121] w-full max-w-2xl overflow-hidden rounded-3xl border border-white/10 bg-[color:var(--bg-card)] shadow-[0_24px_80px_rgba(0,0,0,0.5)]">
        <div className="flex items-center gap-3 border-b border-[color:var(--border)] px-4 py-4">
          <Search size={16} className="shrink-0 text-[color:var(--text-muted)]" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setSelectedIndex(0)
            }}
            onKeyDown={handleKeyDown}
            placeholder={`Search current page, routes, or actions... (${location.pathname})`}
            className="w-full bg-transparent text-sm text-[color:var(--text-primary)] outline-none placeholder:text-[color:var(--text-muted)]"
          />
          <button
            type="button"
            onClick={closeCommandPalette}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[color:var(--text-muted)] transition-colors hover:bg-white/5 hover:text-[color:var(--text-primary)]"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-2">
          {flatCommands.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-[color:var(--text-muted)]">
              No matches found
            </div>
          ) : (
            groupOrder.map((group) => (
              <div key={group} className="mb-3 last:mb-0">
                <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
                  {group}
                </div>
                <div className="space-y-1">
                  {grouped[group].map((command) => {
                    const index = flatCommands.findIndex((item) => item.id === command.id)
                    const active = index === selectedIndex

                    return (
                      <button
                        key={command.id}
                        type="button"
                        onMouseEnter={() => setSelectedIndex(index)}
                        onClick={command.action}
                        className={`flex w-full items-center gap-3 rounded-2xl border px-3 py-3 text-left transition-colors ${
                          active
                            ? 'border-[color:var(--border-accent)] bg-[color:var(--surface-active)]'
                            : 'border-transparent hover:bg-white/5'
                        }`}
                      >
                        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[color:var(--surface-hover)] text-[color:var(--border-accent)]">
                          <command.icon size={16} />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-[color:var(--text-primary)]">
                            {command.label}
                          </span>
                          <span className="block truncate text-xs text-[color:var(--text-muted)]">
                            {command.description}
                          </span>
                        </span>
                        <span className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
                          {active ? 'Selected' : command.group}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

