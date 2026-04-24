import type { HTMLAttributes, ReactNode } from 'react'

type Tone = 'neutral' | 'accent' | 'danger' | 'warning' | 'muted'

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone
  dot?: boolean
  children: ReactNode
}

const tones: Record<Tone, string> = {
  neutral: 'bg-[#161b22] border border-[#21262d] text-[#e6edf3]',
  accent:  'bg-[#00FFA7]/10 border border-[#00FFA7]/30 text-[#00FFA7]',
  danger:  'bg-[#3a1515]/40 border border-[#5a2020]/60 text-[#f87171]',
  warning: 'bg-[#3a2c0a]/40 border border-[#5a4520]/60 text-[#f59e0b]',
  muted:   'bg-[#0f1520] border border-[#1e2a3a] text-[#5a6b7f]',
}

const dotColor: Record<Tone, string> = {
  neutral: 'bg-[#667085]',
  accent:  'bg-[#00FFA7]',
  danger:  'bg-[#ef4444]',
  warning: 'bg-[#f59e0b]',
  muted:   'bg-[#3d4f65]',
}

export function Badge({ tone = 'neutral', dot = false, className = '', children, ...rest }: BadgeProps) {
  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium',
        tones[tone],
        className,
      ].join(' ')}
      {...rest}
    >
      {dot && <span aria-hidden className={`w-1.5 h-1.5 rounded-full ${dotColor[tone]}`} />}
      {children}
    </span>
  )
}
