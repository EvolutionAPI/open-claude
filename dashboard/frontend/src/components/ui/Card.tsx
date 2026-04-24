import type { HTMLAttributes, ReactNode } from 'react'

type Variant = 'premium' | 'default' | 'flat'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: Variant
  interactive?: boolean
  accent?: boolean
  children: ReactNode
}

const base: Record<Variant, string> = {
  premium:
    'rounded-xl border border-[#152030] bg-[#0b1018] shadow-[0_4px_40px_rgba(0,0,0,0.4)]',
  default:
    'rounded-2xl border border-[#21262d] bg-[#161b22]',
  flat:
    'rounded-xl border border-[#1e2a3a] bg-[#0f1520]',
}

export function Card({
  variant = 'default',
  interactive = false,
  accent = false,
  className = '',
  children,
  ...rest
}: CardProps) {
  const interactiveClasses = interactive
    ? 'transition-all duration-300 hover:border-[#00FFA7]/40 hover:shadow-[0_0_24px_rgba(0,255,167,0.06)]'
    : ''

  return (
    <div className={`relative ${base[variant]} ${interactiveClasses} ${className}`} {...rest}>
      {accent && (
        <span
          aria-hidden
          className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#00FFA7]/30 to-transparent rounded-t-2xl"
        />
      )}
      {children}
    </div>
  )
}
