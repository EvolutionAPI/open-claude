import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  ArrowLeft, Package, CheckCircle, XCircle, AlertTriangle,
  Loader2, RefreshCw, Trash2, ShieldCheck, Download,
} from 'lucide-react'
import { api } from '../lib/api'
import type { Plugin } from '../components/PluginCard'

interface HealthResult {
  slug: string
  status: 'active' | 'broken' | 'not_installed'
  tampered_files?: string[]
  reason?: string
}

interface AuditEntry {
  id: number
  action: string
  success: number
  created_at: string
  payload?: string
}

export default function PluginDetail() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const { t } = useTranslation()

  const [plugin, setPlugin] = useState<Plugin | null>(null)
  const [health, setHealth] = useState<HealthResult | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [healthLoading, setHealthLoading] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [updateMsg, setUpdateMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!slug) return
    setLoading(true)
    Promise.all([
      api.get('/plugins') as Promise<Plugin[]>,
      api.get(`/plugins/${slug}/audit`) as Promise<AuditEntry[]>,
    ])
      .then(([plugins, auditLog]) => {
        const found = plugins.find((p) => p.slug === slug)
        if (!found) { setError('Plugin not found'); return }
        setPlugin(found)
        setAudit(Array.isArray(auditLog) ? auditLog : [])
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : t('common.unexpectedError')))
      .finally(() => setLoading(false))
  }, [slug, t])

  async function checkHealth() {
    if (!slug) return
    setHealthLoading(true)
    try {
      const result = await api.get(`/plugins/${slug}/health`) as HealthResult
      setHealth(result)
    } catch {
      setHealth(null)
    } finally {
      setHealthLoading(false)
    }
  }

  async function handleUpdate() {
    if (!slug) return
    setUpdating(true)
    setUpdateMsg(null)
    try {
      const result = await api.post(`/plugins/${slug}/update`, {}) as {
        slug?: string; from?: string; to?: string; error?: string; message?: string
      }
      if (result.error) {
        setUpdateMsg(`${result.error}: ${result.message ?? ''}`)
      } else if (result.from && result.to) {
        setUpdateMsg(`Updated from v${result.from} to v${result.to}`)
        // refresh plugin data
        const plugins = await api.get('/plugins') as Plugin[]
        const found = plugins.find((p) => p.slug === slug)
        if (found) setPlugin(found)
      } else {
        setUpdateMsg('Update complete')
      }
    } catch (e: unknown) {
      setUpdateMsg(e instanceof Error ? e.message : 'update failed')
    } finally {
      setUpdating(false)
    }
  }

  async function handleUninstall() {
    if (!slug || !window.confirm(t('plugins.confirmUninstall'))) return
    setRemoving(true)
    try {
      await api.delete(`/plugins/${slug}`)
      navigate('/plugins')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t('common.unexpectedError'))
      setRemoving(false)
    }
  }

  async function handleToggle() {
    if (!plugin) return
    const next = plugin.enabled !== 1
    try {
      await api.patch(`/plugins/${plugin.slug}`, { enabled: next })
      setPlugin({ ...plugin, enabled: next ? 1 : 0 })
    } catch {
      // silent — refetch if needed
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={24} className="text-[#00FFA7] animate-spin" />
      </div>
    )
  }

  if (error || !plugin) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <p className="text-red-400 mb-2">{error ?? 'Plugin not found'}</p>
          <button onClick={() => navigate('/plugins')} className="text-sm text-[#667085] hover:text-[#D0D5DD]">
            {t('common.back')}
          </button>
        </div>
      </div>
    )
  }

  let manifest: Record<string, unknown> = {}
  try {
    manifest = JSON.parse(plugin.manifest_json ?? '{}')
  } catch {
    // ignore
  }

  const capabilities = Array.isArray(manifest['capabilities']) ? manifest['capabilities'] as string[] : []

  return (
    <div className="max-w-3xl mx-auto">
      {/* Back */}
      <button
        onClick={() => navigate('/plugins')}
        className="flex items-center gap-1.5 text-sm text-[#667085] hover:text-[#D0D5DD] mb-6 transition-colors"
      >
        <ArrowLeft size={14} />
        {t('plugins.title')}
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-4">
          <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-[#00FFA7]/8 border border-[#00FFA7]/15">
            <Package size={24} className="text-[#00FFA7]" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-[#e6edf3]">{plugin.name}</h1>
            <p className="text-sm text-[#667085]">
              {plugin.slug} &middot; v{plugin.version}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleToggle}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors border ${
              plugin.enabled === 1
                ? 'bg-[#00FFA7]/10 text-[#00FFA7] border-[#00FFA7]/20 hover:bg-[#00FFA7]/20'
                : 'bg-[#21262d] text-[#667085] border-[#344054] hover:text-[#D0D5DD]'
            }`}
          >
            {plugin.enabled === 1 ? t('common.enabled') : t('common.disabled')}
          </button>
          <button
            onClick={handleUpdate}
            disabled={updating || removing}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-[#00FFA7] border border-[#00FFA7]/20 rounded-lg hover:bg-[#00FFA7]/10 disabled:opacity-50 transition-colors"
          >
            {updating ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
            Atualizar
          </button>
          <button
            onClick={handleUninstall}
            disabled={removing || updating}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-400 border border-red-500/20 rounded-lg hover:bg-red-500/10 disabled:opacity-50 transition-colors"
          >
            {removing ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
            {t('common.uninstall')}
          </button>
        </div>
      </div>

      {updateMsg && (
        <div className="mb-4 text-xs text-[#D0D5DD] bg-[#161b22] border border-[#21262d] rounded-lg px-3 py-2">
          {updateMsg}
        </div>
      )}

      <div className="space-y-4">
        {/* Manifest details */}
        <section className="bg-[#161b22] border border-[#21262d] rounded-2xl p-5">
          <h2 className="text-sm font-semibold text-[#e6edf3] mb-4">{t('plugins.manifestDetails')}</h2>
          <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
            {[
              { label: t('common.version'), value: plugin.version },
              { label: t('plugins.author'), value: manifest['author'] as string },
              { label: t('plugins.license'), value: manifest['license'] as string },
              { label: t('plugins.tier'), value: plugin.tier },
              { label: t('common.status'), value: plugin.status },
              { label: t('common.createdAt'), value: new Date(plugin.installed_at).toLocaleString() },
            ].map(({ label, value }) =>
              value ? (
                <div key={label}>
                  <dt className="text-xs text-[#667085] mb-0.5">{label}</dt>
                  <dd className="text-[#e6edf3]">{value}</dd>
                </div>
              ) : null
            )}
          </dl>
          {manifest['description'] && (
            <div className="mt-4 pt-4 border-t border-[#21262d]">
              <dt className="text-xs text-[#667085] mb-1">{t('common.description')}</dt>
              <dd className="text-sm text-[#D0D5DD]">{manifest['description'] as string}</dd>
            </div>
          )}
          {capabilities.length > 0 && (
            <div className="mt-4 pt-4 border-t border-[#21262d]">
              <p className="text-xs text-[#667085] mb-2">{t('plugins.capabilities')}</p>
              <div className="flex flex-wrap gap-1.5">
                {capabilities.map((cap) => (
                  <span key={cap} className="text-xs bg-[#00FFA7]/10 text-[#00FFA7] border border-[#00FFA7]/20 px-2 py-0.5 rounded-full">
                    {cap}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Health */}
        <section className="bg-[#161b22] border border-[#21262d] rounded-2xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-[#e6edf3] flex items-center gap-2">
              <ShieldCheck size={14} className="text-[#00FFA7]" />
              {t('plugins.health')}
            </h2>
            <button
              onClick={checkHealth}
              disabled={healthLoading}
              className="flex items-center gap-1.5 text-xs text-[#667085] hover:text-[#D0D5DD] transition-colors"
            >
              {healthLoading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              {t('common.refresh')}
            </button>
          </div>
          {health ? (
            <div>
              <div className="flex items-center gap-2 mb-2">
                {health.status === 'active' ? (
                  <CheckCircle size={14} className="text-[#00FFA7]" />
                ) : (
                  <XCircle size={14} className="text-red-400" />
                )}
                <span className={`text-sm font-medium ${health.status === 'active' ? 'text-[#00FFA7]' : 'text-red-400'}`}>
                  {health.status}
                </span>
              </div>
              {health.reason && (
                <p className="text-xs text-[#667085]">{health.reason}</p>
              )}
              {health.tampered_files && health.tampered_files.length > 0 && (
                <div className="mt-2 bg-red-500/5 border border-red-500/20 rounded-lg p-3">
                  <p className="text-xs text-red-400 font-medium mb-1 flex items-center gap-1.5">
                    <AlertTriangle size={12} /> {t('plugins.tamperedFiles')}
                  </p>
                  <ul className="space-y-0.5">
                    {health.tampered_files.map((f) => (
                      <li key={f} className="text-xs text-red-300/80 font-mono">{f}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-[#667085]">{t('plugins.healthNotChecked')}</p>
          )}
        </section>

        {/* Audit log */}
        {audit.length > 0 && (
          <section className="bg-[#161b22] border border-[#21262d] rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-[#e6edf3] mb-4">{t('plugins.auditLog')}</h2>
            <div className="space-y-1.5">
              {audit.slice(0, 20).map((entry) => (
                <div key={entry.id} className="flex items-center gap-3 text-xs py-1">
                  <span className="text-[#667085] w-32 shrink-0">
                    {new Date(entry.created_at).toLocaleString()}
                  </span>
                  <span className={`font-medium ${entry.success ? 'text-[#00FFA7]' : 'text-red-400'}`}>
                    {entry.action}
                  </span>
                  {!entry.success && (
                    <span className="text-red-400/60">failed</span>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
