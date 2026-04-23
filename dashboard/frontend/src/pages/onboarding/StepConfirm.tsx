import { Check, GitBranch, Cpu } from 'lucide-react'

interface StepConfirmProps {
  provider: string | null
  wantBrainRepo: boolean | null
  onComplete: () => void
  onSkip: () => void
  onBack: () => void
}

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic (Claude)',
  openai: 'OpenAI (GPT-4)',
  openrouter: 'OpenRouter',
  codex: 'Codex',
}

export default function StepConfirm({ provider, wantBrainRepo, onComplete, onSkip, onBack }: StepConfirmProps) {
  return (
    <div className="min-h-screen bg-[#080c14] flex items-center justify-center px-4 font-[Inter,-apple-system,sans-serif]">
      <div className="w-full max-w-[480px] relative z-10">
        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <span className="text-[11px] text-[#5a6b7f] uppercase tracking-[0.08em]">Step 3 of 3</span>
          <div className="flex gap-1.5">
            <span className="h-1.5 w-8 rounded-full bg-[#00FFA7]" />
            <span className="h-1.5 w-8 rounded-full bg-[#00FFA7]" />
            <span className="h-1.5 w-8 rounded-full bg-[#00FFA7]" />
          </div>
        </div>

        <div className="rounded-xl border border-[#152030] bg-[#0b1018] shadow-[0_4px_40px_rgba(0,0,0,0.4)]">
          <div className="px-7 pt-7 pb-5 border-b border-[#152030]">
            <h2 className="text-[16px] font-semibold text-[#e2e8f0]">Review & Finish</h2>
            <p className="text-[11px] text-[#4a5a6e] mt-1">Your workspace is ready to go</p>
          </div>

          <div className="px-7 py-6 space-y-4">
            {/* Summary */}
            <div className="space-y-2">
              <p className="text-[11px] font-semibold text-[#5a6b7f] uppercase tracking-[0.08em] mb-3">
                Configuration summary
              </p>

              <div className="flex items-center gap-3 p-3 rounded-lg bg-[#0f1520] border border-[#1e2a3a]">
                <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[#00FFA7]/10">
                  <Cpu size={14} className="text-[#00FFA7]" />
                </div>
                <div className="flex-1">
                  <p className="text-[11px] text-[#5a6b7f]">AI Provider</p>
                  <p className="text-[13px] font-medium text-[#e2e8f0]">
                    {provider ? (PROVIDER_LABELS[provider] || provider) : 'Not configured'}
                  </p>
                </div>
                <Check size={14} className="text-[#00FFA7] flex-shrink-0" />
              </div>

              <div className="flex items-center gap-3 p-3 rounded-lg bg-[#0f1520] border border-[#1e2a3a]">
                <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[#00FFA7]/10">
                  <GitBranch size={14} className="text-[#00FFA7]" />
                </div>
                <div className="flex-1">
                  <p className="text-[11px] text-[#5a6b7f]">Brain Repo</p>
                  <p className="text-[13px] font-medium text-[#e2e8f0]">
                    {wantBrainRepo ? 'Connected' : 'Skipped'}
                  </p>
                </div>
                {wantBrainRepo ? (
                  <Check size={14} className="text-[#00FFA7] flex-shrink-0" />
                ) : (
                  <span className="text-[10px] text-[#5a6b7f]">optional</span>
                )}
              </div>
            </div>

            <div className="p-3 rounded-lg bg-[#0a1a12] border border-[#00FFA7]/15">
              <p className="text-[11px] text-[#4a7a5a] leading-relaxed">
                You can always configure the Brain Repo later from <span className="text-[#00FFA7]/70">Settings → Brain Repo</span>.
              </p>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={onBack}
                className="flex-none py-3 px-4 rounded-lg border border-[#152030] text-[#5a6b7f] hover:border-[#00FFA7]/30 hover:text-[#e2e8f0] text-sm font-medium transition-colors"
              >
                Back
              </button>
              <button
                onClick={onComplete}
                className="flex-1 py-3 rounded-lg bg-[#00FFA7] text-[#080c14] hover:bg-[#00e69a] text-sm font-semibold transition-colors"
              >
                Finish setup
              </button>
            </div>

            <button
              onClick={onSkip}
              className="w-full py-2 text-[11px] text-[#2d3d4f] hover:text-[#5a6b7f] transition-colors"
            >
              Skip everything and go to workspace
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
