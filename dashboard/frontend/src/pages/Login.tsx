import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { MeshBackground } from '../components/ui'

export default function Login() {
  const { t } = useTranslation()
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (!username.trim() || !password) {
      setError('Username and password are required')
      return
    }
    setSubmitting(true)
    try {
      await login(username.trim(), password)
    } catch (ex: unknown) {
      setError(ex instanceof Error ? ex.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  const inp = "w-full px-4 py-3 rounded-lg bg-[#0f1520] border border-[#1e2a3a] text-[#e2e8f0] placeholder-[#3d4f65] text-sm transition-colors duration-200 focus:outline-none focus:border-[#00FFA7]/60 focus:ring-1 focus:ring-[#00FFA7]/20"
  const lbl = "block text-[11px] font-semibold text-[#5a6b7f] mb-1.5 tracking-[0.08em] uppercase"

  return (
    <div className="min-h-screen bg-[#080c14] flex items-center justify-center px-4 font-[Inter,-apple-system,sans-serif] relative">
      <MeshBackground />

      <div className="w-full max-w-[380px] relative z-10">
        <div className="rounded-xl border border-[#152030] bg-[#0b1018] shadow-[0_4px_40px_rgba(0,0,0,0.4)]">

          {/* Header */}
          <div className="px-7 pt-7 pb-5 border-b border-[#152030]">
            <div className="flex flex-col items-center gap-3">
              <img src="/EVO_NEXUS.webp" alt="EvoNexus" className="h-8 w-auto" />
              <p className="text-[11px] text-[#4a5a6e]">{t('login.subtitle')}</p>
            </div>
          </div>

          {/* Form */}
          <div className="px-7 py-6">
            {error && (
              <div className="mb-4 px-3 py-2.5 rounded-lg bg-[#1a0a0a] border border-[#3a1515] text-[#f87171] text-xs">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className={lbl}>{t('login.username')}</label>
                <input type="text" value={username} onChange={e => setUsername(e.target.value)}
                  className={inp} placeholder={t('login.username')} autoFocus autoComplete="username" />
              </div>
              <div>
                <label className={lbl}>{t('login.password')}</label>
                <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                  className={inp} placeholder={t('login.password')} autoComplete="current-password" />
              </div>

              <button type="submit" disabled={submitting}
                className={`w-full py-3 mt-1 rounded-lg text-sm font-semibold transition-colors disabled:opacity-40 ${
                  submitting
                    ? 'bg-[#00FFA7]/60 text-[#080c14]'
                    : 'bg-[#00FFA7] text-[#080c14] hover:bg-[#00e69a] active:bg-[#00cc88]'
                }`}>
                {submitting ? t('login.signingIn') : t('login.submit')}
              </button>
            </form>
          </div>
        </div>

        <p className="text-center mt-4 text-[10px] text-[#2d3d4f]">
          <a href="https://evolutionfoundation.com.br" target="_blank" rel="noopener noreferrer"
            className="hover:text-[#4a5a6e] transition-colors">
            Evolution Foundation
          </a>
        </p>
      </div>
    </div>
  )
}
