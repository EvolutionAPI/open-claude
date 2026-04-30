import { CheckCircle2, AlertCircle, Plus, Trash2, Globe } from 'lucide-react'
import { getPlatformMeta, type SocialPlatform } from './types'

interface SocialAccountsTabProps {
  platforms: SocialPlatform[]
  onDisconnect: (platformId: string, index: number) => void
}

export function SocialAccountsTab({ platforms, onDisconnect }: SocialAccountsTabProps) {
  return (
    <div>
      <div className="flex items-center gap-2.5 mb-6">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[#00FFA7]/8 border border-[#00FFA7]/15">
          <Globe size={14} className="text-[#00FFA7]" />
        </div>
        <h2 className="text-base font-semibold text-[#e6edf3]">Social Accounts</h2>
      </div>

      <div className="space-y-6">
        {platforms.map((platform) => {
          const platMeta = getPlatformMeta(platform.id)
          const PlatIcon = platMeta.icon

          return (
            <div key={platform.id}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div
                    className="flex h-8 w-8 items-center justify-center rounded-lg"
                    style={{ backgroundColor: platMeta.colorMuted }}
                  >
                    <PlatIcon size={16} style={{ color: platMeta.color }} />
                  </div>
                  <span className="font-semibold text-[#e6edf3] text-sm">{platform.name}</span>
                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-white/[0.04] text-[#667085] border border-[#21262d]">
                    {platform.accounts.length} account{platform.accounts.length !== 1 ? 's' : ''}
                  </span>
                </div>
                <a
                  href={`/connect/${platform.id}`}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-[#00FFA7]/10 text-[#00FFA7] border border-[#00FFA7]/20 hover:bg-[#00FFA7]/20 hover:shadow-[0_0_12px_rgba(0,255,167,0.10)] transition-all"
                >
                  <Plus size={13} /> Add account
                </a>
              </div>

              {platform.accounts.length > 0 ? (
                <div className="space-y-2">
                  {platform.accounts.map((acc) => {
                    const isOk = acc.status === 'connected'
                    const isExpiring = acc.status === 'expiring'
                    const isExpired = acc.status === 'expired'

                    return (
                      <div
                        key={acc.index}
                        className="group relative rounded-xl border border-[#21262d] bg-[#161b22] p-4 flex items-center justify-between transition-all duration-300 hover:border-transparent"
                      >
                        <div
                          className="pointer-events-none absolute inset-0 rounded-xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                          style={{
                            boxShadow: `inset 0 0 0 1px ${platMeta.color}44, 0 0 16px ${platMeta.glowColor}`,
                            borderRadius: 'inherit',
                          }}
                        />

                        <div className="relative flex items-center gap-3">
                          <span
                            className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                            style={{
                              backgroundColor: isOk ? '#00FFA7' : isExpired ? '#EF4444' : isExpiring ? '#FBBF24' : '#3F3F46',
                              boxShadow: isOk ? '0 0 6px rgba(0,255,167,0.5)' : isExpired ? '0 0 6px rgba(239,68,68,0.5)' : 'none',
                            }}
                          />
                          <div>
                            <p className="text-sm font-medium text-[#e6edf3]">{acc.label}</p>
                            <p className="text-xs text-[#667085] mt-0.5">{acc.detail}</p>
                          </div>
                        </div>

                        <div className="relative flex items-center gap-2">
                          <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded-full border ${
                            isOk ? 'bg-[#00FFA7]/10 text-[#00FFA7] border-[#00FFA7]/25' :
                            isExpiring ? 'bg-[#FBBF24]/10 text-[#FBBF24] border-[#FBBF24]/25' :
                            isExpired ? 'bg-red-500/10 text-red-400 border-red-500/25' :
                            'bg-white/[0.04] text-[#667085] border-[#21262d]'
                          }`}>
                            {isOk && <CheckCircle2 size={10} />}
                            {(isExpiring || isExpired) && <AlertCircle size={10} />}
                            {isOk ? 'Connected' :
                             isExpiring ? `Expires in ${acc.days_left}d` :
                             isExpired ? 'Expired' : 'Incomplete'}
                          </span>
                          <button
                            onClick={() => onDisconnect(platform.id, acc.index)}
                            className="p-1.5 rounded-lg hover:bg-red-500/10 text-[#667085] hover:text-red-400 transition-colors"
                            title="Remove"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-[#21262d] bg-[#161b22]/50 p-6 text-center">
                  <p className="text-sm text-[#667085]">No accounts connected</p>
                  <p className="text-xs text-[#3F3F46] mt-1">Click "Add account" to get started</p>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
