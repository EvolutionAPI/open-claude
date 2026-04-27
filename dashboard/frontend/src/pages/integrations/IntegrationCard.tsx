import { Pencil, Settings, Trash2 } from 'lucide-react'
import { getIntegrationIcon, getTypeMeta, type Integration } from './types'
import { getIntegrationMeta } from '../../lib/integrationMeta'

interface IntegrationCardProps {
  int: Integration
  onSelect: (int: Integration) => void
  onEdit?: (int: Integration) => void
  onDelete?: (int: Integration) => void
}

export function IntegrationCard({ int, onSelect, onEdit, onDelete }: IntegrationCardProps) {
  const typeMeta = getTypeMeta(int.type)
  const intIcon = getIntegrationIcon(int.name)
  const Icon = intIcon?.icon ?? typeMeta.icon
  const iconColor = intIcon?.color ?? typeMeta.color
  const iconBg = intIcon?.colorMuted ?? typeMeta.colorMuted
  const isConnected = int.status === 'ok'
  const intMeta = int.kind === 'core' ? getIntegrationMeta(int.name) : null
  const isOAuth = intMeta?.oauthFlow === true
  const isConfigurable = !isOAuth && (
    (intMeta?.fields && intMeta.fields.length > 0) ||
    (int.kind === 'custom' && (int.envKeys?.length ?? 0) > 0)
  )
  const isCustom = int.kind === 'custom'
  const isClickable = !!intMeta || isConfigurable

  return (
    <div
      onClick={() => {
        if (isClickable) onSelect(int)
      }}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={(e) => {
        if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          onSelect(int)
        }
      }}
      aria-label={isClickable ? `Configurar ${int.name}` : undefined}
      className={[
        'group relative rounded-xl border border-[#21262d] bg-[#161b22] p-5 transition-all duration-300 hover:border-transparent',
        isClickable ? 'cursor-pointer' : '',
      ].join(' ')}
    >
      <div
        className="pointer-events-none absolute inset-0 rounded-xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{
          boxShadow: isConnected
            ? 'inset 0 0 0 1px rgba(0,255,167,0.27), 0 0 20px rgba(0,255,167,0.10)'
            : `inset 0 0 0 1px ${typeMeta.color}44, 0 0 20px ${typeMeta.glowColor}`,
          borderRadius: 'inherit',
        }}
      />

      <div className="relative flex items-start justify-between mb-3">
        <div
          className="flex h-10 w-10 items-center justify-center rounded-lg transition-transform duration-300 group-hover:scale-110"
          style={{ backgroundColor: iconBg }}
        >
          <Icon size={20} style={{ color: iconColor }} />
        </div>
        <div className="flex items-center gap-1.5">
          {isCustom && (
            <>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onEdit?.(int)
                }}
                className="p-1 rounded text-[#667085] hover:text-[#00FFA7] transition-colors opacity-0 group-hover:opacity-100"
                title="Edit"
              >
                <Pencil size={13} />
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete?.(int)
                }}
                className="p-1 rounded text-[#667085] hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                title="Delete"
              >
                <Trash2 size={13} />
              </button>
            </>
          )}
          <span
            className="inline-block h-2.5 w-2.5 rounded-full mt-1"
            style={{
              backgroundColor: isConnected ? '#00FFA7' : '#3F3F46',
              boxShadow: isConnected ? '0 0 8px rgba(0,255,167,0.5)' : 'none',
            }}
          />
        </div>
      </div>

      <div className="relative flex items-center gap-2 mb-2">
        <h3 className="text-[15px] font-semibold text-[#e6edf3] transition-colors duration-200 group-hover:text-white">
          {int.name}
        </h3>
        {isCustom && (
          <span className="text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-[#00FFA7]/10 text-[#00FFA7] border border-[#00FFA7]/20">
            Custom
          </span>
        )}
      </div>

      {isCustom && int.description && (
        <p className="relative text-xs text-[#667085] mb-2 line-clamp-2">{int.description}</p>
      )}

      <div className="relative flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className="text-[10px] font-medium uppercase tracking-wider px-2 py-0.5 rounded-full border"
            style={{
              backgroundColor: typeMeta.colorMuted,
              color: typeMeta.color,
              borderColor: `${typeMeta.color}33`,
            }}
          >
            {int.type}
          </span>
          <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${
            isConnected
              ? 'bg-[#00FFA7]/10 text-[#00FFA7] border-[#00FFA7]/25'
              : 'bg-[#FBBF24]/10 text-[#FBBF24] border-[#FBBF24]/25'
          }`}>
            {isConnected ? 'Connected' : 'Not configured'}
          </span>
        </div>

        {isOAuth ? (
          <span className="flex items-center gap-1 text-[11px] text-[#667085] group-hover:text-[#00FFA7] opacity-0 group-hover:opacity-100 transition-all duration-200">
            Conectar
          </span>
        ) : isConfigurable ? (
          <span className="flex items-center gap-1 text-[11px] text-[#667085] group-hover:text-[#00FFA7] opacity-0 group-hover:opacity-100 transition-all duration-200">
            <Settings size={11} />
            Configurar
          </span>
        ) : null}
      </div>
    </div>
  )
}
