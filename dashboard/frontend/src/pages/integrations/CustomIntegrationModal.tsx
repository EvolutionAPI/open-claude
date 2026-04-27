import { useEffect, useRef, useState } from 'react'
import { Eye, EyeOff, Loader2, Plus, X } from 'lucide-react'
import { api } from '../../lib/api'
import { CATEGORY_OPTIONS, EMPTY_FORM, type CustomIntegrationForm, slugify } from './types'

interface CustomModalProps {
  open: boolean
  initial?: CustomIntegrationForm & { slug: string }
  isEdit: boolean
  onClose: () => void
  onSaved: (envWritten?: boolean) => void
}

export function CustomIntegrationModal({ open, initial, isEdit, onClose, onSaved }: CustomModalProps) {
  const [form, setForm] = useState<CustomIntegrationForm>(EMPTY_FORM)
  const [slugManual, setSlugManual] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<keyof CustomIntegrationForm, string>>>({})
  const [saving, setSaving] = useState(false)
  const [visibleRows, setVisibleRows] = useState<Set<number>>(new Set())
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) {
      const baseForm = initial
        ? {
            ...initial,
            envKeys: (initial.envKeys as unknown as (string | { name: string; value: string })[]).map((k) =>
              typeof k === 'string' ? { name: k, value: '' } : k
            ),
          }
        : EMPTY_FORM
      setForm(baseForm)
      setSlugManual(isEdit)
      setErrors({})
      setVisibleRows(new Set())
      setSaving(false)
    }
  }, [open, initial, isEdit])

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  const setField = <K extends keyof CustomIntegrationForm>(key: K, value: CustomIntegrationForm[K]) => {
    setForm((prev) => {
      const next = { ...prev, [key]: value }
      if (key === 'displayName' && !slugManual) {
        next.slug = slugify(value as string)
      }
      return next
    })
    setErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  const validate = (): boolean => {
    const errs: Partial<Record<keyof CustomIntegrationForm, string>> = {}
    if (!form.displayName.trim()) errs.displayName = 'Required'
    if (!form.slug.trim()) {
      errs.slug = 'Required'
    } else if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(form.slug)) {
      errs.slug = 'Lowercase letters, digits and hyphens only'
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSave = async () => {
    if (!validate()) return
    setSaving(true)
    try {
      const envKeyNames = form.envKeys.map((r) => r.name).filter((n) => n.trim())
      const envValues: Record<string, string> = {}
      for (const row of form.envKeys) {
        if (row.name.trim() && row.value.trim()) {
          envValues[row.name.trim()] = row.value.trim()
        }
      }
      const hasEnvValues = Object.keys(envValues).length > 0

      if (isEdit && initial?.slug) {
        await api.patch(`/integrations/custom/${initial.slug}`, {
          displayName: form.displayName,
          description: form.description,
          category: form.category,
          envKeys: envKeyNames,
          ...(hasEnvValues ? { envValues } : {}),
        })
      } else {
        await api.post('/integrations/custom', {
          slug: form.slug,
          displayName: form.displayName,
          description: form.description,
          category: form.category,
          envKeys: envKeyNames,
          ...(hasEnvValues ? { envValues } : {}),
        })
      }
      onSaved(hasEnvValues)
      onClose()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error saving'
      setErrors({ displayName: msg })
    } finally {
      setSaving(false)
    }
  }

  const addEnvRow = () => {
    setField('envKeys', [...form.envKeys, { name: '', value: '' }])
  }

  const removeEnvRow = (idx: number) => {
    setField('envKeys', form.envKeys.filter((_, i) => i !== idx))
    setVisibleRows((prev) => {
      const next = new Set(prev)
      next.delete(idx)
      return next
    })
  }

  const updateEnvRow = (idx: number, field: 'name' | 'value', val: string) => {
    const next = form.envKeys.map((r, i) =>
      i === idx ? { ...r, [field]: field === 'name' ? val.toUpperCase() : val } : r
    )
    setField('envKeys', next)
  }

  const toggleRowVisibility = (idx: number) => {
    setVisibleRows((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        ref={overlayRef}
        className="absolute inset-0 bg-black/60 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <div className="relative w-full max-w-lg bg-[#0C111D] border border-[#21262d] rounded-2xl shadow-2xl flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#21262d]">
          <h2 className="text-base font-semibold text-[#e6edf3]">
            {isEdit ? 'Edit Custom Integration' : 'New Custom Integration'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-[#667085] hover:text-[#e6edf3] hover:bg-[#21262d] transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-[#8b949e] mb-1">
              Display Name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={form.displayName}
              onChange={(e) => setField('displayName', e.target.value)}
              placeholder="My Custom API"
              className="w-full rounded-lg border border-[#21262d] bg-[#161b22] px-3 py-2 text-sm text-[#e6edf3] placeholder-[#3F3F46] focus:outline-none focus:border-[#00FFA7]/50 transition-colors"
            />
            {errors.displayName && <p className="text-xs text-red-400 mt-1">{errors.displayName}</p>}
          </div>

          <div>
            <label className="block text-xs font-medium text-[#8b949e] mb-1">
              Slug <span className="text-red-400">*</span>
            </label>
            <div className="flex items-center rounded-lg border border-[#21262d] bg-[#161b22] focus-within:border-[#00FFA7]/50 transition-colors">
              <span className="pl-3 text-xs text-[#3F3F46] shrink-0">custom-int-</span>
              <input
                type="text"
                value={form.slug}
                onChange={(e) => {
                  setSlugManual(true)
                  setField('slug', e.target.value)
                }}
                disabled={isEdit}
                placeholder="my-api"
                className="flex-1 bg-transparent px-1 py-2 text-sm text-[#e6edf3] placeholder-[#3F3F46] focus:outline-none disabled:opacity-50"
              />
            </div>
            {errors.slug && <p className="text-xs text-red-400 mt-1">{errors.slug}</p>}
          </div>

          <div>
            <label className="block text-xs font-medium text-[#8b949e] mb-1">Description</label>
            <textarea
              value={form.description}
              onChange={(e) => setField('description', e.target.value)}
              rows={2}
              placeholder="What this integration does..."
              className="w-full rounded-lg border border-[#21262d] bg-[#161b22] px-3 py-2 text-sm text-[#e6edf3] placeholder-[#3F3F46] focus:outline-none focus:border-[#00FFA7]/50 transition-colors resize-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[#8b949e] mb-1">Category</label>
            <select
              value={form.category}
              onChange={(e) => setField('category', e.target.value)}
              className="w-full rounded-lg border border-[#21262d] bg-[#161b22] px-3 py-2 text-sm text-[#e6edf3] focus:outline-none focus:border-[#00FFA7]/50 transition-colors"
            >
              {CATEGORY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-[#8b949e] mb-1">Env Keys</label>
            <div className="space-y-1.5 mb-2">
              {form.envKeys.map((row, idx) => (
                <div key={idx} className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={row.name}
                    onChange={(e) => updateEnvRow(idx, 'name', e.target.value)}
                    placeholder="MY_API_KEY"
                    className="w-44 shrink-0 rounded-lg border border-[#21262d] bg-[#161b22] px-3 py-1.5 text-xs text-[#00FFA7] placeholder-[#3F3F46] focus:outline-none focus:border-[#00FFA7]/50 transition-colors font-mono"
                  />
                  <div className="relative flex-1">
                    <input
                      type={visibleRows.has(idx) ? 'text' : 'password'}
                      value={row.value}
                      onChange={(e) => updateEnvRow(idx, 'value', e.target.value)}
                      placeholder={isEdit ? 'leave empty to keep current' : 'secret value (optional)'}
                      className="w-full rounded-lg border border-[#21262d] bg-[#161b22] px-3 py-1.5 pr-8 text-xs text-[#e6edf3] placeholder-[#3F3F46] focus:outline-none focus:border-[#00FFA7]/50 transition-colors"
                    />
                    {row.value.length > 0 && (
                      <button
                        type="button"
                        onClick={() => toggleRowVisibility(idx)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-[#667085] hover:text-[#e6edf3] transition-colors"
                        tabIndex={-1}
                      >
                        {visibleRows.has(idx) ? <EyeOff size={12} /> : <Eye size={12} />}
                      </button>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => removeEnvRow(idx)}
                    className="p-1 rounded text-[#667085] hover:text-red-400 transition-colors shrink-0"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={addEnvRow}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-dashed border-[#21262d] text-xs text-[#667085] hover:text-[#e6edf3] hover:border-[#344054] transition-colors"
            >
              <Plus size={12} />
              Add env key
            </button>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-[#21262d]">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-[#667085] hover:text-[#e6edf3] hover:bg-[#21262d] transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#00FFA7] text-[#0C111D] text-sm font-semibold hover:bg-[#00e699] transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {saving && <Loader2 size={14} className="animate-spin" />}
            {isEdit ? 'Save Changes' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}
