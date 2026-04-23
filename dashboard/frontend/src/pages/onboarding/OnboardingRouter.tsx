import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import Welcome from './Welcome'
import StepProvider from './StepProvider'
import StepBrainRepo from './StepBrainRepo'
import StepBrainConnect from './StepBrainConnect'
import StepBrainChoose from './StepBrainChoose'
import StepConfirm from './StepConfirm'
import RestoreFlow from './restore/RestoreFlow'

type Flow = 'first-time' | 'restore' | null

interface OnboardingState {
  onboarding_state: string
  onboarding_completed_agents_visit: boolean
  brain_repo_configured: boolean
  brain_repo: string | null
}

export default function OnboardingRouter() {
  const navigate = useNavigate()
  const [flow, setFlow] = useState<Flow>(null)
  const [step, setStep] = useState(0)
  const [patToken, setPatToken] = useState('')
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null)
  const [wantBrainRepo, setWantBrainRepo] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/onboarding/state')
      .then((data: OnboardingState) => {
        // If already completed or skipped, go to agents
        if (data.onboarding_state === 'completed' || data.onboarding_state === 'skipped') {
          navigate('/agents', { replace: true })
          return
        }
        if (data.onboarding_state === 'pending') {
          setFlow('first-time')
          setStep(1)
        }
      })
      .catch(() => {
        // No state yet — show welcome
      })
      .finally(() => setLoading(false))
  }, [navigate])

  const startFirstTime = async () => {
    try {
      await api.post('/onboarding/start')
    } catch {
      // ignore
    }
    setFlow('first-time')
    setStep(1)
  }

  const startRestore = () => {
    setFlow('restore')
    setStep(0)
  }

  const handleComplete = async () => {
    try {
      await api.post('/onboarding/complete')
    } catch {
      // ignore
    }
    navigate('/agents', { replace: true })
  }

  const handleSkip = async () => {
    try {
      await api.post('/onboarding/skip')
    } catch {
      // ignore
    }
    navigate('/agents', { replace: true })
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#080c14] flex items-center justify-center">
        <div className="text-[#5a6b7f] text-sm">Loading...</div>
      </div>
    )
  }

  // Welcome screen (no flow chosen yet)
  if (flow === null) {
    return <Welcome onFirstTime={startFirstTime} onRestore={startRestore} />
  }

  // Restore flow
  if (flow === 'restore') {
    return <RestoreFlow onComplete={handleComplete} onBack={() => setFlow(null)} />
  }

  // First-time flow steps
  if (step === 1) {
    return (
      <StepProvider
        onNext={(provider: string) => {
          setSelectedProvider(provider)
          setStep(2)
        }}
        onBack={() => setFlow(null)}
      />
    )
  }

  if (step === 2) {
    return (
      <StepBrainRepo
        onYes={() => {
          setWantBrainRepo(true)
          setStep(3)
        }}
        onNo={() => {
          setWantBrainRepo(false)
          setStep(5)
        }}
        onBack={() => setStep(1)}
      />
    )
  }

  if (step === 3) {
    return (
      <StepBrainConnect
        onNext={(token: string) => {
          setPatToken(token)
          setStep(4)
        }}
        onBack={() => setStep(2)}
      />
    )
  }

  if (step === 4) {
    return (
      <StepBrainChoose
        token={patToken}
        onNext={() => setStep(5)}
        onBack={() => setStep(3)}
      />
    )
  }

  if (step === 5) {
    return (
      <StepConfirm
        provider={selectedProvider}
        wantBrainRepo={wantBrainRepo}
        onComplete={handleComplete}
        onSkip={handleSkip}
        onBack={() => setStep(wantBrainRepo ? 4 : 2)}
      />
    )
  }

  return null
}
