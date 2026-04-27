import { useEffect, useState } from 'react'
import { Activity, RefreshCw, ShieldCheck, Database, Plug, Clock3, AlertTriangle } from 'lucide-react'
import { api } from '../lib/api'
import { PageSkeleton } from '../components/PageStates'

type Summary = any

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: any
  label: string
  value: string
  detail?: string
}) {
  return (
    <div className="rounded-2xl border border-[color:var(--border)] bg-[var(--bg-card)] p-5 shadow-[0_18px_40px_rgba(0,0,0,0.15)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.16em] text-[#667085]">{label}</p>
          <div className="mt-2 text-2xl font-semibold text-[color:var(--text-primary)]">{value}</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/5 p-2 text-[#00FFA7]">
          <Icon size={18} />
        </div>
      </div>
      {detail && <p className="mt-3 text-sm text-[color:var(--text-secondary)]">{detail}</p>}
    </div>
  )
}

export default function Observability() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get('/observability/summary')
      setSummary(data)
    } catch {
      setError('Failed to load observability summary')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  if (loading && !summary) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">Observability</h1>
            <p className="text-sm text-[#5a6b7f]">Platform health, provider metrics, and runtime state.</p>
          </div>
        </div>
        <PageSkeleton rows={3} cards={3} />
      </div>
    )
  }

  const providerMetrics = summary?.provider_metrics?.providers || []
  const routing = summary?.provider_config?.routing?.failover_order || []

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Observability</h1>
          <p className="mt-1 text-sm text-[#5a6b7f]">Platform health, provider metrics, queue state, and cache usage.</p>
        </div>
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-2 rounded-xl border border-[#1e2a3a] bg-[#0b1018] px-4 py-2 text-sm font-medium text-[#e2e8f0] transition-colors hover:border-[#00FFA7]/40 hover:text-[#00FFA7]"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Database}
          label="Database"
          value={summary?.database_backend || 'unknown'}
          detail={summary?.backend?.checks?.database?.status || 'n/a'}
        />
        <MetricCard
          icon={ShieldCheck}
          label="Backend"
          value={summary?.backend?.status || 'unknown'}
          detail={summary?.backend?.checks?.secret_key?.status ? `Secret key: ${summary.backend.checks.secret_key.status}` : undefined}
        />
        <MetricCard
          icon={Activity}
          label="Terminal"
          value={summary?.terminal_server?.status || 'unknown'}
          detail={summary?.terminal_server?.reachable ? 'reachable' : summary?.terminal_server?.error || 'offline'}
        />
        <MetricCard
          icon={Plug}
          label="Plugins"
          value={`${summary?.plugins?.installed_count || 0} installed`}
          detail={`${summary?.plugins?.registry_count || 0} in registry`}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <div className="rounded-2xl border border-[color:var(--border)] bg-[var(--bg-card)] p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-[color:var(--text-primary)]">Provider metrics</h2>
              <p className="text-xs text-[color:var(--text-secondary)]">Success rate and latency by provider.</p>
            </div>
            <div className="rounded-lg border border-[#1e2a3a] bg-[#0b1018] px-3 py-1 text-[11px] text-[#5a6b7f]">
              {summary?.provider_metrics?.total_events || 0} events
            </div>
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-[11px] uppercase tracking-[0.12em] text-[#667085]">
                <tr>
                  <th className="py-2 pr-3">Provider</th>
                  <th className="py-2 pr-3">Events</th>
                  <th className="py-2 pr-3">Success</th>
                  <th className="py-2 pr-3">Latency</th>
                  <th className="py-2 pr-3">Last event</th>
                </tr>
              </thead>
              <tbody>
                {providerMetrics.map((row: any) => (
                  <tr key={row.provider_id} className="border-t border-white/5">
                    <td className="py-3 pr-3 font-medium text-white">{row.provider_id}</td>
                    <td className="py-3 pr-3 text-[#cbd5e1]">{row.events}</td>
                    <td className="py-3 pr-3 text-[#cbd5e1]">{row.success_rate ?? 'n/a'}%</td>
                    <td className="py-3 pr-3 text-[#cbd5e1]">{row.avg_latency_ms ?? 'n/a'} ms</td>
                    <td className="py-3 pr-3 text-[#94a3b8]">{row.last_event?.event || 'n/a'}</td>
                  </tr>
                ))}
                {providerMetrics.length === 0 && (
                  <tr>
                    <td className="py-4 text-sm text-[#5a6b7f]" colSpan={5}>
                      No provider metrics yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-[color:var(--border)] bg-[var(--bg-card)] p-5">
            <h2 className="text-sm font-semibold text-[color:var(--text-primary)]">Routing</h2>
            <p className="mt-1 text-xs text-[color:var(--text-secondary)]">Current failover order used by the terminal server.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {routing.map((item: string) => (
                <span key={item} className="rounded-full border border-[#1e2a3a] bg-[#0b1018] px-2.5 py-1 text-[11px] text-[#e2e8f0]">
                  {item}
                </span>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-[color:var(--border)] bg-[var(--bg-card)] p-5">
            <h2 className="text-sm font-semibold text-[color:var(--text-primary)]">System snapshot</h2>
            <div className="mt-3 space-y-2 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[color:var(--text-secondary)]">Cache</span>
                <span className="text-white">{summary?.cache?.backend || 'unknown'}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-[color:var(--text-secondary)]">Queue</span>
                <span className="text-white">{summary?.queue?.backend || 'unknown'}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-[color:var(--text-secondary)]">Generated at</span>
                <span className="text-white">{summary?.generated_at ? new Date(summary.generated_at).toLocaleString() : 'n/a'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-[color:var(--border)] bg-[var(--bg-card)] p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-[color:var(--text-primary)]">Recent events</h2>
            <p className="text-xs text-[color:var(--text-secondary)]">Queue and platform activity from the last snapshot.</p>
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-[#1e2a3a] bg-[#0b1018] px-3 py-1 text-[11px] text-[#5a6b7f]">
            <Clock3 size={12} />
            {summary?.recent_events?.length || 0}
          </div>
        </div>

        <div className="mt-4 space-y-2">
          {(summary?.recent_events || []).slice().reverse().map((event: any, index: number) => (
            <div key={`${event.ts}-${index}`} className="flex items-start gap-3 rounded-xl border border-white/5 bg-[#0b1018] px-4 py-3">
              <div className="mt-0.5 rounded-full bg-[#00FFA7]/15 p-1 text-[#00FFA7]">
                <AlertTriangle size={12} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-white">{event.topic || 'event'}</span>
                  <span className="text-[11px] text-[#5a6b7f]">{event.source || 'dashboard'}</span>
                </div>
                <p className="mt-1 truncate text-xs text-[#94a3b8]">
                  {JSON.stringify(event.payload || {}).slice(0, 220)}
                </p>
              </div>
              <span className="shrink-0 text-[11px] text-[#5a6b7f]">
                {event.ts ? new Date(event.ts).toLocaleTimeString() : ''}
              </span>
            </div>
          ))}
          {(summary?.recent_events || []).length === 0 && (
            <div className="rounded-xl border border-dashed border-[#1e2a3a] px-4 py-8 text-center text-sm text-[#5a6b7f]">
              No recent events recorded.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
