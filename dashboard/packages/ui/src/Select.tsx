import { type SelectHTMLAttributes } from 'react'
import { FormField, INPUT_BASE, INPUT_ERROR } from './Input.js'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SelectOption {
  value: string
  label: string
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  hint?: string
  options: SelectOption[]
  placeholder?: string
}

// ─── Component ────────────────────────────────────────────────────────────────

export function Select({
  label,
  error,
  hint,
  options,
  placeholder,
  style,
  ...rest
}: SelectProps) {
  const el = (
    <select
      {...rest}
      style={{
        ...INPUT_BASE,
        ...(error ? INPUT_ERROR : {}),
        appearance: 'none',
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23667085' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`,
        backgroundRepeat: 'no-repeat',
        backgroundPosition: 'right 10px center',
        paddingRight: 30,
        cursor: 'pointer',
        ...style,
      }}
    >
      {placeholder && (
        <option value="" disabled>
          {placeholder}
        </option>
      )}
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  )

  if (!label && !error && !hint) return el

  return (
    <FormField label={label} error={error} hint={hint} required={rest.required}>
      {el}
    </FormField>
  )
}
