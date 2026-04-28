import { useState, useCallback, type FormEvent } from 'react'
import Ajv from 'ajv'
import addFormats from 'ajv-formats'
import { Button } from './Button.js'
import { Input, FormField } from './Input.js'
import { Select, type SelectOption } from './Select.js'
import { Checkbox } from './Checkbox.js'

// ─── Ajv instance (bundled) ───────────────────────────────────────────────────
//
// strict: false silences "unknown format" warnings that flip into thrown
// errors at compile time on Ajv 8. addFormats then registers the standard
// JSON-Schema formats (date, date-time, email, uri, uuid, …) so plugin
// schemas declaring `format: "date"` validate correctly AND let SchemaForm
// render the matching native input type.

const ajv = new Ajv({ allErrors: true, coerceTypes: false, strict: false })
addFormats(ajv)

// ─── JSON Schema types ────────────────────────────────────────────────────────

export interface JsonSchemaProperty {
  type?: 'string' | 'number' | 'integer' | 'boolean'
  title?: string
  description?: string
  enum?: string[]
  format?: string
  minLength?: number
  maxLength?: number
  minimum?: number
  maximum?: number
  default?: unknown
}

export interface JsonSchema {
  type: 'object'
  properties: Record<string, JsonSchemaProperty>
  required?: string[]
  title?: string
  description?: string
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SchemaFormProps {
  schema: JsonSchema
  initialValues?: Record<string, unknown>
  onSubmit: (values: Record<string, unknown>) => void | Promise<void>
  loading?: boolean
  submitLabel?: string
  onCancel?: () => void
  cancelLabel?: string
}

// ─── Widget resolution ────────────────────────────────────────────────────────

type WidgetType = 'string' | 'number' | 'boolean' | 'enum' | 'date'

function resolveWidget(prop: JsonSchemaProperty): WidgetType {
  if (prop.enum && prop.enum.length > 0) return 'enum'
  if (prop.type === 'boolean') return 'boolean'
  if (prop.type === 'number' || prop.type === 'integer') return 'number'
  if (prop.type === 'string') {
    if (prop.format === 'date') return 'date'
    return 'string'
  }
  return 'string'
}

function defaultForWidget(widget: WidgetType): unknown {
  if (widget === 'boolean') return false
  return ''
}

// ─── Field renderer ───────────────────────────────────────────────────────────

function FieldRenderer({
  fieldKey,
  prop,
  value,
  error,
  required,
  onChange,
}: {
  fieldKey: string
  prop: JsonSchemaProperty
  value: unknown
  error?: string
  required: boolean
  onChange: (key: string, val: unknown) => void
}) {
  const widget = resolveWidget(prop)
  const label = prop.title ?? fieldKey
  const hint = prop.description

  if (widget === 'boolean') {
    return (
      <Checkbox
        id={`field-${fieldKey}`}
        label={label}
        checked={Boolean(value)}
        error={error}
        required={required}
        onChange={(e) => onChange(fieldKey, e.target.checked)}
      />
    )
  }

  if (widget === 'enum') {
    const options: SelectOption[] = (prop.enum ?? []).map((v) => ({
      value: v,
      label: v,
    }))
    return (
      <Select
        label={label}
        options={options}
        value={typeof value === 'string' ? value : ''}
        error={error}
        required={required}
        hint={hint}
        onChange={(e) => onChange(fieldKey, e.target.value)}
      />
    )
  }

  if (widget === 'date') {
    return (
      <Input
        type="date"
        label={label}
        value={typeof value === 'string' ? value : ''}
        error={error}
        required={required}
        hint={hint}
        onChange={(e) => onChange(fieldKey, e.target.value)}
      />
    )
  }

  if (widget === 'number') {
    return (
      <Input
        type="number"
        label={label}
        value={typeof value === 'number' ? String(value) : ''}
        error={error}
        required={required}
        hint={hint}
        min={prop.minimum}
        max={prop.maximum}
        onChange={(e) =>
          onChange(fieldKey, e.target.value === '' ? '' : Number(e.target.value))
        }
      />
    )
  }

  return (
    <Input
      type="text"
      label={label}
      value={typeof value === 'string' ? value : ''}
      error={error}
      required={required}
      hint={hint}
      minLength={prop.minLength}
      maxLength={prop.maxLength}
      onChange={(e) => onChange(fieldKey, e.target.value)}
    />
  )
}

// ─── SchemaForm ───────────────────────────────────────────────────────────────

export function SchemaForm({
  schema,
  initialValues = {},
  onSubmit,
  loading = false,
  submitLabel = 'Save',
  onCancel,
  cancelLabel = 'Cancel',
}: SchemaFormProps) {
  const buildInitial = useCallback(() => {
    const init: Record<string, unknown> = {}
    for (const [key, prop] of Object.entries(schema.properties)) {
      init[key] =
        key in initialValues
          ? initialValues[key]
          : (prop.default ?? defaultForWidget(resolveWidget(prop)))
    }
    return init
  }, [schema, initialValues])

  const [values, setValues] = useState<Record<string, unknown>>(buildInitial)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)

  const handleChange = useCallback((key: string, val: unknown) => {
    setValues((prev) => ({ ...prev, [key]: val }))
    setErrors((prev) => {
      if (!prev[key]) return prev
      const next = { ...prev }
      delete next[key]
      return next
    })
  }, [])

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()

      const validate = ajv.compile(schema)
      const valid = validate(values)

      if (!valid && validate.errors) {
        const fieldErrors: Record<string, string> = {}
        for (const err of validate.errors) {
          const field =
            err.instancePath.replace(/^\//, '') ||
            (err.params as Record<string, string>).missingProperty ||
            '_form'
          fieldErrors[field] = err.message ?? 'Invalid value'
        }
        setErrors(fieldErrors)
        return
      }

      setErrors({})
      setSubmitting(true)
      try {
        await onSubmit(values)
      } finally {
        setSubmitting(false)
      }
    },
    [schema, values, onSubmit],
  )

  const isLoading = loading || submitting
  const required = new Set(schema.required ?? [])

  return (
    <form onSubmit={handleSubmit} noValidate>
      {schema.title && (
        <h3
          style={{
            margin: '0 0 16px',
            fontSize: 15,
            fontWeight: 600,
            color: 'var(--text-primary, #F9FAFB)',
          }}
        >
          {schema.title}
        </h3>
      )}

      {errors['_form'] && (
        <FormField error={errors['_form']}>{null}</FormField>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {Object.entries(schema.properties).map(([key, prop]) => (
          <FieldRenderer
            key={key}
            fieldKey={key}
            prop={prop}
            value={values[key]}
            error={errors[key]}
            required={required.has(key)}
            onChange={handleChange}
          />
        ))}
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 8,
          marginTop: 20,
        }}
      >
        {onCancel && (
          <Button
            type="button"
            variant="secondary"
            onClick={onCancel}
            disabled={isLoading}
          >
            {cancelLabel}
          </Button>
        )}
        <Button type="submit" variant="primary" loading={isLoading}>
          {submitLabel}
        </Button>
      </div>
    </form>
  )
}
