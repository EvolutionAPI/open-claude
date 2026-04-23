import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { api } from '../../lib/api'

interface Provider {
  id: string
  name: string
  description: string
  color: string
}

const PROVIDERS: Provider[] = [
  { id: 'anthropic', name: 'Anthropic', description: 'Claude models — recommended', color: '#D97706' },
  { id: 'openai', name: 'OpenAI', description: 'GPT-4, GPT-4o and others', color: '#10B981' },
  { id: 'openrouter', name: 'OpenRouter', description: 'Multi-model gateway', color: '#6366F1' },
  { id: 'codex', name: 'Codex', description: 'OpenAI Codex models', color: '#8B5CF6' },
]

const inp = "w-full px-4 py-3 rounded-lg bg-[#0f1520] border border-[#1e2a3a] text-[#e2e8f0] placeholder-[#3d4f65] text-sm transition-colors duration-200 focus:outline-none focus:border-[#00FFA7]/60 focus:ring-1 focus:ring-[#00FFA7]/20"
const lbl = "block text-[11px] font-semibold text-[#5a6b7f] mb-1.5 tracking-[0.08em] uppercase"

interface StepProviderProps {
  onNext: (provider: string) => void
  onBack: () => void
}

export default function StepProvider({ onNext, onBack }: StepProviderProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const handleNext = async () => {
    if (!selected) {
      setError('Please select a provider')
      return
    }
    if (!apiKey.trim()) {
      setError('API key is required')
      return
    }
    setError('')
    setSaving(true)
    try {
      await api.post('/onboarding/provider', { provider: selected, api_key: apiKey.trim() })
      onNext(selected)
    } catch (ex: unknown) {
      setError(ex instanceof Error ? ex.message : 'Failed to save provider')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#080c14] flex items-center justify-center px-4 font-[Inter,-apple-system,sans-serif]">
      <div className="w-full max-w-[480px] relative z-10">
        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <span className="text-[11px] text-[#5a6b7f] uppercase tracking-[0.08em]">Step 1 of 3</span>
          <div className="flex gap-1.5">
            <span className="h-1.5 w-8 rounded-full bg-[#00FFA7]" />
            <span className="h-1.5 w-8 rounded-full bg-[#152030]" />
            <span className="h-1.5 w-8 rounded-full bg-[#152030]" />
          </div>
        </div>

        <div className="rounded-xl border border-[#152030] bg-[#0b1018] shadow-[0_4px_40px_rgba(0,0,0,0.4)]">
          <div className="px-7 pt-7 pb-5 border-b border-[#152030]">
            <h2 className="text-[16px] font-semibold text-[#e2e8f0]">Choose your AI provider</h2>
            <p className="text-[11px] text-[#4a5a6e] mt-1">Select the provider and enter your API key</p>
          </div>

          <div className="px-7 py-6 space-y-4">
            {error && (
              <div className="px-3 py-2.5 rounded-lg bg-[#1a0a0a] border border-[#3a1515] text-[#f87171] text-xs">
                {error}
              </div>
            )}

            {/* Provider cards */}
            <div className="grid grid-cols-2 gap-2">
              {PROVIDERS.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setSelected(p.id)}
                  className={`p-3 rounded-lg border text-left transition-all duration-200 ${
                    selected === p.id
                      ? 'border-[#00FFA7]/60 bg-[#00FFA7]/8'
                      : 'border-[#1e2a3a] bg-[#0f1520] hover:border-[#2a3a4a]'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className="h-2 w-2 rounded-full flex-shrink-0"
                      style={{ backgroundColor: p.color }}
                    />
                    <span className="text-[13px] font-semibold text-[#e2e8f0]">{p.name}</span>
                  </div>
                  <p className="text-[10px] text-[#5a6b7f] leading-snug">{p.description}</p>
                </button>
              ))}
            </div>

            {/* API Key input */}
            {selected && (
              <div>
                <label className={lbl}>API Key</label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    className={`${inp} pr-10`}
                    placeholder={`${PROVIDERS.find(p => p.id === selected)?.name} API key`}
                    autoFocus
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#5a6b7f] hover:text-[#e2e8f0] transition-colors"
                  >
                    {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button
                onClick={onBack}
                className="flex-1 py-3 rounded-lg border border-[#152030] text-[#5a6b7f] hover:border-[#00FFA7]/30 hover:text-[#e2e8f0] text-sm font-medium transition-colors"
              >
                Back
              </button>
              <button
                onClick={handleNext}
                disabled={saving || !selected || !apiKey.trim()}
                className="flex-1 py-3 rounded-lg bg-[#00FFA7] text-[#080c14] hover:bg-[#00e69a] text-sm font-semibold transition-colors disabled:opacity-40"
              >
                {saving ? 'Saving...' : 'Next'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
