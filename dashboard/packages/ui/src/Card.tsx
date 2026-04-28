import { type HTMLAttributes, type ReactNode } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  padding?: number | string
}

export interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
}

export interface CardBodyProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
}

// ─── Components ───────────────────────────────────────────────────────────────

export function Card({ children, padding = 20, style, ...rest }: CardProps) {
  return (
    <div
      {...rest}
      style={{
        background: 'var(--bg-card, #182230)',
        border: '1px solid var(--border, #344054)',
        borderRadius: 8,
        padding,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export function CardHeader({ children, style, ...rest }: CardHeaderProps) {
  return (
    <div
      {...rest}
      style={{
        marginBottom: 16,
        paddingBottom: 12,
        borderBottom: '1px solid var(--border, #344054)',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export function CardBody({ children, style, ...rest }: CardBodyProps) {
  return (
    <div {...rest} style={{ ...style }}>
      {children}
    </div>
  )
}
