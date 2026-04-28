import { type InputHTMLAttributes } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CheckboxProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

// ─── Component ────────────────────────────────────────────────────────────────

export function Checkbox({ label, error, style, id, ...rest }: CheckboxProps) {
  const inputId = id ?? `checkbox-${Math.random().toString(36).slice(2)}`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label
        htmlFor={inputId}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          cursor: rest.disabled ? 'not-allowed' : 'pointer',
          opacity: rest.disabled ? 0.5 : 1,
        }}
      >
        <input
          {...rest}
          id={inputId}
          type="checkbox"
          style={{
            width: 15,
            height: 15,
            accentColor: 'var(--evo-green, #00FFA7)',
            cursor: 'inherit',
            flexShrink: 0,
            ...style,
          }}
        />
        {label && (
          <span
            style={{
              fontSize: 13,
              color: 'var(--text-primary, #F9FAFB)',
            }}
          >
            {label}
          </span>
        )}
      </label>
      {error && (
        <span style={{ fontSize: 11, color: '#ef4444', paddingLeft: 23 }}>
          {error}
        </span>
      )}
    </div>
  )
}
