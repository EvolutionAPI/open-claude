import { useState, useEffect, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { api } from '../lib/api'
import { User, Building2, Globe, Languages, KeyRound, Mail, ArrowRight, ArrowLeft, Sparkles } from 'lucide-react'

function AnimatedBackground() {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none">
      {/* Base gradient */}
      <div className="absolute inset-0 bg-[#060a13]" />

      {/* Animated gradient orbs */}
      <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] rounded-full bg-[#00FFA7]/[0.07] blur-[120px] animate-[float_20s_ease-in-out_infinite]" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[500px] h-[500px] rounded-full bg-[#00FFA7]/[0.05] blur-[100px] animate-[float_25s_ease-in-out_infinite_reverse]" />
      <div className="absolute top-[40%] right-[20%] w-[300px] h-[300px] rounded-full bg-[#0ea5e9]/[0.04] blur-[80px] animate-[float_18s_ease-in-out_infinite_2s]" />

      {/* Grid pattern overlay */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `linear-gradient(rgba(0,255,167,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(0,255,167,0.3) 1px, transparent 1px)`,
          backgroundSize: '60px 60px',
        }}
      />

      {/* Radial vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,#060a13_70%)]" />
    </div>
  )
}

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-3 justify-center mt-5">
      {Array.from({ length: total }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className={`
            relative flex items-center justify-center w-8 h-8 rounded-full text-xs font-bold transition-all duration-500
            ${i + 1 <= current
              ? 'bg-[#00FFA7]/20 text-[#00FFA7] border border-[#00FFA7]/40 shadow-[0_0_15px_rgba(0,255,167,0.15)]'
              : 'bg-white/[0.03] text-[#667085] border border-white/[0.06]'
            }
          `}>
            {i + 1 < current ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            ) : (
              i + 1
            )}
            {i + 1 === current && (
              <div className="absolute inset-0 rounded-full border border-[#00FFA7]/30 animate-ping" />
            )}
          </div>
          {i < total - 1 && (
            <div className={`w-12 h-[2px] rounded-full transition-all duration-500 ${i + 1 < current ? 'bg-[#00FFA7]/40' : 'bg-white/[0.06]'}`} />
          )}
        </div>
      ))}
    </div>
  )
}

export default function Setup() {
  const { refreshUser } = useAuth()
  const [hasConfig, setHasConfig] = useState<boolean | null>(null)

  const [ownerName, setOwnerName] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [timezone, setTimezone] = useState('America/Sao_Paulo')
  const [language, setLanguage] = useState('en')

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [currentStep, setCurrentStep] = useState(1)
  const [slideDir, setSlideDir] = useState<'left' | 'right'>('left')

  useEffect(() => {
    api.get('/config/workspace-status').then((data: { configured: boolean }) => {
      setHasConfig(data.configured)
    }).catch(() => setHasConfig(false))
  }, [])

  useEffect(() => {
    if (hasConfig === true) setCurrentStep(2)
  }, [hasConfig])

  const goToStep = (step: number) => {
    setSlideDir(step > currentStep ? 'left' : 'right')
    setCurrentStep(step)
  }

  const handleStep1 = (e: FormEvent) => {
    e.preventDefault()
    if (!ownerName.trim()) { setError('Your name is required'); return }
    setError('')
    setDisplayName(ownerName)
    goToStep(2)
  }

  const handleStep2 = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (!username.trim()) { setError('Username is required'); return }
    if (password.length < 6) { setError('Password must be at least 6 characters'); return }
    if (password !== confirmPassword) { setError('Passwords do not match'); return }

    setSubmitting(true)
    try {
      let geo = {}
      try {
        const geoResp = await fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout(5000) })
        if (geoResp.ok) {
          const geoData = await geoResp.json()
          geo = { country: geoData.country_name, country_code: geoData.country_code, city: geoData.city, region: geoData.region, lat: geoData.latitude, lng: geoData.longitude, timezone: geoData.timezone }
        }
      } catch { /* geo is optional */ }

      await api.post('/auth/setup', {
        workspace: (hasConfig && currentStep === 2 && !ownerName.trim()) ? undefined : {
          owner_name: ownerName.trim(), company_name: companyName.trim(), timezone, language, agents: [], integrations: [], geo,
        },
        username: username.trim(),
        email: email.trim() || undefined,
        display_name: (displayName.trim() || ownerName.trim() || username.trim()),
        password,
      })
      await refreshUser()
      window.location.href = '/providers'
    } catch (ex: unknown) {
      setError(ex instanceof Error ? ex.message : 'Setup failed')
    } finally {
      setSubmitting(false)
    }
  }

  const inputClass = "w-full pl-11 pr-4 py-3 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white placeholder-[#4a5568] focus:outline-none focus:border-[#00FFA7]/50 focus:bg-white/[0.05] focus:shadow-[0_0_20px_rgba(0,255,167,0.08)] transition-all duration-300 text-sm backdrop-blur-sm"
  const labelClass = "block text-xs font-medium text-[#8896ab] mb-2 uppercase tracking-wider"

  if (hasConfig === null) return (
    <div className="min-h-screen bg-[#060a13] flex items-center justify-center">
      <div className="flex items-center gap-3">
        <div className="w-5 h-5 border-2 border-[#00FFA7]/30 border-t-[#00FFA7] rounded-full animate-spin" />
        <span className="text-[#667085] text-sm">Initializing...</span>
      </div>
    </div>
  )

  const totalSteps = hasConfig ? 1 : 2

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-8 font-[Inter] relative">
      <AnimatedBackground />

      {/* CSS animations */}
      <style>{`
        @keyframes float {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(30px, -20px) scale(1.05); }
          66% { transform: translate(-20px, 15px) scale(0.95); }
        }
        @keyframes slideInLeft {
          from { opacity: 0; transform: translateX(40px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes slideInRight {
          from { opacity: 0; transform: translateX(-40px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .slide-in { animation: ${slideDir === 'left' ? 'slideInLeft' : 'slideInRight'} 0.4s ease-out; }
        .fade-up { animation: fadeInUp 0.6s ease-out; }
      `}</style>

      <div className="w-full max-w-[440px] relative z-10">
        {/* Card */}
        <div className="fade-up relative rounded-2xl border border-white/[0.08] bg-[#0c1220]/80 backdrop-blur-xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] overflow-hidden">
          {/* Top glow line */}
          <div className="absolute top-0 left-[10%] right-[10%] h-[1px] bg-gradient-to-r from-transparent via-[#00FFA7]/40 to-transparent" />

          {/* Header */}
          <div className="px-8 pt-8 pb-2 text-center">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-[#00FFA7]/[0.08] border border-[#00FFA7]/20 mb-4 shadow-[0_0_30px_rgba(0,255,167,0.1)]">
              <Sparkles size={24} className="text-[#00FFA7]" />
            </div>
            <h1 className="text-[28px] font-bold tracking-tight">
              <span className="text-[#00FFA7]">Evo</span>
              <span className="text-white">Nexus</span>
            </h1>
            <p className="text-[#667085] text-sm mt-1.5">
              {currentStep === 1 ? 'Configure your workspace' : 'Create your admin account'}
            </p>
            {!hasConfig && <StepIndicator current={currentStep} total={2} />}
          </div>

          {/* Form body */}
          <div className="px-8 pb-8 pt-4">
            {error && (
              <div className="mb-5 px-4 py-3 rounded-xl bg-red-500/[0.08] border border-red-500/20 text-red-400 text-sm flex items-center gap-2 backdrop-blur-sm">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                {error}
              </div>
            )}

            {/* Step 1: Workspace */}
            {currentStep === 1 && !hasConfig && (
              <form onSubmit={handleStep1} className="space-y-4 slide-in" key="step1">
                <div>
                  <label className={labelClass}>Your Name *</label>
                  <div className="relative">
                    <User size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#4a5568]" />
                    <input type="text" value={ownerName} onChange={(e) => setOwnerName(e.target.value)}
                      className={inputClass} placeholder="John Doe" autoFocus />
                  </div>
                </div>
                <div>
                  <label className={labelClass}>Company</label>
                  <div className="relative">
                    <Building2 size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#4a5568]" />
                    <input type="text" value={companyName} onChange={(e) => setCompanyName(e.target.value)}
                      className={inputClass} placeholder="Acme Inc" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={labelClass}>Timezone</label>
                    <div className="relative">
                      <Globe size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#4a5568]" />
                      <input type="text" value={timezone} onChange={(e) => setTimezone(e.target.value)}
                        className={inputClass} placeholder="America/Sao_Paulo" />
                    </div>
                  </div>
                  <div>
                    <label className={labelClass}>Language</label>
                    <div className="relative">
                      <Languages size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#4a5568]" />
                      <select value={language} onChange={(e) => setLanguage(e.target.value)}
                        className={inputClass + ' appearance-none cursor-pointer'}>
                        <option value="en">English</option>
                        <option value="pt-BR">Portugues (BR)</option>
                        <option value="es">Espanol</option>
                      </select>
                    </div>
                  </div>
                </div>

                <button type="submit"
                  className="w-full py-3 rounded-xl bg-gradient-to-r from-[#00FFA7] to-[#00d48f] text-[#0a0f1a] font-semibold text-sm hover:shadow-[0_0_30px_rgba(0,255,167,0.25)] transition-all duration-300 mt-3 flex items-center justify-center gap-2 group">
                  Continue
                  <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                </button>
              </form>
            )}

            {/* Step 2: Admin Account */}
            {currentStep === 2 && (
              <form onSubmit={handleStep2} className="space-y-4 slide-in" key="step2">
                <div>
                  <label className={labelClass}>Username *</label>
                  <div className="relative">
                    <User size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#4a5568]" />
                    <input type="text" value={username} onChange={(e) => setUsername(e.target.value)}
                      className={inputClass} placeholder="admin" autoFocus />
                  </div>
                </div>
                <div>
                  <label className={labelClass}>Email</label>
                  <div className="relative">
                    <Mail size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#4a5568]" />
                    <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                      className={inputClass} placeholder="admin@example.com" />
                  </div>
                </div>
                <div>
                  <label className={labelClass}>Display Name</label>
                  <div className="relative">
                    <User size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#4a5568]" />
                    <input type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                      className={inputClass} placeholder={ownerName || 'Admin'} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={labelClass}>Password *</label>
                    <div className="relative">
                      <KeyRound size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#4a5568]" />
                      <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                        className={inputClass} placeholder="Min 6 chars" />
                    </div>
                  </div>
                  <div>
                    <label className={labelClass}>Confirm *</label>
                    <div className="relative">
                      <KeyRound size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#4a5568]" />
                      <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
                        className={inputClass} placeholder="Repeat" />
                    </div>
                  </div>
                </div>

                <div className={`flex gap-3 mt-3 ${hasConfig ? '' : 'pt-1'}`}>
                  {!hasConfig && (
                    <button type="button" onClick={() => goToStep(1)}
                      className="flex-1 py-3 rounded-xl text-[#8896ab] text-sm hover:text-white hover:bg-white/[0.04] border border-white/[0.08] transition-all duration-300 flex items-center justify-center gap-2 group">
                      <ArrowLeft size={16} className="group-hover:-translate-x-1 transition-transform" />
                      Back
                    </button>
                  )}
                  <button type="submit" disabled={submitting}
                    className={`${hasConfig ? 'w-full' : 'flex-1'} py-3 rounded-xl bg-gradient-to-r from-[#00FFA7] to-[#00d48f] text-[#0a0f1a] font-semibold text-sm hover:shadow-[0_0_30px_rgba(0,255,167,0.25)] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2`}>
                    {submitting ? (
                      <>
                        <div className="w-4 h-4 border-2 border-[#0a0f1a]/30 border-t-[#0a0f1a] rounded-full animate-spin" />
                        Setting up...
                      </>
                    ) : (
                      <>
                        Launch EvoNexus
                        <Sparkles size={16} />
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>

          {/* Bottom features bar */}
          <div className="px-8 py-4 border-t border-white/[0.05] bg-white/[0.01]">
            <div className="flex items-center justify-center gap-6 text-[11px] text-[#4a5568]">
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#00FFA7]/50" />
                {totalSteps === 2 ? '38 AI Agents' : 'Admin Setup'}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#00FFA7]/50" />
                137 Skills
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#00FFA7]/50" />
                Multi-Provider
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-5">
          <a href="https://evolutionfoundation.com.br" target="_blank" rel="noopener noreferrer"
            className="text-[#4a5568] text-xs hover:text-[#00FFA7] transition-colors duration-300">
            by <span className="font-medium text-[#00FFA7]/60 hover:text-[#00FFA7]">Evolution Foundation</span>
          </a>
        </div>
      </div>
    </div>
  )
}
