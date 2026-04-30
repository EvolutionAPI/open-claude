import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Copy, KeyRound, QrCode, ShieldCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { api } from '../lib/api'

type ToastType = 'success' | 'error' | 'info'

const inp = 'w-full px-4 py-3 rounded-lg bg-[#0f1520] border border-[#1e2a3a] text-[#e2e8f0] placeholder-[#3d4f65] text-sm transition-colors duration-200 focus:outline-none focus:border-[#00FFA7]/60 focus:ring-1 focus:ring-[#00FFA7]/20'
const lbl = 'block text-[11px] font-semibold text-[#5a6b7f] mb-1.5 tracking-[0.08em] uppercase'

interface SecurityTabProps {
  showToast: (msg: string, type?: ToastType) => void
}

export default function SecurityTab({ showToast }: SecurityTabProps) {
  const { hasPermission, user } = useAuth()
  const canManage = hasPermission('config', 'manage')
  const [status, setStatus] = useState<any | null>(null)
  const [enrollment, setEnrollment] = useState<any | null>(null)
  const [verificationCode, setVerificationCode] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get('/auth/2fa/status')
      setStatus(data)
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Failed to load 2FA status', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => {
    load()
  }, [load])

  const startSetup = async () => {
    if (!canManage) {
      showToast('Only admin accounts can manage 2FA', 'error')
      return
    }
    setSaving(true)
    try {
      const data = await api.post('/auth/2fa/setup')
      setEnrollment(data)
      setVerificationCode('')
      showToast('2FA enrollment started')
      await load()
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Failed to start 2FA setup', 'error')
    } finally {
      setSaving(false)
    }
  }

  const confirmSetup = async () => {
    if (!canManage) {
      showToast('Only admin accounts can manage 2FA', 'error')
      return
    }
    if (!verificationCode.trim()) {
      showToast('Enter the verification code from your authenticator app', 'error')
      return
    }
    setSaving(true)
    try {
      await api.post('/auth/2fa/confirm', { code: verificationCode.trim() })
      setEnrollment(null)
      setVerificationCode('')
      setPassword('')
      showToast('Two-factor authentication enabled')
      await load()
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Failed to confirm 2FA', 'error')
    } finally {
      setSaving(false)
    }
  }

  const disableTwoFactor = async () => {
    if (!canManage) {
      showToast('Only admin accounts can manage 2FA', 'error')
      return
    }
    if (!password.trim()) {
      showToast('Enter your current password to disable 2FA', 'error')
      return
    }
    setSaving(true)
    try {
      await api.post('/auth/2fa/disable', { password, totp_code: verificationCode.trim() })
      setEnrollment(null)
      setVerificationCode('')
      setPassword('')
      showToast('Two-factor authentication disabled')
      await load()
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Failed to disable 2FA', 'error')
    } finally {
      setSaving(false)
    }
  }

  const secret = enrollment?.secret || (status?.enrollment_pending ? 'Enrollment pending in session' : '')
  const provisioningUri = enrollment?.otpauth_uri || ''

  return (
    <div className="max-w-2xl space-y-5">
      <div className="rounded-2xl border border-[#21262d] bg-[#161b22] p-5">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h3 className="text-[13px] font-semibold text-[#e6edf3] flex items-center gap-2">
              <ShieldCheck size={15} className="text-[#00FFA7]" />
              Two-factor authentication
            </h3>
            <p className="text-[11px] text-[#667085] mt-1">
              Protect admin access with a TOTP authenticator app.
            </p>
          </div>
          <div className="text-right text-[11px] text-[#667085]">
            <div className={status?.enabled ? 'text-[#00FFA7]' : 'text-[#f87171]'}>
              {status?.enabled ? 'Enabled' : 'Disabled'}
            </div>
            <div>{user?.role || 'user'}</div>
          </div>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => <div key={i} className="skeleton h-10 rounded-lg" />)}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-xl border border-[#1e2a3a] bg-[#0f1520] p-4">
              <div className="flex items-center gap-2 text-sm text-[#e6edf3]">
                <KeyRound size={14} className="text-[#00FFA7]" />
                <span>Current status</span>
              </div>
              <p className="mt-2 text-xs text-[#667085]">
                {status?.enabled
                  ? `Enabled${status?.confirmed_at ? ` since ${status.confirmed_at}` : ''}`
                  : '2FA is not enabled for this account.'}
              </p>
              {status?.last_used_step ? (
                <p className="mt-1 text-[11px] text-[#5a6b7f]">Last accepted time-step: {status.last_used_step}</p>
              ) : null}
            </div>

            {!canManage && (
              <div className="rounded-xl border border-[#3a2a2a] bg-[#1a0a0a] p-4 text-xs text-[#f87171] flex items-start gap-2">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <span>Only admin accounts can enroll or disable 2FA.</span>
              </div>
            )}

            {secret && (
              <div className="rounded-xl border border-[#1e2a3a] bg-[#0b1018] p-4 space-y-3">
                <div className="flex items-center gap-2 text-sm text-[#e6edf3]">
                  <QrCode size={14} className="text-[#00FFA7]" />
                  <span>Enrollment secret</span>
                </div>
                <div className="rounded-lg border border-[#1e2a3a] bg-[#0f1520] px-3 py-2 text-xs font-mono text-[#00FFA7] break-all">
                  {secret}
                </div>
                {provisioningUri && (
                  <div className="rounded-lg border border-[#1e2a3a] bg-[#0f1520] px-3 py-2 text-[11px] text-[#667085] break-all">
                    {provisioningUri}
                  </div>
                )}
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      if (secret) {
                        await navigator.clipboard.writeText(secret)
                        showToast('Secret copied to clipboard')
                      }
                    } catch {
                      showToast('Clipboard copy failed', 'error')
                    }
                  }}
                  className="inline-flex items-center gap-2 text-[11px] px-3 py-1.5 rounded-md border border-[#1e2a3a] text-[#e6edf3] hover:text-[#00FFA7] hover:border-[#00FFA7]/40 transition-colors"
                >
                  <Copy size={12} />
                  Copy secret
                </button>
              </div>
            )}

            {canManage && (
              <div className="grid gap-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <button
                    type="button"
                    disabled={saving}
                    onClick={startSetup}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#00FFA7] px-4 py-2.5 text-sm font-semibold text-[#080c14] transition-colors hover:bg-[#00e69a] disabled:opacity-40"
                  >
                    {status?.enabled ? 'Regenerate secret' : 'Start setup'}
                  </button>
                  <button
                    type="button"
                    disabled={saving || !secret}
                    onClick={confirmSetup}
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-[#1e2a3a] px-4 py-2.5 text-sm font-semibold text-[#e6edf3] transition-colors hover:border-[#00FFA7]/40 hover:text-[#00FFA7] disabled:opacity-40"
                  >
                    Confirm enrollment
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className={lbl}>Verification code</label>
                    <input
                      type="text"
                      value={verificationCode}
                      onChange={(e) => setVerificationCode(e.target.value)}
                      className={inp}
                      placeholder="123456"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                    />
                  </div>
                  <div>
                    <label className={lbl}>Current password</label>
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className={inp}
                      placeholder="••••••••"
                      autoComplete="current-password"
                    />
                  </div>
                </div>

                <button
                  type="button"
                  disabled={saving || !status?.enabled}
                  onClick={disableTwoFactor}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-[#3a2a2a] bg-[#1a0a0a] px-4 py-2.5 text-sm font-semibold text-[#f87171] transition-colors hover:border-[#f87171]/40 disabled:opacity-40"
                >
                  Disable 2FA
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

