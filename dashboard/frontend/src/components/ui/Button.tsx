import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  fullWidth?: boolean
  leftIcon?: ReactNode
  rightIcon?: ReactNode
  loading?: boolean
  children?: ReactNode
}

const variants: Record<Variant, string> = {
  primary:
    'bg-[#00FFA7] text-[#080c14] hover:bg-[#00e69a] active:bg-[#00cc88] focus-visible:ring-2 focus-visible:ring-[#00FFA7]/40',
  secondary:
    'bg-[#0f1520] border border-[#1e2a3a] text-[#e2e8f0] hover:border-[#2e3a4a] hover:bg-[#152030] focus-visible:ring-2 focus-visible:ring-[#00FFA7]/30',
  ghost:
    'text-[#5a6b7f] hover:text-[#e2e8f0] hover:bg-white/5 focus-visible:ring-2 focus-visible:ring-[#00FFA7]/30',
  danger:
    'bg-[#3a1515] border border-[#5a2020] text-[#f87171] hover:bg-[#4a1c1c] focus-visible:ring-2 focus-visible:ring-red-500/40',
}

const sizes: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2.5 text-sm',
  lg: 'px-5 py-3 text-sm',
}

export function Button({
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  leftIcon,
  rightIcon,
  loading = false,
  className = '',
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={[
        'inline-flex items-center justify-center gap-2 rounded-lg font-semibold',
        'transition-colors duration-200 disabled:opacity-40 disabled:cursor-not-allowed',
        'focus:outline-none focus-visible:ring-offset-1 focus-visible:ring-offset-[#080c14]',
        variants[variant],
        sizes[size],
        fullWidth ? 'w-full' : '',
        className,
      ].join(' ')}
      {...rest}
    >
      {loading ? (
        <span
          aria-hidden
          className="w-4 h-4 border-2 border-current/30 border-t-current rounded-full animate-spin"
        />
      ) : (
        leftIcon
      )}
      {children}
      {!loading && rightIcon}
    </button>
  )
}
