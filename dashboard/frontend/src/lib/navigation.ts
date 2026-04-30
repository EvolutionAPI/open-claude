import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  BookOpen,
  Bot,
  BarChart3,
  Brain,
  Calendar,
  CalendarClock,
  Cpu,
  Database,
  DollarSign,
  FolderOpen,
  HardDriveDownload,
  Heart,
  Layout,
  LayoutDashboard,
  Library,
  Monitor,
  Plug,
  Puzzle,
  ScrollText,
  Settings,
  Share2,
  Shield,
  Target,
  Ticket,
  Users,
  Webhook,
  Clock,
  Zap,
} from 'lucide-react'

export interface NavItem {
  to: string
  labelKey: string
  icon: LucideIcon
  resource: string | null
  desktopOnly?: boolean
}

export interface NavGroup {
  key: string
  collapsible: boolean
  adminOnly?: boolean
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'main',
    collapsible: false,
    items: [
      { to: '/', labelKey: 'overview', icon: LayoutDashboard, resource: null },
    ],
  },
  {
    key: 'operations',
    collapsible: true,
    items: [
      { to: '/agents', labelKey: 'agents', icon: Bot, resource: 'agents' },
      { to: '/skills', labelKey: 'skills', icon: Zap, resource: 'skills' },
      { to: '/routines', labelKey: 'routines', icon: Clock, resource: 'routines' },
      { to: '/tasks', labelKey: 'tasks', icon: CalendarClock, resource: 'tasks' },
      { to: '/triggers', labelKey: 'triggers', icon: Webhook, resource: 'triggers' },
      { to: '/heartbeats', labelKey: 'heartbeats', icon: Heart, resource: 'heartbeats' },
      { to: '/activity', labelKey: 'activity', icon: Activity, resource: 'scheduler' },
      { to: '/goals', labelKey: 'goals', icon: Target, resource: 'goals' },
      { to: '/topics', labelKey: 'issues', icon: Ticket, resource: 'tickets' },
      { to: '/templates', labelKey: 'templates', icon: Layout, resource: 'templates' },
    ],
  },
  {
    key: 'data',
    collapsible: true,
    items: [
      { to: '/workspace', labelKey: 'workspace', icon: FolderOpen, resource: 'workspace' },
      { to: '/shares', labelKey: 'shareLinks', icon: Share2, resource: 'workspace' },
      { to: '/memory', labelKey: 'memory', icon: Brain, resource: 'memory' },
      { to: '/mempalace', labelKey: 'mempalace', icon: Library, resource: 'mempalace' },
      { to: '/knowledge', labelKey: 'knowledge', icon: Database, resource: 'knowledge' },
      { to: '/agent-knowledge', labelKey: 'agentKnowledge', icon: Bot, resource: 'knowledge' },
      { to: '/costs', labelKey: 'costs', icon: DollarSign, resource: 'costs' },
    ],
  },
  {
    key: 'system',
    collapsible: true,
    items: [
      { to: '/settings', labelKey: 'settings', icon: Settings, resource: 'config' },
      { to: '/systems', labelKey: 'systems', icon: Monitor, resource: 'systems' },
      { to: '/observability', labelKey: 'observability', icon: BarChart3, resource: 'systems' },
      { to: '/providers', labelKey: 'providers', icon: Cpu, resource: 'config' },
      { to: '/plugins', labelKey: 'plugins', icon: Puzzle, resource: 'config' },
      { to: '/integrations', labelKey: 'integrations', icon: Plug, resource: 'integrations' },
      { to: '/scheduler', labelKey: 'scheduler', icon: Calendar, resource: 'scheduler' },
      { to: '/backups', labelKey: 'backups', icon: HardDriveDownload, resource: 'config' },
    ],
  },
  {
    key: 'admin',
    collapsible: true,
    adminOnly: true,
    items: [
      { to: '/users', labelKey: 'users', icon: Users, resource: 'users' },
      { to: '/roles', labelKey: 'roles', icon: Shield, resource: 'users' },
      { to: '/audit', labelKey: 'audit', icon: ScrollText, resource: 'audit' },
    ],
  },
]

export const DOCS_NAV_ITEM: NavItem = {
  to: '/docs',
  labelKey: 'docs',
  icon: BookOpen,
  resource: null,
}

export function getVisibleNavGroups(hasPermission: (resource: string, action: string) => boolean): NavGroup[] {
  return NAV_GROUPS
    .map((group) => {
      const items = group.items.filter((item) => item.resource === null || hasPermission(item.resource, 'view'))
      if (items.length === 0) return null

      if (group.adminOnly) {
        const hasAnyAdmin = group.items.some((item) => item.resource && hasPermission(item.resource, 'view'))
        if (!hasAnyAdmin) return null
      }

      return { ...group, items }
    })
    .filter((group): group is NavGroup => group !== null)
}

export function getVisibleNavItems(hasPermission: (resource: string, action: string) => boolean): NavItem[] {
  return [...getVisibleNavGroups(hasPermission).flatMap((group) => group.items), DOCS_NAV_ITEM]
}
