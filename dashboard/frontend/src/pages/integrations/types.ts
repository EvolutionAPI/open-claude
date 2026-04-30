import { type LucideIcon, Database, DollarSign, GitBranch, GitFork, Globe, Hash, Image, Key, Mail, MessageSquare, Phone, Plug, Send, Video, Camera, Briefcase, BookOpen, Calendar, Zap, ListTodo } from 'lucide-react'

export interface Integration {
  name: string
  type: string
  status: 'ok' | 'error' | 'pending'
  kind: 'core' | 'custom'
  slug?: string
  description?: string
  envKeys?: string[]
  category?: string
}

export interface SocialAccount {
  index: number
  label: string
  status: string
  detail: string
  days_left: number | null
}

export interface SocialPlatform {
  id: string
  name: string
  icon: string
  accounts: SocialAccount[]
  has_connected: boolean
}

export interface DatabaseConnection {
  index: number
  label: string
  host: string | null
  port: number | null
  database: string | null
  ssl_mode?: string | null
  tls?: boolean
  allow_write: boolean
  query_timeout: number
  max_rows: number
}

export interface DatabaseFlavor {
  slug: 'postgres' | 'mysql' | 'mongo' | 'redis' | string
  skill: string
  ok: boolean
  count: number
  connections: DatabaseConnection[]
  error?: string
}

export type TabKey = 'integrations' | 'social' | 'databases'

export interface CustomIntegrationForm {
  displayName: string
  slug: string
  description: string
  category: string
  envKeys: { name: string; value: string }[]
}

export interface DbFormState {
  label: string
  host: string
  port: string
  database: string
  user: string
  password: string
  ssl_mode: string
  ssl_ca_path: string
  dsn: string
  uri: string
  auth_source: string
  tls: boolean
  url: string
  db: string
  username: string
  allow_write: boolean
  query_timeout: string
  max_rows: string
}

export interface FlavorMeta {
  color: string
  colorMuted: string
  label: string
  defaultPort: number
}

export interface IconMeta {
  icon: LucideIcon
  color: string
  colorMuted: string
  glowColor?: string
}

export const TYPE_META: Record<string, IconMeta> = {
  api: { icon: Globe, color: '#60A5FA', colorMuted: 'rgba(96,165,250,0.12)', glowColor: 'rgba(96,165,250,0.15)' },
  mcp: { icon: Plug, color: '#A78BFA', colorMuted: 'rgba(167,139,250,0.12)', glowColor: 'rgba(167,139,250,0.15)' },
  cli: { icon: Database, color: '#22D3EE', colorMuted: 'rgba(34,211,238,0.12)', glowColor: 'rgba(34,211,238,0.15)' },
  erp: { icon: DollarSign, color: '#34D399', colorMuted: 'rgba(52,211,153,0.12)', glowColor: 'rgba(52,211,153,0.15)' },
  bot: { icon: MessageSquare, color: '#FBBF24', colorMuted: 'rgba(251,191,36,0.12)', glowColor: 'rgba(251,191,36,0.15)' },
  oauth: { icon: Globe, color: '#F472B6', colorMuted: 'rgba(244,114,182,0.12)', glowColor: 'rgba(244,114,182,0.15)' },
}

export const DEFAULT_TYPE: IconMeta = {
  icon: Plug,
  color: '#8b949e',
  colorMuted: 'rgba(139,148,158,0.12)',
  glowColor: 'rgba(139,148,158,0.15)',
}

export const INTEGRATION_ICONS: Record<string, IconMeta> = {
  omie: { icon: DollarSign, color: '#34D399', colorMuted: 'rgba(52,211,153,0.12)' },
  stripe: { icon: DollarSign, color: '#635BFF', colorMuted: 'rgba(99,91,255,0.12)' },
  bling: { icon: DollarSign, color: '#3B82F6', colorMuted: 'rgba(59,130,246,0.12)' },
  asaas: { icon: Zap, color: '#FBBF24', colorMuted: 'rgba(251,191,36,0.12)' },
  todoist: { icon: ListTodo, color: '#E44332', colorMuted: 'rgba(228,67,50,0.12)' },
  fathom: { icon: Video, color: '#7C3AED', colorMuted: 'rgba(124,58,237,0.12)' },
  discord: { icon: Hash, color: '#5865F2', colorMuted: 'rgba(88,101,242,0.12)' },
  telegram: { icon: Send, color: '#26A5E4', colorMuted: 'rgba(38,165,228,0.12)' },
  whatsapp: { icon: Phone, color: '#25D366', colorMuted: 'rgba(37,211,102,0.12)' },
  licensing: { icon: Key, color: '#00FFA7', colorMuted: 'rgba(0,255,167,0.12)' },
  'evolution api': { icon: MessageSquare, color: '#00FFA7', colorMuted: 'rgba(0,255,167,0.12)' },
  'evolution go': { icon: GitBranch, color: '#00FFA7', colorMuted: 'rgba(0,255,167,0.12)' },
  'evo crm': { icon: Database, color: '#00FFA7', colorMuted: 'rgba(0,255,167,0.12)' },
  'ai image creator': { icon: Image, color: '#F472B6', colorMuted: 'rgba(244,114,182,0.12)' },
  github: { icon: GitFork, color: '#E6EDF3', colorMuted: 'rgba(230,237,243,0.12)' },
  linear: { icon: BookOpen, color: '#5E6AD2', colorMuted: 'rgba(94,106,210,0.12)' },
  'google calendar': { icon: Calendar, color: '#4285F4', colorMuted: 'rgba(66,133,244,0.12)' },
  gmail: { icon: Mail, color: '#EA4335', colorMuted: 'rgba(234,67,53,0.12)' },
  youtube: { icon: Video, color: '#FF0000', colorMuted: 'rgba(255,0,0,0.12)' },
  instagram: { icon: Camera, color: '#E4405F', colorMuted: 'rgba(228,64,95,0.12)' },
  linkedin: { icon: Briefcase, color: '#0A66C2', colorMuted: 'rgba(10,102,194,0.12)' },
  notion: { icon: BookOpen, color: '#FFFFFF', colorMuted: 'rgba(255,255,255,0.08)' },
  canva: { icon: Globe, color: '#00C4CC', colorMuted: 'rgba(0,196,204,0.12)' },
  figma: { icon: Globe, color: '#A259FF', colorMuted: 'rgba(162,89,255,0.12)' },
}

export const PLATFORM_ICONS: Record<string, IconMeta> = {
  youtube: { icon: Video, color: '#EF4444', colorMuted: 'rgba(239,68,68,0.12)', glowColor: 'rgba(239,68,68,0.15)' },
  instagram: { icon: Camera, color: '#E879F9', colorMuted: 'rgba(232,121,249,0.12)', glowColor: 'rgba(232,121,249,0.15)' },
  linkedin: { icon: Briefcase, color: '#60A5FA', colorMuted: 'rgba(96,165,250,0.12)', glowColor: 'rgba(96,165,250,0.15)' },
}

export const DEFAULT_PLATFORM: IconMeta = {
  icon: Globe,
  color: '#8b949e',
  colorMuted: 'rgba(139,148,158,0.12)',
  glowColor: 'rgba(139,148,158,0.15)',
}

export const CATEGORY_OPTIONS = [
  { value: 'messaging', label: 'Messaging' },
  { value: 'payments', label: 'Payments' },
  { value: 'crm', label: 'CRM' },
  { value: 'social', label: 'Social' },
  { value: 'productivity', label: 'Productivity' },
  { value: 'other', label: 'Other' },
]

export const EMPTY_FORM: CustomIntegrationForm = {
  displayName: '',
  slug: '',
  description: '',
  category: 'other',
  envKeys: [],
}

export const DB_FLAVOR_META: Record<string, FlavorMeta> = {
  postgres: { color: '#00AEEF', colorMuted: 'rgba(0,174,239,0.10)', label: 'Postgres', defaultPort: 5432 },
  mysql: { color: '#F29111', colorMuted: 'rgba(242,145,17,0.10)', label: 'MySQL', defaultPort: 3306 },
  mongo: { color: '#4DB33D', colorMuted: 'rgba(77,179,61,0.10)', label: 'MongoDB', defaultPort: 27017 },
  redis: { color: '#DC382D', colorMuted: 'rgba(220,56,45,0.10)', label: 'Redis', defaultPort: 6379 },
}

export const EMPTY_DB_FORM: DbFormState = {
  label: '',
  host: '',
  port: '',
  database: '',
  user: '',
  password: '',
  ssl_mode: '',
  ssl_ca_path: '',
  dsn: '',
  uri: '',
  auth_source: '',
  tls: false,
  url: '',
  db: '',
  username: '',
  allow_write: false,
  query_timeout: '',
  max_rows: '',
}

export const SSL_MODES_POSTGRES = ['', 'disable', 'require', 'verify-ca', 'verify-full']

export const inputClass = 'w-full bg-[#161b22] border border-[#21262d] rounded-lg px-3 py-2 text-sm text-[#e6edf3] placeholder:text-[#3F3F46] focus:outline-none focus:border-[#00FFA7]/40 focus:ring-1 focus:ring-[#00FFA7]/20 transition-colors'

export function getIntegrationIcon(name: string) {
  const key = Object.keys(INTEGRATION_ICONS).find((k) => name.toLowerCase().includes(k))
  return key ? INTEGRATION_ICONS[key] : null
}

export function getTypeMeta(type: string) {
  if (!type) return DEFAULT_TYPE
  const key = Object.keys(TYPE_META).find((k) => type.toLowerCase().includes(k))
  return key ? TYPE_META[key] : DEFAULT_TYPE
}

export function getPlatformMeta(id: string) {
  const key = Object.keys(PLATFORM_ICONS).find((k) => id.toLowerCase().includes(k))
  return key ? PLATFORM_ICONS[key] : DEFAULT_PLATFORM
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9 -]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}
