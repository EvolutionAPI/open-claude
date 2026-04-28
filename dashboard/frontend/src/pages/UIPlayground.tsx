/**
 * UI Playground — development-only page at /dev/ui-playground
 *
 * Demonstrates all @evonexus/ui primitives and schema-driven components.
 */
import { useState } from 'react'
import {
  Button,
  Card,
  CardHeader,
  CardBody,
  Badge,
  Input,
  Select,
  Checkbox,
  Modal,
  ErrorBoundary,
  SchemaForm,
  SchemaTable,
  type JsonSchema,
  type TableColumn,
} from '@evoapi/evonexus-ui'

// ─── Representative evo-essentials schema (PRD §6.6) ─────────────────────────

const EVO_ESSENTIALS_SCHEMA: JsonSchema = {
  type: 'object',
  title: 'Create Note',
  required: ['title', 'status'],
  properties: {
    title: {
      type: 'string',
      title: 'Title',
      description: 'Short title for this note',
      minLength: 1,
      maxLength: 120,
    },
    status: {
      type: 'string',
      title: 'Status',
      enum: ['draft', 'active', 'archived'],
    },
    priority: {
      type: 'string',
      title: 'Priority',
      enum: ['low', 'medium', 'high', 'urgent'],
    },
    due_date: {
      type: 'string',
      title: 'Due Date',
      format: 'date',
      description: 'Optional deadline',
    },
    score: {
      type: 'number',
      title: 'Score',
      minimum: 0,
      maximum: 100,
    },
    pinned: {
      type: 'boolean',
      title: 'Pinned',
      description: 'Pin this note to the top',
    },
  },
}

// ─── Mock table data ──────────────────────────────────────────────────────────

const TABLE_COLUMNS: TableColumn[] = [
  { key: 'title', label: 'Title', type: 'string', sortable: true },
  { key: 'status', label: 'Status', type: 'string', sortable: true },
  { key: 'priority', label: 'Priority', type: 'string', sortable: true },
  { key: 'due_date', label: 'Due Date', type: 'date', sortable: true },
  { key: 'score', label: 'Score', type: 'number', sortable: true },
  { key: 'pinned', label: 'Pinned', type: 'boolean' },
]

const TABLE_DATA = [
  {
    title: 'Set up evo-essentials plugin',
    status: 'active',
    priority: 'high',
    due_date: '2026-05-01',
    score: 92,
    pinned: true,
  },
  {
    title: 'Write plugin quickstart docs',
    status: 'draft',
    priority: 'medium',
    due_date: '2026-05-15',
    score: 0,
    pinned: false,
  },
  {
    title: 'Deploy to production',
    status: 'archived',
    priority: 'urgent',
    due_date: null,
    score: 100,
    pinned: false,
  },
]

// ─── Section wrapper ──────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 40 }}>
      <h2
        style={{
          margin: '0 0 16px',
          fontSize: 13,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          color: 'var(--text-muted)',
          paddingBottom: 8,
          borderBottom: '1px solid var(--border)',
        }}
      >
        {title}
      </h2>
      {children}
    </section>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function UIPlayground() {
  const [modalOpen, setModalOpen] = useState(false)
  const [checkboxValue, setCheckboxValue] = useState(false)
  const [selectValue, setSelectValue] = useState('')
  const [lastSubmit, setLastSubmit] = useState<string | null>(null)

  return (
    <div
      style={{
        maxWidth: 860,
        margin: '0 auto',
        padding: '32px 24px',
        color: 'var(--text-primary)',
      }}
    >
      {/* Tailwind preset smoke test — bg-evo-green = #00FFA7 from @theme in tokens.css */}
      <div className="bg-evo-green" style={{ width: 24, height: 4, borderRadius: 2, marginBottom: 16 }} />
      <h1 style={{ margin: '0 0 4px', fontSize: 22, fontWeight: 700 }}>
        @evonexus/ui Playground
      </h1>
      <p style={{ margin: '0 0 40px', color: 'var(--text-muted)', fontSize: 13 }}>
        Internal dev-only page. All primitives from packages/ui.
      </p>

      <Section title="Button">
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="danger">Danger</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="primary" loading>Loading</Button>
          <Button variant="primary" disabled>Disabled</Button>
          <Button variant="primary" size="sm">Small</Button>
          <Button variant="primary" size="lg">Large</Button>
        </div>
      </Section>

      <Section title="Badge">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Badge variant="default">Default</Badge>
          <Badge variant="success">Success</Badge>
          <Badge variant="warning">Warning</Badge>
          <Badge variant="danger">Danger</Badge>
          <Badge variant="info">Info</Badge>
        </div>
      </Section>

      <Section title="Card">
        <Card style={{ maxWidth: 360 }}>
          <CardHeader>
            <span style={{ fontWeight: 600 }}>Card Title</span>
          </CardHeader>
          <CardBody>
            <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 13 }}>
              Card body content goes here.
            </p>
          </CardBody>
        </Card>
      </Section>

      <Section title="Inputs">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 380 }}>
          <Input label="Text input" placeholder="Enter something..." />
          <Input label="With error" placeholder="Type..." error="This field is required" />
          <Input label="With hint" placeholder="YYYY-MM-DD" hint="Use ISO date format" />
          <Select
            label="Select"
            options={[
              { value: 'a', label: 'Option A' },
              { value: 'b', label: 'Option B' },
            ]}
            value={selectValue}
            placeholder="Choose..."
            onChange={(e) => setSelectValue(e.target.value)}
          />
          <Checkbox
            label="Enable pinning"
            checked={checkboxValue}
            onChange={(e) => setCheckboxValue(e.target.checked)}
          />
        </div>
      </Section>

      <Section title="Modal">
        <Button onClick={() => setModalOpen(true)}>Open Modal</Button>
        <Modal
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          title="Example Modal"
          description="This is the modal description."
          footer={
            <>
              <Button variant="secondary" onClick={() => setModalOpen(false)}>
                Cancel
              </Button>
              <Button onClick={() => setModalOpen(false)}>Confirm</Button>
            </>
          }
        >
          <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 13 }}>
            Modal body content. You can put any React node here.
          </p>
        </Modal>
      </Section>

      <Section title="ErrorBoundary">
        <ErrorBoundary>
          <Card style={{ maxWidth: 360 }}>
            <CardBody>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>
                This content is wrapped in an ErrorBoundary.
              </p>
            </CardBody>
          </Card>
        </ErrorBoundary>
      </Section>

      <Section title="SchemaForm (evo-essentials schema)">
        <Card style={{ maxWidth: 460 }}>
          <CardBody>
            <SchemaForm
              schema={EVO_ESSENTIALS_SCHEMA}
              submitLabel="Create Note"
              onCancel={() => setLastSubmit('cancelled')}
              onSubmit={(values) => {
                setLastSubmit(JSON.stringify(values, null, 2))
              }}
            />
          </CardBody>
        </Card>
        {lastSubmit && (
          <pre
            style={{
              marginTop: 16,
              padding: 12,
              background: '#161b22',
              borderRadius: 6,
              fontSize: 12,
              color: '#00FFA7',
              overflowX: 'auto',
              maxWidth: 460,
            }}
          >
            {lastSubmit}
          </pre>
        )}
      </Section>

      <Section title="SchemaTable">
        <Card>
          <CardBody style={{ padding: 0 }}>
            <SchemaTable
              columns={TABLE_COLUMNS}
              data={TABLE_DATA}
              emptyMessage="No notes yet."
            />
          </CardBody>
        </Card>
      </Section>
    </div>
  )
}
