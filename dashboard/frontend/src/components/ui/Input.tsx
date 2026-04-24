import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  leftIcon?: ReactNode
  rightSlot?: ReactNode
  invalid?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { leftIcon, rightSlot, invalid = false, className = '', ...rest },
  ref,
) {
  const borderClass = invalid
    ? 'border-[#5a2020] focus:border-red-500/60 focus:ring-1 focus:ring-red-500/20'
    : 'border-[#1e2a3a] focus:border-[#00FFA7]/60 focus:ring-1 focus:ring-[#00FFA7]/20'

  if (!leftIcon && !rightSlot) {
    return (
      <input
        ref={ref}
        className={[
          'w-full px-4 py-3 rounded-lg bg-[#0f1520] border text-[#e2e8f0] placeholder-[#3d4f65]',
          'text-sm transition-colors duration-200 focus:outline-none',
          borderClass,
          className,
        ].join(' ')}
        {...rest}
      />
    )
  }

  return (
    <div
      className={[
        'flex items-center gap-2 px-3 rounded-lg bg-[#0f1520] border transition-colors duration-200',
        'focus-within:ring-1',
        invalid
          ? 'border-[#5a2020] focus-within:border-red-500/60 focus-within:ring-red-500/20'
          : 'border-[#1e2a3a] focus-within:border-[#00FFA7]/60 focus-within:ring-[#00FFA7]/20',
        className,
      ].join(' ')}
    >
      {leftIcon && <span className="text-[#5a6b7f] flex-shrink-0">{leftIcon}</span>}
      <input
        ref={ref}
        className="flex-1 min-w-0 bg-transparent py-2.5 text-sm text-[#e2e8f0] placeholder-[#3d4f65] focus:outline-none"
        {...rest}
      />
      {rightSlot && <span className="flex-shrink-0">{rightSlot}</span>}
    </div>
  )
})
