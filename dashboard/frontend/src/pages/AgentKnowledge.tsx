import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Database,
  FileText,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'

const API_BASE = import.meta.env.DEV ? 'http://localhost:8080' : ''

interface KnowledgeConnection {
  id: string
  slug: string
  name: string
  status: string
}

interface Division {
  slug: string
  label: string
  agent: string | null
  description: string
  color: string
  ready: boolean
  documents_count: number
  chunks_count: number
  space?: { id: string; slug: string; name: string } | null
}

interface DivisionResponse {
  connections: KnowledgeConnection[]
  active_connection_id: string | null
  divisions: Division[]
  ready: boolean
  message?: string
}

interface KnowledgeDocument {
  id: string
  title: string
  status: string
  created_at?: string
  chunks_count?: number
  pages_count?: number
  division: string
  division_label: string
}

interface UploadItem {
  id: string
  filename: string
  documentId?: string
  division: string
  phase: string
  error?: string
}

interface SearchHit {
  chunk_id: string
  document_id: string
  doc_title?: string
  content_type?: string
  content: string
  final_score?: number
  division: string
  division_label: string
  chunk_metadata?: Record<string, unknown>
}

function formatDate(value?: string) {
  if (!value) return '-'
  try {
    return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
  } catch {
    return value
  }
}

function phaseLabel(phase: string) {
  const normalized = phase || 'pending'
  const labels: Record<string, string> = {
    queued: 'Na fila',
    pending: 'Pendente',
    scanning: 'Analisando',
    parsing: 'Lendo arquivo',
    chunking: 'Quebrando em trechos',
    embedding: 'Gerando vetores',
    storing: 'Gravando',
    classifying: 'Classificando',
    processing: 'Processando',
    ready: 'Pronto',
    done: 'Pronto',
    error: 'Erro',
  }
  return labels[normalized] || normalized
}

function statusColor(status: string) {
  if (['ready', 'done'].includes(status)) return '#00FFA7'
  if (status === 'error') return '#F87171'
  return '#FBBF24'
}

export default function AgentKnowledge() {
  const navigate = useNavigate()
  const { hasPermission } = useAuth()
  const canManage = hasPermission('knowledge', 'manage')

  const [loading, setLoading] = useState(true)
  const [bootstrapping, setBootstrapping] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [connections, setConnections] = useState<KnowledgeConnection[]>([])
  const [activeConnectionId, setActiveConnectionId] = useState<string | null>(null)
  const [divisions, setDivisions] = useState<Division[]>([])
  const [selectedDivision, setSelectedDivision] = useState('geral')
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [documentsLoading, setDocumentsLoading] = useState(false)

  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploads, setUploads] = useState<UploadItem[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pollers = useRef<Record<string, ReturnType<typeof setInterval>>>({})

  const [query, setQuery] = useState('')
  const [searchScope, setSearchScope] = useState('all')
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<SearchHit[] | null>(null)

  const selected = useMemo(
    () => divisions.find((d) => d.slug === selectedDivision) || divisions[0],
    [divisions, selectedDivision]
  )

  const allReady = divisions.length > 0 && divisions.every((d) => d.ready)

  const loadDivisions = useCallback(async (connectionId?: string | null) => {
    setError(null)
    const suffix = connectionId ? `?connection_id=${encodeURIComponent(connectionId)}` : ''
    const data: DivisionResponse = await api.get(`/agent-knowledge/divisions${suffix}`)
    setConnections(data.connections || [])
    setActiveConnectionId(data.active_connection_id)
    setDivisions(data.divisions || [])
    if (!selectedDivision && data.divisions?.[0]) setSelectedDivision(data.divisions[0].slug)
    return data
  }, [selectedDivision])

  const loadDocuments = useCallback(async () => {
    if (!activeConnectionId || !selectedDivision) return
    setDocumentsLoading(true)
    try {
      const params = new URLSearchParams({
        connection_id: activeConnectionId,
        division: selectedDivision,
        limit: '25',
      })
      const data = await api.get(`/agent-knowledge/documents?${params}`)
      setDocuments(data.documents || [])
    } catch {
      setDocuments([])
    } finally {
      setDocumentsLoading(false)
    }
  }, [activeConnectionId, selectedDivision])

  useEffect(() => {
    loadDivisions()
      .catch((e) => setError(e instanceof Error ? e.message : 'Falha ao carregar a base RAG.'))
      .finally(() => setLoading(false))
  }, [loadDivisions])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  useEffect(() => {
    return () => {
      Object.values(pollers.current).forEach(clearInterval)
    }
  }, [])

  async function handleBootstrap() {
    if (!activeConnectionId) return
    setBootstrapping(true)
    setError(null)
    try {
      const data = await api.post('/agent-knowledge/bootstrap', { connection_id: activeConnectionId })
      setDivisions(data.divisions || [])
      await loadDocuments()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao preparar as divisões RAG.')
    } finally {
      setBootstrapping(false)
    }
  }

  function addFiles(nextFiles: File[]) {
    if (nextFiles.length === 0) return
    setFiles((prev) => [...prev, ...nextFiles])
  }

  function updateUpload(id: string, patch: Partial<UploadItem>) {
    setUploads((prev) => prev.map((item) => item.id === id ? { ...item, ...patch } : item))
  }

  function pollStatus(localId: string, documentId: string) {
    const interval = setInterval(async () => {
      try {
        const data = await api.get(`/agent-knowledge/documents/${documentId}/status`)
        const phase = data.phase || data.status || 'processing'
        updateUpload(localId, { phase, error: data.error || data.error_message })
        if (['done', 'ready', 'error'].includes(phase)) {
          clearInterval(interval)
          delete pollers.current[localId]
          await loadDivisions(activeConnectionId)
          await loadDocuments()
        }
      } catch {
        updateUpload(localId, { phase: 'error', error: 'Falha ao consultar status.' })
        clearInterval(interval)
        delete pollers.current[localId]
      }
    }, 2000)
    pollers.current[localId] = interval
  }

  async function handleUpload() {
    if (!activeConnectionId || !selected || files.length === 0) return
    setUploading(true)
    setError(null)
    try {
      const body = new FormData()
      body.append('connection_id', activeConnectionId)
      body.append('division', selected.slug)
      files.forEach((file) => body.append('files', file))

      const res = await fetch(`${API_BASE}/api/agent-knowledge/upload`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body,
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.message || data.error || `Upload falhou: ${res.status}`)
      }
      const data = await res.json()
      const items: UploadItem[] = (data.uploads || []).map((upload: any) => ({
        id: `${upload.document_id}-${Math.random()}`,
        filename: upload.filename,
        documentId: upload.document_id,
        division: upload.division,
        phase: upload.status?.phase || upload.document?.status || 'pending',
      }))
      setUploads((prev) => [...items, ...prev])
      setFiles([])
      items.forEach((item) => {
        if (item.documentId) pollStatus(item.id, item.documentId)
      })
      await loadDivisions(activeConnectionId)
      await loadDocuments()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao enviar arquivos.')
    } finally {
      setUploading(false)
    }
  }

  async function handleSearch() {
    if (!activeConnectionId || !query.trim()) return
    setSearching(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        connection_id: activeConnectionId,
        division: searchScope,
        q: query.trim(),
        top_k: '12',
      })
      const data = await api.get(`/agent-knowledge/search?${params}`)
      setSearchResults(data.results || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao buscar na base RAG.')
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  async function handleDelete(documentId: string) {
    if (!activeConnectionId) return
    try {
      await api.delete(`/agent-knowledge/documents/${documentId}?connection_id=${encodeURIComponent(activeConnectionId)}`)
      await loadDivisions(activeConnectionId)
      await loadDocuments()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao excluir documento.')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-[#667085] text-sm">
        <Loader2 size={16} className="animate-spin mr-2" /> Carregando base RAG...
      </div>
    )
  }

  if (!activeConnectionId) {
    return (
      <div className="max-w-3xl mx-auto py-16">
        <div className="border border-[#344054] bg-[#182230] rounded-xl p-8 text-center">
          <Database size={34} className="text-[#667085] mx-auto mb-4" />
          <h1 className="text-xl font-semibold text-[#F9FAFB]">Base RAG dos Agentes</h1>
          <p className="text-sm text-[#8b949e] mt-2">
            Nenhuma conexão pgvector pronta foi encontrada.
          </p>
          <button
            onClick={() => navigate('/knowledge')}
            className="mt-5 px-4 py-2 rounded-lg bg-[#00FFA7] text-[#0C111D] text-sm font-medium"
          >
            Configurar pgvector
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-[1500px] mx-auto space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg border border-[#00FFA7]/20 bg-[#00FFA7]/10 flex items-center justify-center">
              <Database size={18} className="text-[#00FFA7]" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-[#F9FAFB]">Base RAG dos Agentes</h1>
              <p className="text-sm text-[#667085] mt-1">Conhecimento pgvector dividido por agente contábil</p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {connections.length > 1 && (
            <select
              value={activeConnectionId}
              onChange={async (e) => {
                setActiveConnectionId(e.target.value)
                await loadDivisions(e.target.value)
              }}
              className="bg-[#182230] border border-[#344054] rounded-lg px-3 py-2 text-sm text-[#D0D5DD] focus:border-[#00FFA7] focus:outline-none"
            >
              {connections.map((conn) => (
                <option key={conn.id} value={conn.id}>{conn.name || conn.slug}</option>
              ))}
            </select>
          )}
          <button
            onClick={async () => {
              await loadDivisions(activeConnectionId)
              await loadDocuments()
            }}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-[#344054] text-sm text-[#D0D5DD] hover:bg-white/[0.03]"
          >
            <RefreshCw size={14} /> Atualizar
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {!allReady && (
        <div className="flex flex-col gap-3 rounded-xl border border-[#F59E0B]/25 bg-[#F59E0B]/8 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium text-[#F9FAFB]">Divisões RAG pendentes</p>
            <p className="text-xs text-[#98A2B3] mt-1">Crie os Spaces pgvector: Geral e os seis agentes customizados.</p>
          </div>
          {canManage && (
            <button
              onClick={handleBootstrap}
              disabled={bootstrapping}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-[#00FFA7] text-[#0C111D] text-sm font-medium disabled:opacity-60"
            >
              {bootstrapping ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
              Preparar base
            </button>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[360px_minmax(0,1fr)] gap-6">
        <div className="space-y-2">
          {divisions.map((division) => (
            <button
              key={division.slug}
              onClick={() => {
                setSelectedDivision(division.slug)
                setSearchScope(division.slug)
              }}
              className={`w-full text-left rounded-xl border px-4 py-3 transition-colors ${
                selectedDivision === division.slug
                  ? 'border-[#00FFA7]/50 bg-[#00FFA7]/8'
                  : 'border-[#243044] bg-[#111827] hover:border-[#344054]'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 gap-3">
                  <div
                    className="mt-0.5 h-8 w-8 rounded-lg flex items-center justify-center shrink-0"
                    style={{ backgroundColor: `${division.color}22`, border: `1px solid ${division.color}44` }}
                  >
                    <Bot size={15} style={{ color: division.color }} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[#F9FAFB] truncate">{division.label}</p>
                    <p className="text-xs text-[#667085] truncate">{division.agent || 'base-geral'}</p>
                    <p className="text-xs text-[#98A2B3] mt-1 line-clamp-2">{division.description}</p>
                  </div>
                </div>
                <span
                  className="text-[10px] px-2 py-0.5 rounded-full shrink-0"
                  style={{
                    color: division.ready ? '#00FFA7' : '#FBBF24',
                    background: division.ready ? 'rgba(0,255,167,0.08)' : 'rgba(251,191,36,0.1)',
                    border: `1px solid ${division.ready ? 'rgba(0,255,167,0.18)' : 'rgba(251,191,36,0.22)'}`,
                  }}
                >
                  {division.ready ? 'pronta' : 'pendente'}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                <span className="rounded-lg bg-[#0C111D] px-2 py-1 text-[#98A2B3]">
                  <strong className="text-[#E6EDF3]">{division.documents_count}</strong> docs
                </span>
                <span className="rounded-lg bg-[#0C111D] px-2 py-1 text-[#98A2B3]">
                  <strong className="text-[#E6EDF3]">{division.chunks_count}</strong> chunks
                </span>
              </div>
            </button>
          ))}
        </div>

        <div className="space-y-6">
          <section className="rounded-xl border border-[#243044] bg-[#111827] p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
              <div>
                <h2 className="text-base font-semibold text-[#F9FAFB]">Upload para {selected?.label}</h2>
                <p className="text-xs text-[#667085] mt-1">{selected?.agent || 'Conhecimento comum dos agentes'}</p>
              </div>
              {files.length > 0 && (
                <button
                  onClick={() => setFiles([])}
                  className="text-xs text-[#98A2B3] hover:text-[#F9FAFB]"
                >
                  Limpar seleção
                </button>
              )}
            </div>

            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                addFiles(Array.from(e.dataTransfer.files))
              }}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                dragging ? 'border-[#00FFA7] bg-[#00FFA7]/5' : 'border-[#344054] hover:border-[#00FFA7]/40'
              }`}
            >
              <Upload size={26} className={dragging ? 'text-[#00FFA7] mx-auto mb-3' : 'text-[#667085] mx-auto mb-3'} />
              <p className="text-sm font-medium text-[#D0D5DD]">Arraste arquivos ou clique para selecionar</p>
              <p className="text-xs text-[#667085] mt-1">PDF, DOCX, PPTX, XLSX, HTML, imagens, TXT, MD, CSV e JSON</p>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.docx,.pptx,.xlsx,.html,.htm,.epub,.txt,.md,.markdown,.csv,.json,.png,.jpg,.jpeg,.gif,.webp,.tiff,.tif"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files) addFiles(Array.from(e.target.files))
                  e.currentTarget.value = ''
                }}
              />
            </div>

            {files.length > 0 && (
              <div className="mt-4 space-y-3">
                <div className="flex flex-wrap gap-2">
                  {files.map((file, idx) => (
                    <span key={`${file.name}-${idx}`} className="inline-flex items-center gap-1 rounded-lg border border-[#344054] bg-[#0C111D] px-2.5 py-1 text-xs text-[#D0D5DD]">
                      <FileText size={12} /> {file.name}
                    </span>
                  ))}
                </div>
                <button
                  onClick={handleUpload}
                  disabled={uploading || !canManage || !selected?.ready}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#00FFA7] text-[#0C111D] text-sm font-medium disabled:opacity-50"
                >
                  {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                  Enviar para {selected?.label}
                </button>
                {!canManage && <p className="text-xs text-[#FBBF24]">Seu papel precisa de permissão knowledge:manage para upload.</p>}
                {selected && !selected.ready && <p className="text-xs text-[#FBBF24]">Prepare a divisão antes de enviar arquivos.</p>}
              </div>
            )}

            {uploads.length > 0 && (
              <div className="mt-5 space-y-2">
                {uploads.slice(0, 6).map((item) => (
                  <div key={item.id} className="flex items-center justify-between gap-3 rounded-lg bg-[#0C111D] border border-[#243044] px-3 py-2">
                    <div className="min-w-0">
                      <p className="text-sm text-[#D0D5DD] truncate">{item.filename}</p>
                      {item.error && <p className="text-xs text-red-300 mt-0.5">{item.error}</p>}
                    </div>
                    <span
                      className="text-xs px-2 py-0.5 rounded-full shrink-0"
                      style={{ color: statusColor(item.phase), background: `${statusColor(item.phase)}14`, border: `1px solid ${statusColor(item.phase)}33` }}
                    >
                      {phaseLabel(item.phase)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-[#243044] bg-[#111827] p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
              <div>
                <h2 className="text-base font-semibold text-[#F9FAFB]">Busca RAG</h2>
                <p className="text-xs text-[#667085] mt-1">Consulta híbrida vetorial + BM25 nos chunks prontos</p>
              </div>
              <select
                value={searchScope}
                onChange={(e) => setSearchScope(e.target.value)}
                className="bg-[#0C111D] border border-[#344054] rounded-lg px-3 py-2 text-sm text-[#D0D5DD] focus:border-[#00FFA7] focus:outline-none"
              >
                <option value="all">Todas as divisões</option>
                {divisions.map((division) => (
                  <option key={division.slug} value={division.slug}>{division.label}</option>
                ))}
              </select>
            </div>

            <div className="flex gap-3">
              <div className="relative flex-1">
                <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#667085]" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="Buscar instruções, regras, prazos ou documentos..."
                  className="w-full bg-[#0C111D] border border-[#344054] rounded-lg pl-9 pr-3 py-2.5 text-sm text-[#F9FAFB] placeholder-[#667085] focus:border-[#00FFA7] focus:outline-none"
                />
              </div>
              <button
                onClick={handleSearch}
                disabled={searching || !query.trim()}
                className="px-4 py-2 rounded-lg bg-[#00FFA7] text-[#0C111D] text-sm font-medium disabled:opacity-50"
              >
                {searching ? 'Buscando...' : 'Buscar'}
              </button>
            </div>

            {searchResults && (
              <div className="mt-4 space-y-3">
                {searchResults.length === 0 ? (
                  <p className="text-sm text-[#667085] py-4">Nenhum resultado encontrado.</p>
                ) : (
                  searchResults.map((hit) => (
                    <div key={hit.chunk_id} className="rounded-lg border border-[#243044] bg-[#0C111D] p-4">
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-[#D0D5DD] truncate">{hit.doc_title || 'Documento'}</p>
                          <p className="text-xs text-[#667085]">{hit.division_label} {hit.content_type ? `- ${hit.content_type}` : ''}</p>
                        </div>
                        {hit.final_score != null && (
                          <span className="text-xs rounded bg-[#00FFA7]/10 text-[#00FFA7] px-2 py-0.5">
                            {hit.final_score.toFixed(4)}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-[#C7D7EA] whitespace-pre-wrap line-clamp-4">{hit.content}</p>
                    </div>
                  ))
                )}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-[#243044] bg-[#111827] p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-base font-semibold text-[#F9FAFB]">Documentos em {selected?.label}</h2>
                <p className="text-xs text-[#667085] mt-1">Últimos arquivos enviados para esta divisão</p>
              </div>
              {documentsLoading && <Loader2 size={15} className="animate-spin text-[#667085]" />}
            </div>

            {documents.length === 0 ? (
              <p className="text-sm text-[#667085] py-4">Nenhum documento nesta divisão.</p>
            ) : (
              <div className="overflow-hidden rounded-lg border border-[#243044]">
                <table className="w-full text-sm">
                  <thead className="bg-[#0C111D] text-xs text-[#667085]">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium">Documento</th>
                      <th className="text-left px-3 py-2 font-medium">Status</th>
                      <th className="text-left px-3 py-2 font-medium">Chunks</th>
                      <th className="text-left px-3 py-2 font-medium">Criado</th>
                      <th className="w-10 px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map((doc) => (
                      <tr key={doc.id} className="border-t border-[#243044]">
                        <td className="px-3 py-2 text-[#D0D5DD]">{doc.title}</td>
                        <td className="px-3 py-2">
                          <span
                            className="text-xs px-2 py-0.5 rounded-full"
                            style={{ color: statusColor(doc.status), background: `${statusColor(doc.status)}14`, border: `1px solid ${statusColor(doc.status)}33` }}
                          >
                            {phaseLabel(doc.status)}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-[#98A2B3]">{doc.chunks_count ?? 0}</td>
                        <td className="px-3 py-2 text-[#98A2B3]">{formatDate(doc.created_at)}</td>
                        <td className="px-3 py-2 text-right">
                          {canManage && (
                            <button
                              onClick={() => handleDelete(doc.id)}
                              className="p-1.5 rounded text-[#667085] hover:text-red-300 hover:bg-red-500/10"
                              title="Excluir documento"
                            >
                              <Trash2 size={14} />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
