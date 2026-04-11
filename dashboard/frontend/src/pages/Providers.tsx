import { useEffect, useState } from 'react'
import {
  CheckCircle2,
  AlertCircle,
  Download,
  Star,
  RefreshCw,
  Settings2,
  X,
  Zap,
  TestTube2,
  type LucideIcon,
} from 'lucide-react'
import { api } from '../lib/api'

interface ProviderEnvVars {
  [key: string]: string
}

interface Provider {
  id: string
  name: string
  description: string
  cli_command: string
  is_active: boolean
  installed: boolean
  version: string | null
  path: string | null
  has_config: boolean
  env_vars: ProviderEnvVars
  requires_logout: boolean
  setup_hint: string | null
  default_model: string | null
  default_base_url: string | null
  default_region: string | null
}

interface ProvidersResponse {
  providers: Provider[]
  active_provider: string
  claude_installed: boolean
  openclaude_installed: boolean
}

// Env var display names
const ENV_VAR_LABELS: Record<string, string> = {
  CLAUDE_CODE_USE_OPENAI: 'Use OpenAI (flag)',
  CLAUDE_CODE_USE_GEMINI: 'Use Gemini (flag)',
  CLAUDE_CODE_USE_BEDROCK: 'Use Bedrock (flag)',
  CLAUDE_CODE_USE_VERTEX: 'Use Vertex (flag)',
  OPENAI_BASE_URL: 'Base URL',
  OPENAI_API_KEY: 'API Key',
  OPENAI_MODEL: 'Model',
  GEMINI_API_KEY: 'API Key',
  GEMINI_MODEL: 'Model',
  AWS_REGION: 'AWS Region',
  AWS_BEARER_TOKEN_BEDROCK: 'Bearer Token',
  ANTHROPIC_VERTEX_PROJECT_ID: 'GCP Project ID',
  CLOUD_ML_REGION: 'Region',
}

// Provider accent colors
const PROVIDER_COLORS: Record<string, string> = {
  anthropic: '#D4A574',
  openrouter: '#6366F1',
  openai: '#10A37F',
  gemini: '#4285F4',
  codex_auth: '#10A37F',
  bedrock: '#FF9900',
  vertex: '#4285F4',
}

function getColor(id: string) {
  return PROVIDER_COLORS[id] || '#8b949e'
}

function isFlag(key: string) {
  return key.startsWith('CLAUDE_CODE_USE_')
}

function isSecret(key: string) {
  return key.includes('KEY') || key.includes('SECRET') || key.includes('TOKEN')
}

export default function Providers() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [loading, setLoading] = useState(true)
  const [configOpen, setConfigOpen] = useState<string | null>(null)
  const [editVars, setEditVars] = useState<ProviderEnvVars>({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [claudeInstalled, setClaudeInstalled] = useState(false)
  const [openclaudeInstalled, setOpenclaudeInstalled] = useState(false)

  const load = () => {
    setLoading(true)
    api
      .get('/providers')
      .then((data: ProvidersResponse) => {
        setProviders(data.providers || [])
        setClaudeInstalled(data.claude_installed)
        setOpenclaudeInstalled(data.openclaude_installed)
      })
      .catch(() => setProviders([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleActivate = async (id: string) => {
    try {
      await api.post('/providers/active', { provider_id: id })
      load()
    } catch (e) {
      console.error(e)
    }
  }

  const openConfig = (prov: Provider) => {
    // Load real env var values (API will return masked values for secrets)
    setConfigOpen(prov.id)
    setTestResult(null)
    // Initialize with current values, replacing masked with empty for editing
    const vars: ProviderEnvVars = {}
    for (const [k, v] of Object.entries(prov.env_vars)) {
      if (isFlag(k)) continue // Skip flags — they're automatic
      vars[k] = v.includes('****') ? '' : v
    }
    setEditVars(vars)
  }

  const handleSave = async () => {
    if (!configOpen) return
    setSaving(true)
    try {
      // Find the provider to get defaults
      const prov = providers.find(p => p.id === configOpen)
      const finalVars = { ...editVars }

      // Auto-fill defaults if empty
      if (prov?.default_base_url && !finalVars.OPENAI_BASE_URL) {
        finalVars.OPENAI_BASE_URL = prov.default_base_url
      }
      if (prov?.default_model) {
        const modelKey = Object.keys(finalVars).find(k => k.includes('MODEL'))
        if (modelKey && !finalVars[modelKey]) {
          finalVars[modelKey] = prov.default_model
        }
      }

      await api.post(`/providers/${configOpen}/config`, { env_vars: finalVars })
      setConfigOpen(null)
      load()
    } catch (e) {
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async (id: string) => {
    setTesting(id)
    setTestResult(null)
    try {
      const result = await api.post(`/providers/${id}/test`) as any
      setTestResult({
        success: result.success,
        message: result.success
          ? `${result.cli} ${result.version}`
          : result.error || 'Test failed',
      })
    } catch (e) {
      setTestResult({ success: false, message: 'Request failed' })
    } finally {
      setTesting(null)
    }
  }

  const activeCount = providers.filter(p => p.is_active).length
  const configuredCount = providers.filter(p => p.has_config && p.installed).length

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#e6edf3] tracking-tight">Providers</h1>
        <p className="text-[#667085] text-sm mt-1">
          Configure which AI provider powers EvoNexus — Anthropic (native), OpenRouter, OpenAI, Gemini, and more
        </p>
      </div>

      {/* Install status banner */}
      {!loading && (
        <div className="flex flex-wrap gap-3 mb-6">
          <span className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border ${
            claudeInstalled
              ? 'bg-[#00FFA7]/10 text-[#00FFA7] border-[#00FFA7]/25'
              : 'bg-red-500/10 text-red-400 border-red-500/25'
          }`}>
            {claudeInstalled ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
            claude {claudeInstalled ? 'installed' : 'not found'}
          </span>
          <span className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border ${
            openclaudeInstalled
              ? 'bg-[#00FFA7]/10 text-[#00FFA7] border-[#00FFA7]/25'
              : 'bg-[#FBBF24]/10 text-[#FBBF24] border-[#FBBF24]/25'
          }`}>
            {openclaudeInstalled ? <CheckCircle2 size={12} /> : <Download size={12} />}
            openclaude {openclaudeInstalled ? 'installed' : (
              <span className="text-[#667085]">
                — <code className="text-[#8b949e]">npm install -g @gitlawb/openclaude</code>
              </span>
            )}
          </span>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        {loading ? (
          <>
            <div className="skeleton h-20 rounded-2xl" />
            <div className="skeleton h-20 rounded-2xl" />
            <div className="skeleton h-20 rounded-2xl" />
          </>
        ) : (
          <>
            <div className="bg-[#161b22] border border-[#21262d] rounded-2xl p-4">
              <p className="text-2xl font-bold text-[#e6edf3]">{providers.length}</p>
              <p className="text-sm text-[#667085]">Available</p>
            </div>
            <div className="bg-[#161b22] border border-[#21262d] rounded-2xl p-4">
              <p className="text-2xl font-bold text-[#e6edf3]">{configuredCount}</p>
              <p className="text-sm text-[#667085]">Configured</p>
            </div>
            <div className="bg-[#161b22] border border-[#21262d] rounded-2xl p-4">
              <p className="text-2xl font-bold text-[#00FFA7]">{activeCount}</p>
              <p className="text-sm text-[#667085]">Active</p>
            </div>
          </>
        )}
      </div>

      {/* Provider Cards */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="skeleton h-48 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {providers.map((prov) => {
            const color = getColor(prov.id)
            const isInstalled = prov.cli_command === 'claude' ? claudeInstalled : openclaudeInstalled

            return (
              <div
                key={prov.id}
                className={`group relative rounded-xl border bg-[#161b22] p-5 transition-all duration-300 ${
                  prov.is_active
                    ? 'border-[#00FFA7]/40 shadow-[0_0_20px_rgba(0,255,167,0.08)]'
                    : 'border-[#21262d] hover:border-[#30363d]'
                }`}
              >
                {/* Active indicator */}
                {prov.is_active && (
                  <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#00FFA7]/50 to-transparent rounded-t-xl" />
                )}

                {/* Header */}
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: color }}
                      />
                      <h3 className="text-base font-semibold text-[#e6edf3]">{prov.name}</h3>
                    </div>
                    <p className="text-xs text-[#667085] mt-1">{prov.description}</p>
                  </div>
                  {prov.is_active && (
                    <span className="flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-[#00FFA7]/10 text-[#00FFA7] border border-[#00FFA7]/25 whitespace-nowrap">
                      <Star size={9} /> Active
                    </span>
                  )}
                </div>

                {/* CLI badge */}
                <div className="flex items-center gap-2 mb-3">
                  <code className="text-[10px] px-2 py-0.5 rounded bg-[#0C111D] text-[#8b949e] border border-[#21262d]">
                    {prov.cli_command}
                  </code>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
                    isInstalled
                      ? 'bg-[#00FFA7]/10 text-[#00FFA7] border-[#00FFA7]/25'
                      : 'bg-red-500/10 text-red-400 border-red-500/25'
                  }`}>
                    {isInstalled ? 'installed' : 'not found'}
                  </span>
                  {prov.has_config && Object.keys(prov.env_vars).length > 0 && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#00FFA7]/10 text-[#00FFA7] border border-[#00FFA7]/25">
                      configured
                    </span>
                  )}
                </div>

                {/* Logout warning */}
                {prov.requires_logout && prov.is_active && (
                  <p className="text-[10px] text-[#FBBF24] mb-3">
                    Run <code>/logout</code> in Claude Code if you were previously logged into Anthropic
                  </p>
                )}

                {/* Actions */}
                <div className="flex items-center gap-2 mt-auto pt-3 border-t border-[#21262d]">
                  <button
                    onClick={() => openConfig(prov)}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-white/[0.04] text-[#8b949e] border border-[#21262d] hover:bg-white/[0.08] hover:text-white transition-all"
                  >
                    <Settings2 size={12} />
                    Configure
                  </button>

                  {!prov.is_active && isInstalled && (
                    <button
                      onClick={() => handleActivate(prov.id)}
                      className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-[#00FFA7]/10 text-[#00FFA7] border border-[#00FFA7]/20 hover:bg-[#00FFA7]/20 transition-all"
                    >
                      <Zap size={12} />
                      Activate
                    </button>
                  )}

                  <button
                    onClick={() => handleTest(prov.id)}
                    disabled={testing === prov.id}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-white/[0.04] text-[#8b949e] border border-[#21262d] hover:bg-white/[0.08] hover:text-white transition-all disabled:opacity-50"
                  >
                    {testing === prov.id ? (
                      <RefreshCw size={12} className="animate-spin" />
                    ) : (
                      <TestTube2 size={12} />
                    )}
                    Test
                  </button>
                </div>

                {/* Test result inline */}
                {testResult && configOpen !== prov.id && testing !== prov.id && (
                  <div className={`mt-2 text-[10px] px-2 py-1 rounded ${
                    testResult.success
                      ? 'bg-[#00FFA7]/10 text-[#00FFA7]'
                      : 'bg-red-500/10 text-red-400'
                  }`}>
                    {testResult.message}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Configuration Modal */}
      {configOpen && (() => {
        const prov = providers.find(p => p.id === configOpen)
        if (!prov) return null
        const editableVars = Object.entries(prov.env_vars).filter(([k]) => !isFlag(k))

        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="w-full max-w-lg mx-4 bg-[#161b22] border border-[#21262d] rounded-2xl shadow-2xl">
              {/* Modal header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-[#21262d]">
                <div className="flex items-center gap-3">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: getColor(prov.id) }}
                  />
                  <h2 className="text-lg font-semibold text-[#e6edf3]">
                    Configure {prov.name}
                  </h2>
                </div>
                <button
                  onClick={() => { setConfigOpen(null); setTestResult(null) }}
                  className="p-1 rounded-lg hover:bg-white/[0.08] text-[#667085] hover:text-white transition-colors"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Modal body */}
              <div className="px-6 py-5 space-y-4">
                {editableVars.length === 0 ? (
                  <p className="text-sm text-[#667085]">
                    No configuration needed — uses native Claude Code authentication.
                  </p>
                ) : (
                  editableVars.map(([key]) => (
                    <div key={key}>
                      <label className="block text-xs font-medium text-[#8b949e] mb-1.5">
                        {ENV_VAR_LABELS[key] || key}
                        <span className="ml-1 text-[#667085] font-normal">({key})</span>
                      </label>
                      <input
                        type={isSecret(key) ? 'password' : 'text'}
                        value={editVars[key] || ''}
                        onChange={(e) => setEditVars(prev => ({ ...prev, [key]: e.target.value }))}
                        placeholder={
                          key === 'OPENAI_BASE_URL' ? (prov.default_base_url || 'https://...') :
                          key.includes('MODEL') ? (prov.default_model || 'model-name') :
                          key.includes('REGION') ? (prov.default_region || 'us-east-1') :
                          key.includes('KEY') ? 'sk-...' :
                          ''
                        }
                        className="w-full px-3 py-2 text-sm bg-[#0C111D] border border-[#21262d] rounded-lg text-[#e6edf3] placeholder-[#667085] focus:outline-none focus:border-[#00FFA7]/50 focus:ring-1 focus:ring-[#00FFA7]/20 transition-all font-mono"
                      />
                    </div>
                  ))
                )}

                {/* Defaults hint */}
                {prov.default_model && (
                  <p className="text-[10px] text-[#667085]">
                    Default model: <code className="text-[#8b949e]">{prov.default_model}</code>
                    {prov.default_base_url && (
                      <> | Base URL: <code className="text-[#8b949e]">{prov.default_base_url}</code></>
                    )}
                  </p>
                )}

                {/* Setup hint */}
                {prov.setup_hint && (
                  <div className="rounded-lg bg-[#0C111D] border border-[#21262d] p-3">
                    <p className="text-xs text-[#FBBF24]">{prov.setup_hint}</p>
                  </div>
                )}

                {/* Logout warning */}
                {prov.requires_logout && (
                  <div className="rounded-lg bg-[#FBBF24]/5 border border-[#FBBF24]/20 p-3">
                    <p className="text-xs text-[#FBBF24]">
                      After activating, run <code className="font-bold">/logout</code> inside Claude Code
                      if you were previously logged into Anthropic.
                    </p>
                  </div>
                )}

                {/* Test result */}
                {testResult && (
                  <div className={`rounded-lg p-3 text-xs ${
                    testResult.success
                      ? 'bg-[#00FFA7]/10 text-[#00FFA7] border border-[#00FFA7]/25'
                      : 'bg-red-500/10 text-red-400 border border-red-500/25'
                  }`}>
                    {testResult.success ? <CheckCircle2 size={12} className="inline mr-1" /> : <AlertCircle size={12} className="inline mr-1" />}
                    {testResult.message}
                  </div>
                )}
              </div>

              {/* Modal footer */}
              <div className="flex items-center justify-between px-6 py-4 border-t border-[#21262d]">
                <button
                  onClick={() => handleTest(prov.id)}
                  disabled={testing === prov.id}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-white/[0.04] text-[#8b949e] border border-[#21262d] hover:bg-white/[0.08] hover:text-white transition-all disabled:opacity-50"
                >
                  {testing === prov.id ? <RefreshCw size={12} className="animate-spin" /> : <TestTube2 size={12} />}
                  Test Connection
                </button>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => { setConfigOpen(null); setTestResult(null) }}
                    className="text-xs px-4 py-1.5 rounded-full bg-white/[0.04] text-[#8b949e] border border-[#21262d] hover:bg-white/[0.08] hover:text-white transition-all"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-full bg-[#00FFA7]/10 text-[#00FFA7] border border-[#00FFA7]/20 hover:bg-[#00FFA7]/20 transition-all disabled:opacity-50"
                  >
                    {saving ? <RefreshCw size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
                    Save & Activate
                  </button>
                </div>
              </div>
            </div>
          </div>
        )
      })()}
    </div>
  )
}
