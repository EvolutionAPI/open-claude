import { useState, type ReactNode } from 'react'
import { ChevronDown, ChevronUp, ChevronsUpDown } from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

export type ColumnType = 'string' | 'number' | 'boolean' | 'date' | 'badge'

export interface TableColumn {
  key: string
  label: string
  type?: ColumnType
  render?: (value: unknown, row: Record<string, unknown>) => ReactNode
  sortable?: boolean
  width?: number | string
}

export interface SchemaTableProps {
  columns: TableColumn[]
  data: Record<string, unknown>[]
  emptyMessage?: string
  loading?: boolean
}

type SortDir = 'asc' | 'desc' | null

// ─── Cell formatters ──────────────────────────────────────────────────────────

function formatCell(value: unknown, type: ColumnType = 'string'): ReactNode {
  if (value === null || value === undefined || value === '') {
    return <span style={{ color: 'var(--text-muted, #667085)' }}>—</span>
  }

  switch (type) {
    case 'boolean':
      return (
        <span
          style={{
            display: 'inline-block',
            padding: '2px 8px',
            borderRadius: 4,
            fontSize: 11,
            fontWeight: 500,
            background: value
              ? 'rgba(0,255,167,0.1)'
              : 'rgba(255,255,255,0.06)',
            color: value ? '#00FFA7' : 'rgba(255,255,255,0.45)',
            border: value
              ? '1px solid rgba(0,255,167,0.25)'
              : '1px solid rgba(255,255,255,0.1)',
          }}
        >
          {value ? 'Yes' : 'No'}
        </span>
      )
    case 'date':
      return typeof value === 'string' ? (
        <span style={{ color: 'var(--text-secondary, #D0D5DD)', fontSize: 12 }}>
          {new Date(value).toLocaleDateString()}
        </span>
      ) : (
        String(value)
      )
    case 'number':
      return (
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>
          {typeof value === 'number' ? value.toLocaleString() : String(value)}
        </span>
      )
    default:
      return String(value)
  }
}

// ─── SchemaTable ──────────────────────────────────────────────────────────────

export function SchemaTable({
  columns,
  data,
  emptyMessage = 'No records found.',
  loading = false,
}: SchemaTableProps) {
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>(null)

  function handleSort(col: TableColumn) {
    if (!col.sortable) return
    if (sortKey === col.key) {
      if (sortDir === 'asc') {
        setSortDir('desc')
      } else if (sortDir === 'desc') {
        setSortKey(null)
        setSortDir(null)
      }
    } else {
      setSortKey(col.key)
      setSortDir('asc')
    }
  }

  const sorted = [...data].sort((a, b) => {
    if (!sortKey || !sortDir) return 0
    const av = a[sortKey]
    const bv = b[sortKey]
    const cmp =
      typeof av === 'number' && typeof bv === 'number'
        ? av - bv
        : String(av ?? '').localeCompare(String(bv ?? ''))
    return sortDir === 'asc' ? cmp : -cmp
  })

  return (
    <div style={{ overflowX: 'auto' }}>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 13,
        }}
      >
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                onClick={() => handleSort(col)}
                style={{
                  padding: '10px 12px',
                  textAlign: 'left',
                  fontWeight: 500,
                  fontSize: 11,
                  color: 'var(--text-muted, #667085)',
                  borderBottom: '1px solid var(--border, #344054)',
                  cursor: col.sortable ? 'pointer' : 'default',
                  userSelect: 'none',
                  whiteSpace: 'nowrap',
                  width: col.width,
                }}
              >
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                  }}
                >
                  {col.label}
                  {col.sortable && (
                    <SortIcon dir={sortKey === col.key ? sortDir : null} />
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <tr key={i}>
                {columns.map((col) => (
                  <td key={col.key} style={{ padding: '10px 12px' }}>
                    <div
                      className="skeleton"
                      style={{ height: 14, borderRadius: 4 }}
                    />
                  </td>
                ))}
              </tr>
            ))
          ) : sorted.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                style={{
                  padding: '32px 12px',
                  textAlign: 'center',
                  color: 'var(--text-muted, #667085)',
                  fontSize: 13,
                }}
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            sorted.map((row, rowIdx) => (
              <tr
                key={rowIdx}
                style={{
                  borderBottom: '1px solid var(--border, #344054)',
                  transition: 'background 80ms',
                }}
                onMouseEnter={(e) => {
                  ;(e.currentTarget as HTMLTableRowElement).style.background =
                    'var(--surface-hover, #1e2d3d)'
                }}
                onMouseLeave={(e) => {
                  ;(e.currentTarget as HTMLTableRowElement).style.background =
                    'transparent'
                }}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    style={{
                      padding: '10px 12px',
                      color: 'var(--text-secondary, #D0D5DD)',
                      maxWidth: 280,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {col.render
                      ? col.render(row[col.key], row)
                      : formatCell(row[col.key], col.type)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

// ─── Sort icon ────────────────────────────────────────────────────────────────

function SortIcon({ dir }: { dir: SortDir }) {
  if (dir === 'asc') return <ChevronUp size={12} />
  if (dir === 'desc') return <ChevronDown size={12} />
  return <ChevronsUpDown size={12} style={{ opacity: 0.4 }} />
}
