import { useState, type FormEvent, type ReactNode } from 'react'
import { AlertCircle, Database, Eye, EyeOff, Loader2, Lock, Pencil, Plus, Trash2, Unlock, X } from 'lucide-react'
import { api } from '../../lib/api'
import {
  DB_FLAVOR_META,
  EMPTY_DB_FORM,
  SSL_MODES_POSTGRES,
  inputClass,
  type DatabaseConnection,
  type DatabaseFlavor,
  type DbFormState,
  type FlavorMeta,
} from './types'

interface DatabasesTabProps {
  flavors: DatabaseFlavor[]
  onReload: () => void
}

interface DeleteTarget {
  flavor: 'postgres' | 'mysql' | 'mongo' | 'redis'
  index: number
  label: string
}

export function DatabasesTab({ flavors, onReload }: DatabasesTabProps) {
  const postgres = flavors.find((f) => f.slug === 'postgres') ?? { slug: 'postgres', skill: 'db-postgres', ok: true, count: 0, connections: [] }
  const mysql = flavors.find((f) => f.slug === 'mysql') ?? { slug: 'mysql', skill: 'db-mysql', ok: true, count: 0, connections: [] }
  const mongo = flavors.find((f) => f.slug === 'mongo') ?? { slug: 'mongo', skill: 'db-mongo', ok: true, count: 0, connections: [] }
  const redis = flavors.find((f) => f.slug === 'redis') ?? { slug: 'redis', skill: 'db-redis', ok: true, count: 0, connections: [] }

  const [modalFlavor, setModalFlavor] = useState<'postgres' | 'mysql' | 'mongo' | 'redis' | null>(null)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [formInitial, setFormInitial] = useState<Partial<DbFormState>>({})
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null)
  const [deleting, setDeleting] = useState(false)

  const openCreate = (flavor: 'postgres' | 'mysql' | 'mongo' | 'redis') => {
    setEditingIndex(null)
    setFormInitial({})
    setModalFlavor(flavor)
  }

  const openEdit = (flavor: 'postgres' | 'mysql' | 'mongo' | 'redis', conn: DatabaseConnection) => {
    setEditingIndex(conn.index)
    const usesConnString = conn.host === '<dsn>' || conn.host === '<uri>' || conn.host === '<url>'
    setFormInitial({
      label: conn.label,
      host: usesConnString ? '' : (conn.host ?? ''),
      port: conn.port ? String(conn.port) : '',
      database: flavor === 'redis' ? '' : (conn.database ?? ''),
      db: flavor === 'redis' ? (conn.database ?? '') : '',
      ssl_mode: conn.ssl_mode ?? '',
      allow_write: conn.allow_write,
      query_timeout: String(conn.query_timeout),
      max_rows: String(conn.max_rows),
    })
    setModalFlavor(flavor)
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await api.delete(`/integrations/databases/${deleteTarget.flavor}/${deleteTarget.index}`)
      setDeleteTarget(null)
      onReload()
    } catch (e) {
      console.error(e)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="space-y-8">
      {deleteTarget && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-[2px]" onClick={() => setDeleteTarget(null)} />
          <div className="relative w-full max-w-sm bg-[#0C111D] border border-[#21262d] rounded-2xl shadow-2xl p-6">
            <h3 className="text-base font-semibold text-[#e6edf3] mb-2">Remove database connection</h3>
            <p className="text-sm text-[#667085] mb-5">
              Remove <span className="text-[#e6edf3] font-medium">{deleteTarget.label}</span>? The env variables will be deleted from{' '}
              <code className="text-[#00FFA7] font-mono text-xs">.env</code>.
            </p>
            <div className="flex items-center justify-end gap-3">
              <button onClick={() => setDeleteTarget(null)} className="px-4 py-2 rounded-lg text-sm text-[#667085] hover:text-[#e6edf3] hover:bg-[#21262d] transition-colors">Cancel</button>
              <button onClick={handleDelete} disabled={deleting} className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-red-500/80 text-white text-sm font-semibold hover:bg-red-500 transition-colors disabled:opacity-60">
                {deleting && <Loader2 size={14} className="animate-spin" />} Remove
              </button>
            </div>
          </div>
        </div>
      )}

      {modalFlavor && (
        <DatabaseFormModal
          flavor={modalFlavor}
          editingIndex={editingIndex}
          initial={formInitial}
          onClose={() => setModalFlavor(null)}
          onSaved={() => {
            setModalFlavor(null)
            onReload()
          }}
        />
      )}

      <FlavorSection flavor={postgres} onAdd={() => openCreate('postgres')} onEdit={(c) => openEdit('postgres', c)} onDelete={(c) => setDeleteTarget({ flavor: 'postgres', index: c.index, label: c.label })} />
      <FlavorSection flavor={mysql} onAdd={() => openCreate('mysql')} onEdit={(c) => openEdit('mysql', c)} onDelete={(c) => setDeleteTarget({ flavor: 'mysql', index: c.index, label: c.label })} />
      <FlavorSection flavor={mongo} onAdd={() => openCreate('mongo')} onEdit={(c) => openEdit('mongo', c)} onDelete={(c) => setDeleteTarget({ flavor: 'mongo', index: c.index, label: c.label })} />
      <FlavorSection flavor={redis} onAdd={() => openCreate('redis')} onEdit={(c) => openEdit('redis', c)} onDelete={(c) => setDeleteTarget({ flavor: 'redis', index: c.index, label: c.label })} />
    </div>
  )
}

function FlavorSection({
  flavor,
  onAdd,
  onEdit,
  onDelete,
}: {
  flavor: DatabaseFlavor
  onAdd: () => void
  onEdit: (c: DatabaseConnection) => void
  onDelete: (c: DatabaseConnection) => void
}) {
  const meta = DB_FLAVOR_META[flavor.slug] ?? { color: '#667085', colorMuted: 'rgba(102,112,133,0.10)', label: flavor.slug, defaultPort: 0 }

  return (
    <section>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg" style={{ backgroundColor: meta.colorMuted, border: `1px solid ${meta.color}33` }}>
            <Database size={14} style={{ color: meta.color }} />
          </div>
          <h2 className="text-base font-semibold text-[#e6edf3]">{meta.label}</h2>
          {flavor.count > 0 && (
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ backgroundColor: meta.colorMuted, color: meta.color, border: `1px solid ${meta.color}40` }}>
              {flavor.count}
            </span>
          )}
          {!flavor.ok && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/25 flex items-center gap-1">
              <AlertCircle size={10} /> {flavor.error || 'parser error'}
            </span>
          )}
        </div>
        <button onClick={onAdd} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-[#00FFA7]/10 text-[#00FFA7] border border-[#00FFA7]/20 hover:bg-[#00FFA7]/20 transition-all">
          <Plus size={13} /> Add {meta.label}
        </button>
      </div>

      {flavor.connections.length === 0 ? (
        <div
          onClick={onAdd}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              onAdd()
            }
          }}
          className="cursor-pointer rounded-xl border border-dashed border-[#21262d] hover:border-[#00FFA7]/30 bg-[#161b22]/50 p-8 flex flex-col items-center justify-center gap-2 transition-colors group"
        >
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-[#00FFA7]/8 border border-[#00FFA7]/15 group-hover:bg-[#00FFA7]/15 transition-colors">
            <Plus size={20} className="text-[#00FFA7]" />
          </div>
          <p className="text-sm font-medium text-[#667085] group-hover:text-[#e6edf3] transition-colors">Add {meta.label} connection</p>
          <p className="text-xs text-[#3F3F46]">Host, port, user, password - stored in .env automatically</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {flavor.connections.map((conn) => (
            <ConnectionCard key={conn.index} conn={conn} flavor={flavor.slug} meta={meta} onEdit={() => onEdit(conn)} onDelete={() => onDelete(conn)} />
          ))}
        </div>
      )}
    </section>
  )
}

function ConnectionCard({
  conn,
  flavor,
  meta,
  onEdit,
  onDelete,
}: {
  conn: DatabaseConnection
  flavor: string
  meta: FlavorMeta
  onEdit: () => void
  onDelete: () => void
}) {
  const envPrefix = `DB_${flavor.toUpperCase()}_${conn.index}`
  const hostDisplay =
    conn.host === '<dsn>' ? 'via DSN' :
    conn.host === '<uri>' ? 'via URI' :
    conn.host === '<url>' ? 'via URL' :
    (conn.host ?? '—')
  const dbLabel = flavor === 'redis' ? 'DB index' : 'Database'
  const sslLabel = flavor === 'redis' || flavor === 'mongo' ? 'TLS' : 'SSL'
  const sslValue =
    flavor === 'redis' || flavor === 'mongo'
      ? (conn as DatabaseConnection & { tls?: boolean }).tls ? 'on' : 'off'
      : (conn.ssl_mode ?? '—')

  return (
    <div className="group relative rounded-xl border border-[#21262d] bg-[#161b22] p-4 transition-all hover:border-transparent">
      <div className="pointer-events-none absolute inset-0 rounded-xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ boxShadow: `inset 0 0 0 1px ${meta.color}44, 0 0 16px ${meta.color}22`, borderRadius: 'inherit' }} />

      <div className="relative flex items-start justify-between mb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-sm font-semibold text-[#e6edf3] truncate">{conn.label}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full font-mono text-[#667085] bg-white/[0.04] border border-[#21262d] shrink-0">#{conn.index}</span>
          </div>
          <p className="text-[11px] text-[#667085] font-mono truncate">{envPrefix}_*</p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {conn.allow_write ? (
            <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/25" title="ALLOW_WRITE=true">
              <Unlock size={10} /> read/write
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-[#00FFA7]/10 text-[#00FFA7] border border-[#00FFA7]/25">
              <Lock size={10} /> read-only
            </span>
          )}
        </div>
      </div>

      <div className="relative grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs mb-3">
        <div><p className="text-[10px] uppercase tracking-wider text-[#3F3F46] mb-0.5">Host</p><p className="text-[#e6edf3] font-mono truncate" title={hostDisplay}>{hostDisplay}</p></div>
        <div><p className="text-[10px] uppercase tracking-wider text-[#3F3F46] mb-0.5">Port</p><p className="text-[#e6edf3] font-mono">{conn.port ?? '—'}</p></div>
        <div><p className="text-[10px] uppercase tracking-wider text-[#3F3F46] mb-0.5">{dbLabel}</p><p className="text-[#e6edf3] font-mono truncate" title={conn.database ?? '—'}>{conn.database ?? '—'}</p></div>
        <div><p className="text-[10px] uppercase tracking-wider text-[#3F3F46] mb-0.5">{sslLabel}</p><p className="text-[#e6edf3] font-mono">{sslValue}</p></div>
      </div>

      <div className="relative flex items-center justify-between gap-2 pt-3 border-t border-[#21262d]">
        <div className="flex items-center gap-3 text-[10px] text-[#667085]">
          <span>timeout <span className="text-[#e6edf3] font-mono">{conn.query_timeout}s</span></span>
          <span>max rows <span className="text-[#e6edf3] font-mono">{conn.max_rows}</span></span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={onEdit} className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] text-[#667085] hover:text-[#e6edf3] hover:bg-[#21262d] transition-colors" title="Edit">
            <Pencil size={11} /> Edit
          </button>
          <button onClick={onDelete} className="p-1.5 rounded-lg hover:bg-red-500/10 text-[#667085] hover:text-red-400 transition-colors" title="Remove">
            <Trash2 size={12} />
          </button>
        </div>
      </div>
    </div>
  )
}

const SSL_PLACEHOLDER = SSL_MODES_POSTGRES

function DatabaseFormModal({
  flavor,
  editingIndex,
  initial,
  onClose,
  onSaved,
}: {
  flavor: 'postgres' | 'mysql' | 'mongo' | 'redis'
  editingIndex: number | null
  initial: Partial<DbFormState>
  onClose: () => void
  onSaved: () => void
}) {
  const meta = DB_FLAVOR_META[flavor]
  const isEdit = editingIndex !== null

  const [form, setForm] = useState<DbFormState>({
    ...EMPTY_DB_FORM,
    port: String(meta.defaultPort),
    query_timeout: '30',
    max_rows: '1000',
    ssl_mode: flavor === 'postgres' ? 'require' : '',
    ...initial,
  } as DbFormState)
  const [showPassword, setShowPassword] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const update = <K extends keyof DbFormState>(key: K, value: DbFormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!form.label.trim()) {
      setError('Label is required')
      return
    }

    const connectionStringField =
      flavor === 'mongo' ? form.uri.trim() :
      flavor === 'redis' ? form.url.trim() :
      form.dsn.trim()
    if (!connectionStringField && !form.host.trim()) {
      setError(flavor === 'mongo' ? 'Host or URI is required' :
               flavor === 'redis' ? 'Host or URL is required' :
               'Host is required (or use a full DSN)')
      return
    }

    const body: Record<string, unknown> = {
      label: form.label.trim(),
      host: form.host.trim() || undefined,
      port: form.port.trim() || undefined,
      allow_write: form.allow_write ? 'true' : undefined,
      query_timeout: form.query_timeout.trim() || undefined,
      max_rows: form.max_rows.trim() || undefined,
    }

    if (flavor === 'postgres' || flavor === 'mysql') {
      body.database = form.database.trim() || undefined
      body.user = form.user.trim() || undefined
      body.ssl_ca_path = form.ssl_ca_path.trim() || undefined
      body.dsn = form.dsn.trim() || undefined
      if (flavor === 'postgres') body.ssl_mode = form.ssl_mode || undefined
    } else if (flavor === 'mongo') {
      body.database = form.database.trim() || undefined
      body.user = form.user.trim() || undefined
      body.auth_source = form.auth_source.trim() || undefined
      body.tls = form.tls ? 'true' : undefined
      body.uri = form.uri.trim() || undefined
    } else if (flavor === 'redis') {
      body.db = form.db.trim() || undefined
      body.username = form.username.trim() || undefined
      body.tls = form.tls ? 'true' : undefined
      body.url = form.url.trim() || undefined
    }

    if (isEdit) {
      body.password = form.password === '' ? '__KEEP__' : form.password
    } else {
      body.password = form.password
    }

    setSaving(true)
    try {
      if (isEdit) {
        await api.put(`/integrations/databases/${flavor}/${editingIndex}`, body)
      } else {
        await api.post(`/integrations/databases/${flavor}`, body)
      }
      onSaved()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to save'
      setError(msg)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-[2px]" onClick={onClose} />
      <div className="relative w-full max-w-lg max-h-[90vh] overflow-y-auto bg-[#0C111D] border border-[#21262d] rounded-2xl shadow-2xl">
        <form onSubmit={submit}>
          <div className="flex items-center justify-between p-5 border-b border-[#21262d]">
            <div className="flex items-center gap-3">
              <div className="flex items-center justify-center w-9 h-9 rounded-lg" style={{ backgroundColor: meta.colorMuted, border: `1px solid ${meta.color}33` }}>
                <Database size={16} style={{ color: meta.color }} />
              </div>
              <div>
                <h3 className="text-base font-semibold text-[#e6edf3]">{isEdit ? 'Edit' : 'Add'} {meta.label} connection</h3>
                <p className="text-xs text-[#667085] mt-0.5">Saved to <code className="text-[#00FFA7] font-mono">.env</code> as <code className="text-[#00FFA7] font-mono">DB_{flavor.toUpperCase()}_N_*</code></p>
              </div>
            </div>
            <button type="button" onClick={onClose} className="p-1.5 rounded-lg text-[#667085] hover:text-[#e6edf3] hover:bg-[#21262d]"><X size={16} /></button>
          </div>

          <div className="p-5 space-y-4">
            {error && (
              <div className="flex items-start gap-2 rounded-lg bg-red-500/10 border border-red-500/25 px-3 py-2 text-xs text-red-300">
                <AlertCircle size={14} className="shrink-0 mt-0.5" /><span>{error}</span>
              </div>
            )}

            <Field label="Label" required hint="How agents refer to this DB (e.g. msgops-dev)">
              <input type="text" value={form.label} onChange={(e) => update('label', e.target.value)} placeholder="msgops-dev" autoFocus className={inputClass} />
            </Field>

            <div className="grid grid-cols-[1fr,90px] gap-3">
              <Field label="Host">
                <input type="text" value={form.host} onChange={(e) => update('host', e.target.value)} placeholder="db.example.com" className={inputClass} />
              </Field>
              <Field label="Port">
                <input type="number" value={form.port} onChange={(e) => update('port', e.target.value)} placeholder={String(meta.defaultPort)} className={inputClass} />
              </Field>
            </div>

            {flavor === 'redis' ? (
              <Field label="DB index" hint="Redis numeric database (default 0)">
                <input type="number" min={0} value={form.db} onChange={(e) => update('db', e.target.value)} placeholder="0" className={inputClass} />
              </Field>
            ) : (
              <Field label="Database" hint={flavor === 'mongo' ? 'Optional if included in URI' : undefined}>
                <input type="text" value={form.database} onChange={(e) => update('database', e.target.value)} placeholder="my_database" className={inputClass} />
              </Field>
            )}

            <div className="grid grid-cols-2 gap-3">
              <Field label={flavor === 'redis' ? 'Username (ACL)' : 'User'} hint={flavor === 'redis' ? 'Optional (Redis 6+ ACL)' : undefined}>
                <input
                  type="text"
                  value={flavor === 'redis' ? form.username : form.user}
                  onChange={(e) => update(flavor === 'redis' ? 'username' : 'user', e.target.value)}
                  placeholder={flavor === 'redis' ? 'default' : 'agent_readonly'}
                  className={inputClass}
                  autoComplete="off"
                />
              </Field>
              <Field label="Password" hint={isEdit ? 'Leave blank to keep current' : undefined}>
                <div className="relative">
                  <input type={showPassword ? 'text' : 'password'} value={form.password} onChange={(e) => update('password', e.target.value)} placeholder={isEdit ? '••••••• (unchanged)' : 'password'} className={inputClass + ' pr-9'} autoComplete="new-password" />
                  <button type="button" onClick={() => setShowPassword((v) => !v)} className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-[#667085] hover:text-[#e6edf3]">
                    {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </Field>
            </div>

            {flavor === 'postgres' && (
              <Field label="SSL mode" hint="Postgres connection encryption">
                <select value={form.ssl_mode} onChange={(e) => update('ssl_mode', e.target.value)} className={inputClass}>
                  {SSL_PLACEHOLDER.map((m) => <option key={m} value={m}>{m || '— none —'}</option>)}
                </select>
              </Field>
            )}

            {(flavor === 'postgres' || flavor === 'mysql') && (
              <Field label="SSL CA path" hint={flavor === 'postgres' ? 'Optional, for verify-ca / verify-full' : 'Optional, enables TLS verification'}>
                <input type="text" value={form.ssl_ca_path} onChange={(e) => update('ssl_ca_path', e.target.value)} placeholder="/path/to/ca.pem" className={inputClass} />
              </Field>
            )}

            {flavor === 'mongo' && (
              <div className="grid grid-cols-[1fr,auto] gap-3 items-end">
                <Field label="Auth source" hint="Optional (e.g. admin)">
                  <input type="text" value={form.auth_source} onChange={(e) => update('auth_source', e.target.value)} placeholder="admin" className={inputClass} />
                </Field>
                <label className="flex items-center gap-2 cursor-pointer select-none pb-2">
                  <input type="checkbox" checked={form.tls} onChange={(e) => update('tls', e.target.checked)} className="peer sr-only" />
                  <span className={`w-9 h-5 rounded-full border transition-all flex items-center ${form.tls ? 'bg-[#00FFA7]/30 border-[#00FFA7]/50' : 'bg-[#161b22] border-[#21262d]'}`}>
                    <span className={`block w-4 h-4 rounded-full transition-all ${form.tls ? 'ml-4 bg-[#00FFA7]' : 'ml-0.5 bg-[#667085]'}`} />
                  </span>
                  <span className="text-xs text-[#e6edf3] font-medium">TLS</span>
                </label>
              </div>
            )}

            {flavor === 'redis' && (
              <label className="flex items-center gap-2.5 cursor-pointer select-none">
                <input type="checkbox" checked={form.tls} onChange={(e) => update('tls', e.target.checked)} className="peer sr-only" />
                <span className={`w-9 h-5 rounded-full border transition-all flex items-center ${form.tls ? 'bg-[#00FFA7]/30 border-[#00FFA7]/50' : 'bg-[#161b22] border-[#21262d]'}`}>
                  <span className={`block w-4 h-4 rounded-full transition-all ${form.tls ? 'ml-4 bg-[#00FFA7]' : 'ml-0.5 bg-[#667085]'}`} />
                </span>
                <div>
                  <span className="text-xs text-[#e6edf3] font-medium">TLS (rediss://)</span>
                  <p className="text-[10px] text-[#667085] mt-0.5">Enable for managed Redis (Upstash, AWS, etc).</p>
                </div>
              </label>
            )}

            <details className="group rounded-lg border border-[#21262d] bg-[#161b22]/50">
              <summary className="cursor-pointer px-3 py-2 text-xs text-[#667085] hover:text-[#e6edf3] flex items-center gap-1.5 select-none">
                <span className="group-open:rotate-90 transition-transform">▸</span> Advanced
              </summary>
              <div className="px-3 pb-3 pt-1 space-y-3">
                {(flavor === 'postgres' || flavor === 'mysql') && (
                  <Field label="Full DSN (overrides host/port/user/password)" hint="Use only if the components above don't cover your setup">
                    <input type="text" value={form.dsn} onChange={(e) => update('dsn', e.target.value)} placeholder={flavor === 'postgres' ? 'postgresql://user:pw@host:5432/db' : 'mysql://user:pw@host:3306/db'} className={inputClass + ' font-mono text-xs'} />
                  </Field>
                )}
                {flavor === 'mongo' && (
                  <Field label="Full URI (overrides host/port/user/password)" hint="Use for Atlas or complex connection strings">
                    <input type="text" value={form.uri} onChange={(e) => update('uri', e.target.value)} placeholder="mongodb+srv://user:pw@cluster.abc.mongodb.net/db" className={inputClass + ' font-mono text-xs'} />
                  </Field>
                )}
                {flavor === 'redis' && (
                  <Field label="Full URL (overrides host/port/username/password)" hint="Use for managed Redis (Upstash, AWS, etc)">
                    <input type="text" value={form.url} onChange={(e) => update('url', e.target.value)} placeholder="rediss://user:pw@host:6380/0" className={inputClass + ' font-mono text-xs'} />
                  </Field>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <Field label="Query timeout (s)">
                    <input type="number" min={1} value={form.query_timeout} onChange={(e) => update('query_timeout', e.target.value)} className={inputClass} />
                  </Field>
                  <Field label="Max rows returned">
                    <input type="number" min={1} value={form.max_rows} onChange={(e) => update('max_rows', e.target.value)} className={inputClass} />
                  </Field>
                </div>

                <label className="flex items-center gap-2.5 cursor-pointer select-none">
                  <input type="checkbox" checked={form.allow_write} onChange={(e) => update('allow_write', e.target.checked)} className="peer sr-only" />
                  <span className={`w-9 h-5 rounded-full border transition-all flex items-center ${form.allow_write ? 'bg-amber-500/30 border-amber-500/50' : 'bg-[#161b22] border-[#21262d]'}`}>
                    <span className={`block w-4 h-4 rounded-full transition-all ${form.allow_write ? 'ml-4 bg-amber-400' : 'ml-0.5 bg-[#667085]'}`} />
                  </span>
                  <div>
                    <span className="text-xs text-[#e6edf3] font-medium">Allow write queries</span>
                    <p className="text-[10px] text-[#667085] mt-0.5">Default off. When on, DELETE/UPDATE/INSERT are permitted on this DB.</p>
                  </div>
                </label>
              </div>
            </details>
          </div>

          <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-[#21262d] bg-[#0a0f18]">
            <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-[#667085] hover:text-[#e6edf3] hover:bg-[#21262d] transition-colors">Cancel</button>
            <button type="submit" disabled={saving} className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#00FFA7] text-[#0C111D] text-sm font-semibold hover:bg-[#00FFA7]/90 transition-colors disabled:opacity-60">
              {saving && <Loader2 size={14} className="animate-spin" />} {isEdit ? 'Save changes' : 'Add connection'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string
  hint?: string
  required?: boolean
  children: ReactNode
  }) {
  return (
    <div>
      <label className="flex items-center gap-1.5 text-xs font-medium text-[#e6edf3] mb-1.5">
        {label}{required && <span className="text-[#00FFA7]">*</span>}
      </label>
      {children}
      {hint && <p className="text-[10px] text-[#667085] mt-1">{hint}</p>}
    </div>
  )
}
