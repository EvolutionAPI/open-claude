import type { LabelHTMLAttributes, ReactNode } from 'react'

interface LabelProps extends LabelHTMLAttributes<HTMLLabelElement> {
  children: ReactNode
}

export function Label({ className = '', children, ...rest }: LabelProps) {
  return (
    <label
      className={`block text-[11px] font-semibold text-[#5a6b7f] mb-1.5 tracking-[0.08em] uppercase ${className}`}
      {...rest}
    >
      {children}
    </label>
  )
}
