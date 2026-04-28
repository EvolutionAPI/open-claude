// ─── Primitives ───────────────────────────────────────────────────────────────
export { Button } from './Button.js'
export type { ButtonProps, ButtonVariant, ButtonSize } from './Button.js'

export { Card, CardHeader, CardBody } from './Card.js'
export type { CardProps, CardHeaderProps, CardBodyProps } from './Card.js'

export { Badge } from './Badge.js'
export type { BadgeProps, BadgeVariant } from './Badge.js'

export { Input, FormField, INPUT_BASE, INPUT_ERROR } from './Input.js'
export type { InputProps } from './Input.js'

export { Select } from './Select.js'
export type { SelectProps, SelectOption } from './Select.js'

export { Checkbox } from './Checkbox.js'
export type { CheckboxProps } from './Checkbox.js'

export { Modal } from './Modal.js'
export type { ModalProps } from './Modal.js'

export { ToastProvider, useToast } from './Toast.js'
export type { ToastContextValue } from './Toast.js'

export { ErrorBoundary } from './ErrorBoundary.js'
export type { ErrorBoundaryProps } from './ErrorBoundary.js'

// ─── Schema-driven CRUD ───────────────────────────────────────────────────────
export { SchemaForm } from './SchemaForm.js'
export type {
  SchemaFormProps,
  JsonSchema,
  JsonSchemaProperty,
} from './SchemaForm.js'

export { SchemaTable } from './SchemaTable.js'
export type { SchemaTableProps, TableColumn, ColumnType } from './SchemaTable.js'

// ─── Reserved hook names (Step 2) ────────────────────────────────────────────
// usePluginNavigation is implemented in Step 2 (host renderer rewrite).
// Name reserved here to prevent collision.
// export { usePluginNavigation } from './navigation.js'
