import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Link2, Eye, Download, CheckCircle, AlertTriangle, Loader2 } from 'lucide-react'
import { api } from '../lib/api'

interface PreviewResult {
  manifest: Record<string, unknown>
  warnings: string[]
  conflicts?: Record<string, unknown>
}

interface Props {
  onClose: () => void
  onInstalled: () => void
}

type Step = 1 | 2 | 3

export default function PluginInstallModal({ onClose, onInstalled }: Props) {
  const { t } = useTranslation()
  const [step, setStep] = useState<Step>(1)
  const [sourceUrl, setSourceUrl] = useState('')
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [installError, setInstallError] = useState<string | null>(null)
  const [installedSlug, setInstalledSlug] = useState<string | null>(null)

  async function handlePreview() {
    if (!sourceUrl.trim()) return
    setLoadingPreview(true)
    setPreviewError(null)
    try {
      const result = await api.post('/plugins/preview', { source_url: sourceUrl.trim() }) as PreviewResult
      setPreview(result)
      setStep(2)
    } catch (e: unknown) {
      setPreviewError(e instanceof Error ? e.message : t('common.unexpectedError'))
    } finally {
      setLoadingPreview(false)
    }
  }

  async function handleInstall() {
    if (!sourceUrl.trim()) return
    setInstalling(true)
    setInstallError(null)
    try {
      const result = await api.post('/plugins/install', { source_url: sourceUrl.trim() }) as { slug: string }
      setInstalledSlug(result.slug)
      setStep(3)
    } catch (e: unknown) {
      setInstallError(e instanceof Error ? e.message : t('common.unexpectedError'))
    } finally {
      setInstalling(false)
    }
  }

  const manifest = preview?.manifest ?? {}
  const warnings = preview?.warnings ?? []
  const conflicts = preview?.conflicts ? Object.keys(preview.conflicts) : []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-[#161b22] border border-[#344054] rounded-2xl w-full max-w-lg shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#21262d]">
          <div>
            <h2 className="text-base font-semibold text-[#e6edf3]">{t('plugins.installPlugin')}</h2>
            <p className="text-xs text-[#667085] mt-0.5">{t('plugins.stepOf', { current: step, total: 3 })}</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[#667085] hover:text-[#D0D5DD] hover:bg-white/5 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Step indicators */}
        <div className="flex items-center gap-2 px-6 py-3 border-b border-[#21262d]">
          {([1, 2, 3] as Step[]).map((s) => (
            <div key={s} className="flex items-center gap-2">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                s < step ? 'bg-[#00FFA7] text-black' :
                s === step ? 'bg-[#00FFA7]/20 text-[#00FFA7] border border-[#00FFA7]/40' :
                'bg-[#21262d] text-[#667085]'
              }`}>
                {s < step ? <CheckCircle size={12} /> : s}
              </div>
              {s < 3 && <div className={`flex-1 h-px w-8 ${s < step ? 'bg-[#00FFA7]/40' : 'bg-[#21262d]'}`} />}
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="px-6 py-5">
          {/* Step 1: URL input */}
          {step === 1 && (
            <div>
              <label className="block text-sm font-medium text-[#D0D5DD] mb-2 flex items-center gap-2">
                <Link2 size={14} className="text-[#00FFA7]" />
                {t('plugins.sourceUrl')}
              </label>
              <input
                type="url"
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
                placeholder="https://github.com/org/plugin-name"
                className="w-full bg-[#0C111D] border border-[#344054] rounded-lg px-3 py-2.5 text-sm text-[#e6edf3] placeholder-[#667085] focus:outline-none focus:border-[#00FFA7]/50 transition-colors"
                onKeyDown={(e) => { if (e.key === 'Enter') handlePreview() }}
              />
              <p className="mt-2 text-xs text-[#667085]">{t('plugins.onlyHttpsAllowed')}</p>
              {previewError && (
                <p className="mt-2 text-xs text-red-400 flex items-center gap-1.5">
                  <AlertTriangle size={12} /> {previewError}
                </p>
              )}
            </div>
          )}

          {/* Step 2: Preview */}
          {step === 2 && preview && (
            <div className="space-y-4">
              <div className="bg-[#0C111D] border border-[#21262d] rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Eye size={14} className="text-[#00FFA7]" />
                  <span className="text-sm font-medium text-[#e6edf3]">{t('plugins.manifestPreview')}</span>
                </div>
                <dl className="space-y-1.5 text-xs">
                  {['name', 'version', 'author', 'license', 'description'].map((k) =>
                    manifest[k] ? (
                      <div key={k} className="flex gap-2">
                        <dt className="text-[#667085] capitalize w-20 shrink-0">{k}</dt>
                        <dd className="text-[#e6edf3] break-all">{String(manifest[k])}</dd>
                      </div>
                    ) : null
                  )}
                  {Array.isArray(manifest['capabilities']) && (manifest['capabilities'] as string[]).length > 0 && (
                    <div className="flex gap-2">
                      <dt className="text-[#667085] capitalize w-20 shrink-0">capabilities</dt>
                      <dd className="text-[#e6edf3]">{(manifest['capabilities'] as string[]).join(', ')}</dd>
                    </div>
                  )}
                </dl>
              </div>

              {warnings.length > 0 && (
                <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-xl p-3">
                  <p className="text-xs font-medium text-yellow-400 mb-1.5 flex items-center gap-1.5">
                    <AlertTriangle size={12} /> {t('plugins.warnings')} ({warnings.length})
                  </p>
                  <ul className="space-y-1">
                    {warnings.map((w, i) => (
                      <li key={i} className="text-xs text-yellow-300/80">{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {conflicts.length > 0 && (
                <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-3">
                  <p className="text-xs font-medium text-red-400 mb-1 flex items-center gap-1.5">
                    <AlertTriangle size={12} /> {t('plugins.conflicts')}
                  </p>
                  <p className="text-xs text-red-300/80">{conflicts.join(', ')}</p>
                </div>
              )}

              {installError && (
                <p className="text-xs text-red-400 flex items-center gap-1.5">
                  <AlertTriangle size={12} /> {installError}
                </p>
              )}
            </div>
          )}

          {/* Step 3: Done */}
          {step === 3 && (
            <div className="text-center py-4">
              <div className="flex items-center justify-center w-14 h-14 rounded-full bg-[#00FFA7]/10 border border-[#00FFA7]/20 mx-auto mb-4">
                <CheckCircle size={28} className="text-[#00FFA7]" />
              </div>
              <h3 className="text-base font-semibold text-[#e6edf3] mb-1">{t('plugins.installedSuccessTitle')}</h3>
              <p className="text-sm text-[#667085]">
                {installedSlug && <code className="text-[#00FFA7]">{installedSlug}</code>} {t('plugins.installedDesc')}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[#21262d]">
          {step < 3 && (
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-[#667085] hover:text-[#D0D5DD] transition-colors"
            >
              {t('common.cancel')}
            </button>
          )}

          {step === 1 && (
            <button
              onClick={handlePreview}
              disabled={!sourceUrl.trim() || loadingPreview}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-[#00FFA7] text-black rounded-lg hover:bg-[#00FFA7]/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loadingPreview ? <Loader2 size={14} className="animate-spin" /> : <Eye size={14} />}
              {t('plugins.preview')}
            </button>
          )}

          {step === 2 && (
            <>
              <button
                onClick={() => setStep(1)}
                className="px-4 py-2 text-sm text-[#667085] hover:text-[#D0D5DD] transition-colors"
              >
                {t('common.back')}
              </button>
              <button
                onClick={handleInstall}
                disabled={installing || conflicts.length > 0}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-[#00FFA7] text-black rounded-lg hover:bg-[#00FFA7]/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {installing ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                {t('plugins.confirmInstall')}
              </button>
            </>
          )}

          {step === 3 && (
            <button
              onClick={() => { onInstalled(); onClose() }}
              className="px-4 py-2 text-sm font-medium bg-[#00FFA7] text-black rounded-lg hover:bg-[#00FFA7]/90 transition-colors"
            >
              {t('common.close')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
