import { type ButtonHTMLAttributes, type ReactNode } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'
export type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  children: ReactNode
}

// ─── Style maps ───────────────────────────────────────────────────────────────

const VARIANT_STYLES: Record<ButtonVariant, React.CSSProperties> = {
  primary: {
    background: '#00FFA7',
    color: '#000',
    border: 'none',
    fontWeight: 600,
  },
  secondary: {
    background: 'transparent',
    color: 'rgba(255,255,255,0.65)',
    border: '1px solid rgba(255,255,255,0.1)',
    fontWeight: 500,
  },
  danger: {
    background: 'rgba(239,68,68,0.12)',
    color: '#f87171',
    border: '1px solid rgba(239,68,68,0.3)',
    fontWeight: 500,
  },
  ghost: {
    background: 'transparent',
    color: 'rgba(255,255,255,0.55)',
    border: 'none',
    fontWeight: 400,
  },
}

const SIZE_STYLES: Record<ButtonSize, React.CSSProperties> = {
  sm: { padding: '5px 12px', fontSize: 12, borderRadius: 5 },
  md: { padding: '7px 16px', fontSize: 13, borderRadius: 6 },
  lg: { padding: '10px 20px', fontSize: 14, borderRadius: 7 },
}

// ─── Component ────────────────────────────────────────────────────────────────

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  children,
  style,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading

  return (
    <button
      {...rest}
      disabled={isDisabled}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        cursor: isDisabled ? 'not-allowed' : 'pointer',
        opacity: isDisabled ? 0.5 : 1,
        transition: 'opacity 140ms, background 140ms',
        lineHeight: 1,
        whiteSpace: 'nowrap',
        ...VARIANT_STYLES[variant],
        ...SIZE_STYLES[size],
        ...style,
      }}
    >
      {loading && (
        <span
          style={{
            display: 'inline-block',
            width: 12,
            height: 12,
            border: '2px solid currentColor',
            borderTopColor: 'transparent',
            borderRadius: '50%',
            animation: 'spin 0.6s linear infinite',
          }}
          aria-hidden="true"
        />
      )}
      {children}
    </button>
  )
}
