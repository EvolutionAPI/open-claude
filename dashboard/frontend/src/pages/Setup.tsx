import { useState, useEffect, useRef, useCallback, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { api } from '../lib/api'

/* ── Animated mesh background ── */
function NetworkCanvas() {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId: number
    let particles: { x: number; y: number; vx: number; vy: number }[] = []

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }

    const init = () => {
      resize()
      const count = Math.floor((canvas.width * canvas.height) / 18000)
      particles = Array.from({ length: Math.min(count, 80) }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
      }))
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      const maxDist = 150

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i]
        p.x += p.vx
        p.y += p.vy
        if (p.x < 0 || p.x > canvas.width) p.vx *= -1
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1

        // Node
        ctx.beginPath()
        ctx.arc(p.x, p.y, 1.5, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(0, 255, 167, 0.25)'
        ctx.fill()

        // Edges
        for (let j = i + 1; j < particles.length; j++) {
          const q = particles[j]
          const dx = p.x - q.x
          const dy = p.y - q.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < maxDist) {
            ctx.beginPath()
            ctx.moveTo(p.x, p.y)
            ctx.lineTo(q.x, q.y)
            ctx.strokeStyle = `rgba(0, 255, 167, ${0.06 * (1 - dist / maxDist)})`
            ctx.lineWidth = 0.5
            ctx.stroke()
          }
        }
      }
      animId = requestAnimationFrame(draw)
    }

    init()
    draw()
    window.addEventListener('resize', init)
    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', init)
    }
  }, [])

  return <canvas ref={ref} className="fixed inset-0 pointer-events-none" style={{ zIndex: 0 }} />
}

/* ── Main ── */
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

  useEffect(() => {
    api.get('/config/workspace-status').then((data: { configured: boolean }) => {
      setHasConfig(data.configured)
    }).catch(() => setHasConfig(false))
  }, [])

  useEffect(() => {
    if (hasConfig === true) setCurrentStep(2)
  }, [hasConfig])

  const handleStep1 = useCallback((e: FormEvent) => {
    e.preventDefault()
    if (!ownerName.trim()) { setError('Name is required'); return }
    setError('')
    setDisplayName(ownerName)
    setCurrentStep(2)
  }, [ownerName])

  const handleStep2 = useCallback(async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (!username.trim()) { setError('Username is required'); return }
    if (password.length < 6) { setError('Password must be at least 6 characters'); return }
    if (password !== confirmPassword) { setError('Passwords do not match'); return }

    setSubmitting(true)
    try {
      let geo = {}
      try {
        const r = await fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout(5000) })
        if (r.ok) { const d = await r.json(); geo = { country: d.country_name, country_code: d.country_code, city: d.city, region: d.region, lat: d.latitude, lng: d.longitude, timezone: d.timezone } }
      } catch { /* optional */ }

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
  }, [hasConfig, currentStep, ownerName, companyName, timezone, language, username, email, displayName, password, confirmPassword, refreshUser])

  if (hasConfig === null) return (
    <div className="min-h-screen bg-[#080c14] flex items-center justify-center">
      <div className="w-5 h-5 border-2 border-[#00FFA7]/20 border-t-[#00FFA7] rounded-full animate-spin" />
    </div>
  )

  const inp = "w-full px-4 py-3 rounded-lg bg-[#0f1520] border border-[#1e2a3a] text-[#e2e8f0] placeholder-[#3d4f65] text-sm transition-colors duration-200 focus:outline-none focus:border-[#00FFA7]/60 focus:ring-1 focus:ring-[#00FFA7]/20"
  const lbl = "block text-[11px] font-semibold text-[#5a6b7f] mb-1.5 tracking-[0.08em] uppercase"

  return (
    <div className="min-h-screen bg-[#080c14] flex items-center justify-center px-4 py-8 font-[Inter,-apple-system,sans-serif] relative">
      <NetworkCanvas />

      <div className="w-full max-w-[420px] relative z-10">
        {/* ── Card ── */}
        <div className="rounded-xl border border-[#152030] bg-[#0b1018] shadow-[0_4px_40px_rgba(0,0,0,0.4)]">

          {/* Header */}
          <div className="px-7 pt-7 pb-5 border-b border-[#152030]">
            <div className="flex items-center gap-3 mb-4">
              {/* Logo mark */}
              <div className="w-9 h-9 rounded-lg bg-[#00FFA7]/10 flex items-center justify-center">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <path d="M12 2L2 7l10 5 10-5-10-5z" fill="#00FFA7" opacity="0.8"/>
                  <path d="M2 17l10 5 10-5" stroke="#00FFA7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.5"/>
                  <path d="M2 12l10 5 10-5" stroke="#00FFA7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.7"/>
                </svg>
              </div>
              <div>
                <h1 className="text-lg font-bold text-white tracking-tight leading-none">
                  <span className="text-[#00FFA7]">Evo</span>Nexus
                </h1>
                <p className="text-[11px] text-[#4a5a6e] mt-0.5">AI Workspace Platform</p>
              </div>
            </div>

            {/* Step nav */}
            {!hasConfig && (
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => currentStep > 1 && setCurrentStep(1)}
                  className={`flex-1 py-1.5 text-[11px] font-medium rounded-md transition-colors ${
                    currentStep === 1
                      ? 'bg-[#00FFA7]/10 text-[#00FFA7]'
                      : 'text-[#4a5a6e] hover:text-[#7a8a9e]'
                  }`}
                >
                  Workspace
                </button>
                <button
                  type="button"
                  className={`flex-1 py-1.5 text-[11px] font-medium rounded-md transition-colors ${
                    currentStep === 2
                      ? 'bg-[#00FFA7]/10 text-[#00FFA7]'
                      : 'text-[#4a5a6e]'
                  }`}
                  disabled
                >
                  Account
                </button>
              </div>
            )}
          </div>

          {/* Form */}
          <div className="px-7 py-6">
            {error && (
              <div className="mb-4 px-3 py-2.5 rounded-lg bg-[#1a0a0a] border border-[#3a1515] text-[#f87171] text-xs">
                {error}
              </div>
            )}

            {/* Step 1 */}
            {currentStep === 1 && !hasConfig && (
              <form onSubmit={handleStep1} className="space-y-4">
                <div>
                  <label className={lbl}>Your name</label>
                  <input type="text" value={ownerName} onChange={e => setOwnerName(e.target.value)}
                    className={inp} placeholder="Full name" autoFocus autoComplete="name" />
                </div>
                <div>
                  <label className={lbl}>Company</label>
                  <input type="text" value={companyName} onChange={e => setCompanyName(e.target.value)}
                    className={inp} placeholder="Organization name" autoComplete="organization" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={lbl}>Timezone</label>
                    <input type="text" value={timezone} onChange={e => setTimezone(e.target.value)}
                      className={inp} />
                  </div>
                  <div>
                    <label className={lbl}>Language</label>
                    <select value={language} onChange={e => setLanguage(e.target.value)}
                      className={inp + ' appearance-none cursor-pointer'}>
                      <option value="en">English</option>
                      <option value="pt-BR">Portugues (BR)</option>
                      <option value="es">Espanol</option>
                    </select>
                  </div>
                </div>

                <button type="submit"
                  className="w-full py-3 mt-2 rounded-lg bg-[#00FFA7] text-[#080c14] text-sm font-semibold hover:bg-[#00e69a] active:bg-[#00cc88] transition-colors">
                  Continue
                </button>
              </form>
            )}

            {/* Step 2 */}
            {currentStep === 2 && (
              <form onSubmit={handleStep2} className="space-y-4">
                {hasConfig && (
                  <p className="text-[#5a6b7f] text-xs mb-2">Create your administrator account to get started.</p>
                )}
                <div>
                  <label className={lbl}>Username</label>
                  <input type="text" value={username} onChange={e => setUsername(e.target.value)}
                    className={inp} placeholder="admin" autoFocus autoComplete="username" />
                </div>
                <div>
                  <label className={lbl}>Email</label>
                  <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                    className={inp} placeholder="you@company.com" autoComplete="email" />
                </div>
                <div>
                  <label className={lbl}>Display name</label>
                  <input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)}
                    className={inp} placeholder={ownerName || 'Your name'} autoComplete="name" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={lbl}>Password</label>
                    <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                      className={inp} placeholder="Min 6 chars" autoComplete="new-password" />
                  </div>
                  <div>
                    <label className={lbl}>Confirm</label>
                    <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                      className={inp} placeholder="Repeat" autoComplete="new-password" />
                  </div>
                </div>

                <div className={`flex gap-2.5 mt-2 ${hasConfig ? '' : ''}`}>
                  {!hasConfig && (
                    <button type="button" onClick={() => setCurrentStep(1)}
                      className="px-5 py-3 rounded-lg text-[#5a6b7f] text-sm font-medium border border-[#1e2a3a] hover:border-[#2e3a4a] hover:text-[#8a9aae] transition-colors">
                      Back
                    </button>
                  )}
                  <button type="submit" disabled={submitting}
                    className={`flex-1 py-3 rounded-lg text-sm font-semibold transition-colors disabled:opacity-40 ${
                      submitting
                        ? 'bg-[#00FFA7]/60 text-[#080c14]'
                        : 'bg-[#00FFA7] text-[#080c14] hover:bg-[#00e69a] active:bg-[#00cc88]'
                    }`}>
                    {submitting ? 'Creating...' : 'Create account'}
                  </button>
                </div>
              </form>
            )}
          </div>

          {/* Footer stats */}
          <div className="px-7 py-3.5 border-t border-[#152030] flex items-center justify-between">
            <div className="flex gap-4 text-[10px] text-[#3d4f65] font-medium tracking-wide uppercase">
              <span>38 Agents</span>
              <span>137 Skills</span>
              <span>Multi-AI</span>
            </div>
            <div className="w-1.5 h-1.5 rounded-full bg-[#00FFA7]/40" />
          </div>
        </div>

        {/* Attribution */}
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
