import { useState, useEffect } from 'react'
import { Plus, GitBranch, Loader2 } from 'lucide-react'
import { api } from '../../lib/api'
import { useAuth } from '../../context/AuthContext'

const inp = "w-full px-4 py-3 rounded-lg bg-[#0f1520] border border-[#1e2a3a] text-[#e2e8f0] placeholder-[#3d4f65] text-sm transition-colors duration-200 focus:outline-none focus:border-[#00FFA7]/60 focus:ring-1 focus:ring-[#00FFA7]/20"

interface Repo {
  name: string
  full_name: string
  html_url: string
}

interface StepBrainChooseProps {
  token: string
  onNext: () => void
  onBack: () => void
}

export default function StepBrainChoose({ token, onNext, onBack }: StepBrainChooseProps) {
  const { user } = useAuth()
  const [mode, setMode] = useState<'create' | 'existing'>('create')
  const [repoName, setRepoName] = useState(`evo-brain-${user?.username || 'workspace'}`)
  const [repos, setRepos] = useState<Repo[]>([])
  const [selectedRepo, setSelectedRepo] = useState<Repo | null>(null)
  const [loadingRepos, setLoadingRepos] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (mode === 'existing') {
      setLoadingRepos(true)
      api.get('/brain-repo/detect')
        .then((data: { repos: Repo[] }) => setRepos(data.repos || []))
        .catch(() => setRepos([]))
        .finally(() => setLoadingRepos(false))
    }
  }, [mode])

  const handleSave = async () => {
    setError('')
    setSaving(true)
    try {
      if (mode === 'create') {
        if (!repoName.trim()) {
          setError('Repository name is required')
          setSaving(false)
          return
        }
        await api.post('/brain-repo/connect', { token, create_repo: repoName.trim() })
      } else {
        if (!selectedRepo) {
          setError('Please select a repository')
          setSaving(false)
          return
        }
        await api.post('/brain-repo/connect', { token, repo_url: selectedRepo.html_url })
      }
      onNext()
    } catch (ex: unknown) {
      setError(ex instanceof Error ? ex.message : 'Failed to configure repository')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#080c14] flex items-center justify-center px-4 font-[Inter,-apple-system,sans-serif]">
      <div className="w-full max-w-[480px] relative z-10">
        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <span className="text-[11px] text-[#5a6b7f] uppercase tracking-[0.08em]">Step 2b of 3</span>
          <div className="flex gap-1.5">
            <span className="h-1.5 w-8 rounded-full bg-[#00FFA7]" />
            <span className="h-1.5 w-8 rounded-full bg-[#00FFA7]" />
            <span className="h-1.5 w-8 rounded-full bg-[#152030]" />
          </div>
        </div>

        <div className="rounded-xl border border-[#152030] bg-[#0b1018] shadow-[0_4px_40px_rgba(0,0,0,0.4)]">
          <div className="px-7 pt-7 pb-5 border-b border-[#152030]">
            <h2 className="text-[16px] font-semibold text-[#e2e8f0]">Choose a repository</h2>
            <p className="text-[11px] text-[#4a5a6e] mt-1">Create a new one or connect an existing brain repo</p>
          </div>

          <div className="px-7 py-6 space-y-4">
            {error && (
              <div className="px-3 py-2.5 rounded-lg bg-[#1a0a0a] border border-[#3a1515] text-[#f87171] text-xs">
                {error}
              </div>
            )}

            {/* Mode selector */}
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setMode('create')}
                className={`flex items-center gap-2 p-3 rounded-lg border text-left transition-all ${
                  mode === 'create'
                    ? 'border-[#00FFA7]/60 bg-[#00FFA7]/8'
                    : 'border-[#1e2a3a] bg-[#0f1520] hover:border-[#2a3a4a]'
                }`}
              >
                <Plus size={14} className={mode === 'create' ? 'text-[#00FFA7]' : 'text-[#5a6b7f]'} />
                <div>
                  <p className="text-[12px] font-semibold text-[#e2e8f0]">Create new</p>
                  <p className="text-[10px] text-[#5a6b7f]">New private repo</p>
                </div>
              </button>
              <button
                onClick={() => setMode('existing')}
                className={`flex items-center gap-2 p-3 rounded-lg border text-left transition-all ${
                  mode === 'existing'
                    ? 'border-[#00FFA7]/60 bg-[#00FFA7]/8'
                    : 'border-[#1e2a3a] bg-[#0f1520] hover:border-[#2a3a4a]'
                }`}
              >
                <GitBranch size={14} className={mode === 'existing' ? 'text-[#00FFA7]' : 'text-[#5a6b7f]'} />
                <div>
                  <p className="text-[12px] font-semibold text-[#e2e8f0]">Use existing</p>
                  <p className="text-[10px] text-[#5a6b7f]">Detected repos</p>
                </div>
              </button>
            </div>

            {/* Create mode */}
            {mode === 'create' && (
              <div>
                <label className="block text-[11px] font-semibold text-[#5a6b7f] mb-1.5 tracking-[0.08em] uppercase">
                  Repository name
                </label>
                <input
                  type="text"
                  value={repoName}
                  onChange={(e) => setRepoName(e.target.value)}
                  className={inp}
                  placeholder="evo-brain-workspace"
                  autoFocus
                />
                <p className="text-[10px] text-[#5a6b7f] mt-1.5">
                  Will be created as a private repository in your GitHub account.
                </p>
              </div>
            )}

            {/* Existing mode */}
            {mode === 'existing' && (
              <div>
                <label className="block text-[11px] font-semibold text-[#5a6b7f] mb-1.5 tracking-[0.08em] uppercase">
                  Detected repositories
                </label>
                {loadingRepos ? (
                  <div className="flex items-center justify-center py-6">
                    <Loader2 size={18} className="text-[#5a6b7f] animate-spin" />
                  </div>
                ) : repos.length === 0 ? (
                  <div className="py-4 text-center">
                    <p className="text-[12px] text-[#5a6b7f]">No compatible repositories found</p>
                    <p className="text-[11px] text-[#2d3d4f] mt-1">Repositories must contain .evo-brain metadata</p>
                  </div>
                ) : (
                  <div className="space-y-1.5 max-h-48 overflow-y-auto">
                    {repos.map((repo) => (
                      <button
                        key={repo.full_name}
                        onClick={() => setSelectedRepo(repo)}
                        className={`w-full flex items-center gap-3 p-3 rounded-lg border text-left transition-all ${
                          selectedRepo?.full_name === repo.full_name
                            ? 'border-[#00FFA7]/60 bg-[#00FFA7]/8'
                            : 'border-[#1e2a3a] bg-[#0f1520] hover:border-[#2a3a4a]'
                        }`}
                      >
                        <GitBranch size={13} className="text-[#5a6b7f] flex-shrink-0" />
                        <div className="min-w-0">
                          <p className="text-[12px] font-medium text-[#e2e8f0] truncate">{repo.name}</p>
                          <p className="text-[10px] text-[#5a6b7f] truncate">{repo.full_name}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button
                onClick={onBack}
                className="flex-none py-3 px-4 rounded-lg border border-[#152030] text-[#5a6b7f] hover:border-[#00FFA7]/30 hover:text-[#e2e8f0] text-sm font-medium transition-colors"
              >
                Back
              </button>
              <button
                onClick={handleSave}
                disabled={saving || (mode === 'existing' && !selectedRepo)}
                className="flex-1 py-3 rounded-lg bg-[#00FFA7] text-[#080c14] hover:bg-[#00e69a] text-sm font-semibold transition-colors disabled:opacity-40"
              >
                {saving ? 'Connecting...' : 'Next'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
