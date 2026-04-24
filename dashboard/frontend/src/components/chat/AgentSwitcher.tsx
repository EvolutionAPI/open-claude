import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, ChevronDown, History, Bot, X } from 'lucide-react'
import { api } from '../../lib/api'
import { AgentAvatar } from '../AgentAvatar'

interface AgentLite {
  name: string
  description?: string
  custom?: boolean
  locked?: boolean
}

interface AgentSwitcherProps {
  currentAgent: string
  accentColor?: string
}

const RECENT_KEY = 'evo:recent-agents'
const MAX_RECENT = 6

function getRecentAgents(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    if (!raw) return []
    const data = JSON.parse(raw) as { name: string; ts: number }[]
    return data.sort((a, b) => b.ts - a.ts).map(d => d.name).slice(0, MAX_RECENT)
  } catch {
    return []
  }
}

function formatName(slug: string): string {
  return slug
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

export default function AgentSwitcher({ currentAgent, accentColor = '#00FFA7' }: AgentSwitcherProps) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [agents, setAgents] = useState<AgentLite[]>([])
  const [activeIndex, setActiveIndex] = useState(0)
  const [recents] = useState(getRecentAgents)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // Lazy-load agents list when panel first opens
  useEffect(() => {
    if (!open || agents.length > 0) return
    api.get('/agents')
      .then((data) => setAgents(Array.isArray(data) ? data : []))
      .catch(() => setAgents([]))
  }, [open, agents.length])

  const openPanel = useCallback(() => {
    setQuery('')
    setActiveIndex(0)
    setOpen(true)
    requestAnimationFrame(() => searchRef.current?.focus())
  }, [])

  const togglePanel = useCallback(() => {
    setOpen((v) => {
      if (!v) {
        setQuery('')
        setActiveIndex(0)
        requestAnimationFrame(() => searchRef.current?.focus())
      }
      return !v
    })
  }, [])

  // Cmd/Ctrl+K opens the switcher globally
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const isMac = navigator.platform.toLowerCase().includes('mac')
      const mod = isMac ? e.metaKey : e.ctrlKey
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        if (open) setOpen(false)
        else openPanel()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, openPanel])

  // Click outside to close
  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      const target = e.target as Node
      if (
        panelRef.current && !panelRef.current.contains(target) &&
        triggerRef.current && !triggerRef.current.contains(target)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  // Group: recents (filtered) at top, then all (filtered, alpha)
  const items = useMemo(() => {
    const q = query.trim().toLowerCase()
    const accessible = agents.filter((a) => !a.locked && a.name !== currentAgent)
    const matches = (a: AgentLite) => {
      if (!q) return true
      return a.name.toLowerCase().includes(q) || (a.description || '').toLowerCase().includes(q)
    }

    const recentSet = new Set(recents)
    const recentMatches = recents
      .map(name => accessible.find(a => a.name === name))
      .filter((a): a is AgentLite => !!a && matches(a))

    const otherMatches = accessible
      .filter(a => !recentSet.has(a.name) && matches(a))
      .sort((x, y) => x.name.localeCompare(y.name))

    type Item = { type: 'recent' | 'all'; agent: AgentLite }
    const flat: Item[] = [
      ...recentMatches.map((a): Item => ({ type: 'recent', agent: a })),
      ...otherMatches.map((a): Item => ({ type: 'all', agent: a })),
    ]
    return { recents: recentMatches, others: otherMatches, flat }
  }, [agents, query, recents, currentAgent])

  const select = (name: string) => {
    setOpen(false)
    if (name !== currentAgent) navigate(`/agents/${name}`)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
      triggerRef.current?.focus()
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, items.flat.length - 1))
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      const target = items.flat[activeIndex]
      if (target) select(target.agent.name)
    }
  }

  // Scroll active item into view
  useEffect(() => {
    if (!open) return
    const list = listRef.current
    if (!list) return
    const active = list.querySelector<HTMLElement>(`[data-idx="${activeIndex}"]`)
    if (active) active.scrollIntoView({ block: 'nearest' })
  }, [activeIndex, open])

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        onClick={togglePanel}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`Switch agent (current: ${formatName(currentAgent)})`}
        className="group flex items-center gap-3 rounded-lg px-2 py-1.5 -mx-2 transition-colors hover:bg-[#152030] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#00FFA7]/40"
      >
        <div
          className="rounded-full flex-shrink-0"
          style={{ padding: 2, background: `${accentColor}40` }}
        >
          <AgentAvatar name={currentAgent} size={44} />
        </div>
        <div className="flex flex-col min-w-0 text-left">
          <span className="text-[14px] font-semibold text-[#e6edf3] tracking-tight truncate flex items-center gap-1.5">
            {formatName(currentAgent)}
            <ChevronDown
              size={14}
              className="text-[#5a6b7f] transition-transform group-hover:text-[#e6edf3]"
              style={{ transform: open ? 'rotate(180deg)' : 'none' }}
            />
          </span>
          <span className="text-[10px] uppercase tracking-[0.12em] text-[#5a6b7f] hidden sm:inline">
            Switch agent · ⌘K
          </span>
        </div>
      </button>

      {open && (
        <div
          ref={panelRef}
          role="dialog"
          aria-label="Agent switcher"
          className="absolute left-0 top-full mt-2 w-[360px] max-w-[calc(100vw-2rem)] rounded-xl border border-[#152030] bg-[#0b1018] shadow-[0_12px_50px_rgba(0,0,0,0.5)] z-50 flex flex-col overflow-hidden"
          onKeyDown={onKeyDown}
        >
          {/* Search */}
          <div className="flex items-center gap-2 px-3 py-2.5 border-b border-[#152030]">
            <Search size={14} className="text-[#5a6b7f] flex-shrink-0" aria-hidden />
            <input
              ref={searchRef}
              type="search"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setActiveIndex(0) }}
              placeholder="Search agents…"
              aria-label="Search agents"
              className="flex-1 min-w-0 bg-transparent text-[13px] text-[#e6edf3] placeholder:text-[#5a6b7f] focus:outline-none"
            />
            {query && (
              <button
                type="button"
                onClick={() => { setQuery(''); searchRef.current?.focus() }}
                aria-label="Clear search"
                className="p-0.5 rounded text-[#5a6b7f] hover:text-[#e6edf3] hover:bg-[#152030] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#00FFA7]/40"
              >
                <X size={12} />
              </button>
            )}
            <kbd className="hidden sm:inline-block ml-1 text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#080c14] border border-[#152030] text-[#5a6b7f]">
              esc
            </kbd>
          </div>

          {/* List */}
          <div ref={listRef} role="listbox" aria-label="Agents" className="flex-1 overflow-y-auto max-h-[420px] py-1">
            {agents.length === 0 ? (
              <div className="px-4 py-6 text-center text-[12px] text-[#5a6b7f]">Loading agents…</div>
            ) : items.flat.length === 0 ? (
              <div className="px-4 py-6 text-center text-[12px] text-[#5a6b7f]">No matches.</div>
            ) : (
              <>
                {items.recents.length > 0 && (
                  <div>
                    <div className="px-3 pt-2 pb-1 flex items-center gap-1.5">
                      <History size={10} className="text-[#5a6b7f]" aria-hidden />
                      <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#5a6b7f]">
                        Recent
                      </span>
                    </div>
                    {items.recents.map((a, i) => (
                      <SwitcherRow
                        key={a.name}
                        agent={a}
                        idx={i}
                        active={i === activeIndex}
                        onMouseEnter={() => setActiveIndex(i)}
                        onClick={() => select(a.name)}
                      />
                    ))}
                  </div>
                )}
                {items.others.length > 0 && (
                  <div>
                    <div className="px-3 pt-3 pb-1 flex items-center gap-1.5">
                      <Bot size={10} className="text-[#5a6b7f]" aria-hidden />
                      <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#5a6b7f]">
                        All agents
                      </span>
                    </div>
                    {items.others.map((a, i) => {
                      const idx = items.recents.length + i
                      return (
                        <SwitcherRow
                          key={a.name}
                          agent={a}
                          idx={idx}
                          active={idx === activeIndex}
                          onMouseEnter={() => setActiveIndex(idx)}
                          onClick={() => select(a.name)}
                        />
                      )
                    })}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Footer hints */}
          <div className="flex items-center justify-between gap-2 px-3 py-2 border-t border-[#152030] text-[10px] text-[#5a6b7f]">
            <div className="flex items-center gap-2">
              <kbd className="font-mono px-1.5 py-0.5 rounded bg-[#080c14] border border-[#152030]">↑↓</kbd>
              <span>navigate</span>
              <kbd className="font-mono px-1.5 py-0.5 rounded bg-[#080c14] border border-[#152030]">↵</kbd>
              <span>open</span>
            </div>
            <span>{items.flat.length} {items.flat.length === 1 ? 'agent' : 'agents'}</span>
          </div>
        </div>
      )}
    </div>
  )
}

interface RowProps {
  agent: AgentLite
  idx: number
  active: boolean
  onMouseEnter: () => void
  onClick: () => void
}

function SwitcherRow({ agent, idx, active, onMouseEnter, onClick }: RowProps) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={active}
      data-idx={idx}
      onMouseEnter={onMouseEnter}
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-3 py-2 text-left transition-colors focus:outline-none ${
        active ? 'bg-[#00FFA7]/10' : 'hover:bg-[#152030]'
      }`}
    >
      <AgentAvatar name={agent.name} size={28} />
      <div className="flex-1 min-w-0">
        <div className={`text-[12.5px] font-medium truncate ${active ? 'text-[#00FFA7]' : 'text-[#e6edf3]'}`}>
          {formatName(agent.name)}
        </div>
        {agent.description && (
          <div className="text-[10.5px] text-[#5a6b7f] truncate">{agent.description}</div>
        )}
      </div>
      {agent.custom && (
        <span className="text-[9px] uppercase tracking-wider text-[#C084FC] flex-shrink-0">custom</span>
      )}
    </button>
  )
}
