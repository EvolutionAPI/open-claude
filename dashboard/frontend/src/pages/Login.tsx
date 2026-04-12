import { useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { User, KeyRound, LogIn } from 'lucide-react'

export default function Login() {
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

  const inputClass = "w-full pl-11 pr-4 py-3 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white placeholder-[#4a5568] focus:outline-none focus:border-[#00FFA7]/50 focus:bg-white/[0.05] focus:shadow-[0_0_20px_rgba(0,255,167,0.08)] transition-all duration-300 text-sm backdrop-blur-sm"

  return (
    <div className="min-h-screen flex items-center justify-center px-4 font-[Inter] relative">
      {/* Animated background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute inset-0 bg-[#060a13]" />
        <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] rounded-full bg-[#00FFA7]/[0.07] blur-[120px] animate-[float_20s_ease-in-out_infinite]" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[500px] h-[500px] rounded-full bg-[#00FFA7]/[0.05] blur-[100px] animate-[float_25s_ease-in-out_infinite_reverse]" />
        <div className="absolute top-[40%] right-[20%] w-[300px] h-[300px] rounded-full bg-[#0ea5e9]/[0.04] blur-[80px] animate-[float_18s_ease-in-out_infinite_2s]" />
        <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: 'linear-gradient(rgba(0,255,167,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(0,255,167,0.3) 1px, transparent 1px)', backgroundSize: '60px 60px' }} />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,#060a13_70%)]" />
      </div>

      <style>{`
        @keyframes float {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(30px, -20px) scale(1.05); }
          66% { transform: translate(-20px, 15px) scale(0.95); }
        }
        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .fade-up { animation: fadeInUp 0.6s ease-out; }
      `}</style>

      <div className="w-full max-w-[400px] relative z-10">
        <div className="fade-up relative rounded-2xl border border-white/[0.08] bg-[#0c1220]/80 backdrop-blur-xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] overflow-hidden">
          {/* Top glow line */}
          <div className="absolute top-0 left-[10%] right-[10%] h-[1px] bg-gradient-to-r from-transparent via-[#00FFA7]/40 to-transparent" />

          <div className="p-8">
            {/* Logo */}
            <div className="text-center mb-8">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-[#00FFA7]/[0.08] border border-[#00FFA7]/20 mb-4 shadow-[0_0_30px_rgba(0,255,167,0.1)]">
                <LogIn size={24} className="text-[#00FFA7]" />
              </div>
              <h1 className="text-[28px] font-bold tracking-tight">
                <span className="text-[#00FFA7]">Evo</span>
                <span className="text-white">Nexus</span>
              </h1>
              <p className="text-[#667085] text-sm mt-1.5">Sign in to your workspace</p>
            </div>

            {error && (
              <div className="mb-5 px-4 py-3 rounded-xl bg-red-500/[0.08] border border-red-500/20 text-red-400 text-sm flex items-center gap-2 backdrop-blur-sm">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-[#8896ab] mb-2 uppercase tracking-wider">Username</label>
                <div className="relative">
                  <User size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#4a5568]" />
                  <input type="text" value={username} onChange={(e) => setUsername(e.target.value)}
                    className={inputClass} placeholder="Username" autoFocus />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-[#8896ab] mb-2 uppercase tracking-wider">Password</label>
                <div className="relative">
                  <KeyRound size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#4a5568]" />
                  <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                    className={inputClass} placeholder="Password" />
                </div>
              </div>

              <button type="submit" disabled={submitting}
                className="w-full py-3 rounded-xl bg-gradient-to-r from-[#00FFA7] to-[#00d48f] text-[#0a0f1a] font-semibold text-sm hover:shadow-[0_0_30px_rgba(0,255,167,0.25)] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed mt-3 flex items-center justify-center gap-2">
                {submitting ? (
                  <>
                    <div className="w-4 h-4 border-2 border-[#0a0f1a]/30 border-t-[#0a0f1a] rounded-full animate-spin" />
                    Signing in...
                  </>
                ) : (
                  'Sign In'
                )}
              </button>
            </form>
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
