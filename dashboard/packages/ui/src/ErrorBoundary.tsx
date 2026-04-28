import { Component, type ErrorInfo, type ReactNode } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ErrorBoundaryProps {
  fallback?: ReactNode | ((error: Error, reset: () => void) => ReactNode)
  onError?: (error: Error, info: ErrorInfo) => void
  children: ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

// ─── Component ────────────────────────────────────────────────────────────────

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { error: null }
    this.reset = this.reset.bind(this)
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info)
  }

  reset() {
    this.setState({ error: null })
  }

  render() {
    const { error } = this.state
    const { fallback, children } = this.props

    if (error) {
      if (typeof fallback === 'function') {
        return fallback(error, this.reset)
      }
      if (fallback) {
        return fallback
      }
      return <DefaultErrorFallback error={error} reset={this.reset} />
    }

    return children
  }
}

// ─── Default fallback ─────────────────────────────────────────────────────────

function DefaultErrorFallback({
  error,
  reset,
}: {
  error: Error
  reset: () => void
}) {
  return (
    <div
      role="alert"
      style={{
        padding: 20,
        background: 'rgba(239,68,68,0.08)',
        border: '1px solid rgba(239,68,68,0.25)',
        borderRadius: 8,
        color: '#f87171',
      }}
    >
      <p style={{ margin: '0 0 8px', fontWeight: 600, fontSize: 14 }}>
        Something went wrong
      </p>
      <p
        style={{
          margin: '0 0 12px',
          fontSize: 12,
          color: 'rgba(255,255,255,0.5)',
          fontFamily: 'monospace',
          wordBreak: 'break-word',
        }}
      >
        {error.message}
      </p>
      <button
        onClick={reset}
        style={{
          padding: '5px 12px',
          background: 'rgba(239,68,68,0.15)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: 5,
          color: '#f87171',
          fontSize: 12,
          cursor: 'pointer',
        }}
      >
        Try again
      </button>
    </div>
  )
}
