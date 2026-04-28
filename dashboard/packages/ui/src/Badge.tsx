import { type HTMLAttributes, type ReactNode } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

export type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info'

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant
  children: ReactNode
}

// ─── Style maps ───────────────────────────────────────────────────────────────

const BADGE_STYLES: Record<BadgeVariant, React.CSSProperties> = {
  default: {
    background: 'rgba(255,255,255,0.07)',
    color: 'rgba(255,255,255,0.65)',
    border: '1px solid rgba(255,255,255,0.1)',
  },
  success: {
    background: 'rgba(0,255,167,0.1)',
    color: '#00FFA7',
    border: '1px solid rgba(0,255,167,0.25)',
  },
  warning: {
    background: 'rgba(245,158,11,0.12)',
    color: '#f59e0b',
    border: '1px solid rgba(245,158,11,0.3)',
  },
  danger: {
    background: 'rgba(239,68,68,0.12)',
    color: '#f87171',
    border: '1px solid rgba(239,68,68,0.3)',
  },
  info: {
    background: 'rgba(59,130,246,0.12)',
    color: '#60a5fa',
    border: '1px solid rgba(59,130,246,0.3)',
  },
}

// ─── Component ────────────────────────────────────────────────────────────────

export function Badge({ variant = 'default', children, style, ...rest }: BadgeProps) {
  return (
    <span
      {...rest}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 500,
        lineHeight: 1.6,
        ...BADGE_STYLES[variant],
        ...style,
      }}
    >
      {children}
    </span>
  )
}
