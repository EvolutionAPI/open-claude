import { type InputHTMLAttributes, type ReactNode } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
  startAdornment?: ReactNode
  endAdornment?: ReactNode
}

// ─── Shared field styles ──────────────────────────────────────────────────────

export const INPUT_BASE: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid var(--border, #344054)',
  borderRadius: 6,
  color: 'var(--text-primary, #F9FAFB)',
  fontSize: 13,
  outline: 'none',
  transition: 'border-color 120ms',
  boxSizing: 'border-box',
}

export const INPUT_ERROR: React.CSSProperties = {
  borderColor: '#ef4444',
}

// ─── FormField wrapper ────────────────────────────────────────────────────────

export function FormField({
  label,
  error,
  hint,
  required,
  children,
}: {
  label?: string
  error?: string
  hint?: string
  required?: boolean
  children: ReactNode
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {label && (
        <label
          style={{
            fontSize: 12,
            fontWeight: 500,
            color: 'var(--text-secondary, #D0D5DD)',
          }}
        >
          {label}
          {required && (
            <span style={{ color: '#ef4444', marginLeft: 3 }}>*</span>
          )}
        </label>
      )}
      {children}
      {error && (
        <span style={{ fontSize: 11, color: '#ef4444' }}>{error}</span>
      )}
      {!error && hint && (
        <span style={{ fontSize: 11, color: 'var(--text-muted, #667085)' }}>
          {hint}
        </span>
      )}
    </div>
  )
}

// ─── Input component ──────────────────────────────────────────────────────────

export function Input({
  label,
  error,
  hint,
  startAdornment,
  endAdornment,
  style,
  ...rest
}: InputProps) {
  const hasAdornment = startAdornment || endAdornment

  const inputEl = (
    <input
      {...rest}
      style={{
        ...INPUT_BASE,
        ...(error ? INPUT_ERROR : {}),
        ...(hasAdornment ? { paddingLeft: startAdornment ? 32 : 10 } : {}),
        ...style,
      }}
    />
  )

  if (!label && !error && !hint && !hasAdornment) return inputEl

  return (
    <FormField label={label} error={error} hint={hint} required={rest.required}>
      {hasAdornment ? (
        <div style={{ position: 'relative' }}>
          {startAdornment && (
            <span
              style={{
                position: 'absolute',
                left: 10,
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--text-muted, #667085)',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              {startAdornment}
            </span>
          )}
          {inputEl}
          {endAdornment && (
            <span
              style={{
                position: 'absolute',
                right: 10,
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--text-muted, #667085)',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              {endAdornment}
            </span>
          )}
        </div>
      ) : (
        inputEl
      )}
    </FormField>
  )
}
