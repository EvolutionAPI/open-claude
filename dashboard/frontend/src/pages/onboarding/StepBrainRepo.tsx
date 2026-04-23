import { GitBranch, History, RefreshCw, Shield } from 'lucide-react'

interface StepBrainRepoProps {
  onYes: () => void
  onNo: () => void
  onBack: () => void
}

export default function StepBrainRepo({ onYes, onNo, onBack }: StepBrainRepoProps) {
  return (
    <div className="min-h-screen bg-[#080c14] flex items-center justify-center px-4 font-[Inter,-apple-system,sans-serif]">
      <div className="w-full max-w-[480px] relative z-10">
        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <span className="text-[11px] text-[#5a6b7f] uppercase tracking-[0.08em]">Step 2 of 3</span>
          <div className="flex gap-1.5">
            <span className="h-1.5 w-8 rounded-full bg-[#00FFA7]" />
            <span className="h-1.5 w-8 rounded-full bg-[#00FFA7]" />
            <span className="h-1.5 w-8 rounded-full bg-[#152030]" />
          </div>
        </div>

        <div className="rounded-xl border border-[#152030] bg-[#0b1018] shadow-[0_4px_40px_rgba(0,0,0,0.4)]">
          <div className="px-7 pt-7 pb-5 border-b border-[#152030]">
            <div className="flex items-center gap-3 mb-2">
              <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-[#00FFA7]/10 border border-[#00FFA7]/20">
                <GitBranch size={18} className="text-[#00FFA7]" />
              </div>
              <h2 className="text-[16px] font-semibold text-[#e2e8f0]">Brain Repo</h2>
            </div>
            <p className="text-[11px] text-[#4a5a6e]">Version control for your workspace configuration</p>
          </div>

          <div className="px-7 py-6 space-y-5">
            <p className="text-[13px] text-[#8a9ab0] leading-relaxed">
              The <span className="text-[#e2e8f0] font-medium">Brain Repo</span> is a private GitHub repository
              that stores all your agents, memories, skills, and workspace configuration.
            </p>

            {/* Benefits list */}
            <div className="space-y-3">
              {[
                { icon: History, label: 'Snapshot history', desc: 'Daily, weekly and milestone snapshots' },
                { icon: RefreshCw, label: 'Restore anytime', desc: 'Roll back your entire workspace in seconds' },
                { icon: Shield, label: 'Your data, your repo', desc: 'Stored in your own private GitHub repository' },
              ].map(({ icon: Icon, label, desc }) => (
                <div key={label} className="flex items-start gap-3 p-3 rounded-lg bg-[#0f1520] border border-[#1e2a3a]">
                  <Icon size={14} className="text-[#00FFA7] mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-[12px] font-medium text-[#e2e8f0]">{label}</p>
                    <p className="text-[11px] text-[#5a6b7f]">{desc}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={onBack}
                className="flex-none py-3 px-4 rounded-lg border border-[#152030] text-[#5a6b7f] hover:border-[#00FFA7]/30 hover:text-[#e2e8f0] text-sm font-medium transition-colors"
              >
                Back
              </button>
              <button
                onClick={onNo}
                className="flex-1 py-3 rounded-lg border border-[#152030] text-[#5a6b7f] hover:border-[#00FFA7]/30 hover:text-[#e2e8f0] text-sm font-medium transition-colors"
              >
                Not now
              </button>
              <button
                onClick={onYes}
                className="flex-1 py-3 rounded-lg bg-[#00FFA7] text-[#080c14] hover:bg-[#00e69a] text-sm font-semibold transition-colors"
              >
                Yes, version it
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
