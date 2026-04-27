import { useState } from 'react'
import {
  Ban,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Edit2,
  FileCode,
  FileText,
  ShieldAlert,
  Terminal as TermIcon,
} from 'lucide-react'
import { AgentAvatar } from '../AgentAvatar'

export function TypingIndicator({ accentColor, isThinking }: { accentColor: string; isThinking?: boolean }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <div className="flex items-center gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{
              backgroundColor: accentColor,
              animation: 'chat-bounce 1.4s ease-in-out infinite',
              animationDelay: `${i * 0.16}s`,
            }}
          />
        ))}
      </div>
      <span className="text-[10px] text-[#667085]" style={{ animation: 'chat-pulse 2s ease-in-out infinite' }}>
        {isThinking ? 'Thinking...' : 'Typing...'}
      </span>
    </div>
  )
}

export function AgentInputToggle({ parsedInput, rawInput }: { parsedInput: any; rawInput: string }) {
  const [showInput, setShowInput] = useState(false)
  return (
    <div className="border-t border-[#21262d]/50">
      <button
        onClick={() => setShowInput((value) => !value)}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-[10px] text-[#667085] transition-colors hover:text-[#8b949e]"
      >
        {showInput ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        View input
      </button>
      {showInput && (
        <pre className="max-h-48 overflow-y-auto px-3 pb-2 font-mono text-[11px] whitespace-pre-wrap break-all text-[#8b949e]">
          {parsedInput ? JSON.stringify(parsedInput, null, 2) : rawInput}
        </pre>
      )}
    </div>
  )
}

export function TypingIndicatorMini({ accentColor }: { accentColor: string }) {
  return (
    <span className="flex items-center gap-0.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="inline-block h-1 w-1 rounded-full"
          style={{
            backgroundColor: accentColor,
            opacity: 0.7,
            animation: 'chat-bounce 1.4s ease-in-out infinite',
            animationDelay: `${i * 0.16}s`,
          }}
        />
      ))}
    </span>
  )
}

export function ToolCard({ block, accentColor }: { block: any; accentColor: string }) {
  const [open, setOpen] = useState(false)

  let parsedInput: any = null
  try {
    parsedInput = JSON.parse(block.input)
  } catch {}

  const isAgentTool = block.toolName === 'Agent' || block.toolName === 'SendMessage'
  const subagentName = parsedInput?.subagent_type || parsedInput?.name || parsedInput?.to || ''
  const subagentDesc = parsedInput?.description || parsedInput?.summary || block.subagentType || ''

  if (isAgentTool) {
    const isRunning = block.subagentStatus === 'running'
    const isDone = block.done || block.subagentStatus === 'completed' || block.subagentStatus === 'failed'
    const subagentTools = block.subagentTools || []
    const toolCount = subagentTools.length

    const getToolIcon = (toolName: string) => {
      if (toolName === 'Bash') return <TermIcon size={11} className="flex-shrink-0 text-[#667085]" />
      if (toolName === 'Read') return <FileText size={11} className="flex-shrink-0 text-[#667085]" />
      if (toolName === 'Edit' || toolName === 'Write') return <Edit2 size={11} className="flex-shrink-0 text-[#667085]" />
      return <FileCode size={11} className="flex-shrink-0 text-[#667085]" />
    }

    return (
      <div className="overflow-hidden rounded-lg border border-[#21262d]">
        <button
          onClick={() => setOpen((value) => !value)}
          className="flex w-full items-center gap-2.5 bg-[#161b22] px-3 py-2.5 text-[12px] transition-colors hover:bg-[#1c2333]"
        >
          {open ? <ChevronDown size={12} className="text-[#667085]" /> : <ChevronRight size={12} className="text-[#667085]" />}

          {(() => {
            const isUuid = /^[0-9a-f]{8,}$/i.test(subagentName)
            const displayName = isUuid ? '' : subagentName
            return displayName ? (
              <AgentAvatar name={displayName.replace('custom-', '')} size={20} />
            ) : (
              <FileCode size={13} style={{ color: accentColor }} />
            )
          })()}

          <span className="font-medium text-[#e6edf3]">
            {(() => {
              const isUuid = /^[0-9a-f]{8,}$/i.test(subagentName)
              return isUuid ? (block.toolName === 'SendMessage' ? 'SendMessage' : 'Agent') : subagentName ? `@${subagentName}` : block.toolName
            })()}
          </span>

          {subagentDesc && <span className="max-w-[300px] truncate text-[11px] text-[#8b949e]">{subagentDesc}</span>}

          <span className="ml-auto flex items-center gap-2 flex-shrink-0">
            {toolCount > 0 && (
              <span className="text-[10px] tabular-nums text-[#667085]">
                {toolCount} {toolCount === 1 ? 'tool' : 'tools'}
              </span>
            )}
            {isRunning && block.subagentSummary && (
              <span className="max-w-[200px] truncate text-[10px] text-[#667085]" style={{ animation: 'chat-pulse 2s ease-in-out infinite' }}>
                {block.subagentSummary}
              </span>
            )}
            {isDone ? (
              <CheckCircle2 size={13} className={block.subagentStatus === 'failed' ? 'text-[#ef4444]' : 'text-[#22C55E]'} />
            ) : (
              <TypingIndicatorMini accentColor={accentColor} />
            )}
          </span>
        </button>

        {open && (
          <div className="border-t border-[#21262d] bg-[#0d1117]">
            <div className="max-h-80 overflow-y-auto">
              {subagentTools.length === 0 ? (
                <div className="px-3 py-2 text-[11px] text-[#667085]">No tools yet</div>
              ) : (
                subagentTools.map((tool: any, index: number) => {
                  let inputPreview = ''
                  try {
                    const parsed = JSON.parse(tool.input)
                    inputPreview = (parsed.command || parsed.file_path || parsed.path || parsed.pattern || parsed.description || tool.input).slice(0, 60)
                  } catch {
                    inputPreview = tool.input.slice(0, 60)
                  }

                  return (
                    <div
                      key={tool.toolUseId || index}
                      className="flex items-center gap-2 border-t border-[#21262d]/50 px-3 py-1.5 text-[11px] first:border-t-0"
                    >
                      {getToolIcon(tool.toolName)}
                      <span className="flex-shrink-0 font-medium text-[#8b949e]">{tool.toolName}</span>
                      {inputPreview && <span className="truncate text-[#667085]">{inputPreview}</span>}
                    </div>
                  )
                })
              )}
            </div>
            {block.input && <AgentInputToggle parsedInput={parsedInput} rawInput={block.input} />}
          </div>
        )}
      </div>
    )
  }

  if (block.toolName === 'TodoWrite' && Array.isArray(parsedInput?.todos)) {
    const todos: Array<{ content: string; status: string; priority?: string; id?: string }> = parsedInput.todos
    const completedCount = todos.filter((todo) => todo.status === 'completed').length

    return (
      <div className="overflow-hidden rounded-lg border border-[#21262d]">
        <button
          onClick={() => setOpen((value) => !value)}
          className="flex w-full items-center gap-2 bg-[#161b22] px-3 py-2 text-[12px] transition-colors hover:bg-[#1c2333]"
        >
          {open ? <ChevronDown size={12} className="text-[#667085]" /> : <ChevronRight size={12} className="text-[#667085]" />}
          <CheckCircle2 size={13} style={{ color: accentColor }} />
          <span className="font-medium text-[#e6edf3]">TodoWrite</span>
          <span className="text-[11px] text-[#667085]">{completedCount}/{todos.length} done</span>
          <span className="ml-auto flex-shrink-0">
            {block.done ? <CheckCircle2 size={13} className="text-[#22C55E]" /> : <TypingIndicatorMini accentColor={accentColor} />}
          </span>
        </button>

        <div className="space-y-1 border-t border-[#21262d] bg-[#0d1117] px-3 py-2">
          {todos.map((todo, index) => {
            const isPending = todo.status === 'pending'
            const isInProgress = todo.status === 'in_progress'
            const isCompleted = todo.status === 'completed'
            const icon = isPending ? '○' : isInProgress ? '◐' : '●'
            return (
              <div key={index} className="flex items-start gap-2 text-[12px]">
                <span className="mt-0.5 flex-shrink-0 font-mono text-[13px]" style={{ color: isPending ? '#667085' : '#00FFA7' }}>
                  {icon}
                </span>
                <span className={isCompleted ? 'opacity-60 line-through' : ''} style={{ color: isPending ? '#8b949e' : isCompleted ? '#8b949e' : '#e6edf3' }}>
                  {todo.content}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  const displayInfo = parsedInput
    ? (parsedInput.command || parsedInput.file_path || parsedInput.path || parsedInput.pattern || parsedInput.description || '')
    : ''

  return (
    <div className="overflow-hidden rounded-lg border border-[#21262d]">
      <button
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 bg-[#161b22] px-3 py-2 text-[12px] transition-colors hover:bg-[#1c2333]"
      >
        {open ? <ChevronDown size={12} className="text-[#667085]" /> : <ChevronRight size={12} className="text-[#667085]" />}
        <FileCode size={13} style={{ color: accentColor }} />
        <span className="font-medium text-[#e6edf3]">{block.toolName}</span>
        {displayInfo && <span className="max-w-[300px] truncate font-mono text-[11px] text-[#667085]">{displayInfo}</span>}
        <span className="ml-auto flex-shrink-0">
          {block.done ? <CheckCircle2 size={13} className="text-[#22C55E]" /> : <TypingIndicatorMini accentColor={accentColor} />}
        </span>
      </button>

      {open && block.input && (
        <div className="border-t border-[#21262d] bg-[#0d1117] px-3 py-2">
          <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap break-all font-mono text-[11px] text-[#8b949e]">
            {parsedInput ? JSON.stringify(parsedInput, null, 2) : block.input}
          </pre>
        </div>
      )}
    </div>
  )
}

export function ApprovalCard({ req, accentColor, onAllow, onDeny }: { req: any; accentColor: string; onAllow: () => void; onDeny: () => void }) {
  let summary = ''
  const inp = req.input as any

  if (req.toolName === 'Bash') {
    summary = inp?.command ? String(inp.command).slice(0, 120) : ''
  } else if (req.toolName === 'Write') {
    const lines = inp?.content ? String(inp.content).split('\n').slice(0, 5).join('\n') : ''
    summary = inp?.file_path ? `${inp.file_path}${lines ? '\n' + lines : ''}` : lines
  } else if (req.toolName === 'Edit') {
    summary = inp?.file_path ? String(inp.file_path) : ''
  } else if (req.toolName === 'Agent') {
    const agentName = inp?.subagent_type || inp?.agent || ''
    const prompt = inp?.prompt || inp?.description || ''
    summary = agentName ? `@${agentName}${prompt ? ' — ' + String(prompt).slice(0, 80) : ''}` : String(prompt).slice(0, 100)
  }
  if (!summary && req.title) summary = req.title

  return (
    <div className="flex items-start gap-3 rounded-lg border border-[#F59E0B30] bg-[#161b22] px-3 py-2.5">
      <ShieldAlert size={14} className="mt-0.5 flex-shrink-0" style={{ color: '#F59E0B' }} />
      <div className="min-w-0 flex-1">
        <div className="mb-0.5 flex items-center gap-2">
          <span className="text-[11px] font-semibold text-[#e6edf3]">{req.toolName}</span>
          {summary && <span className="max-w-[260px] truncate font-mono text-[10px] text-[#8b949e]">{summary}</span>}
        </div>
        {req.description && <p className="truncate text-[10px] text-[#667085]">{req.description}</p>}
      </div>
      <div className="flex flex-shrink-0 items-center gap-1.5">
        <button
          onClick={onAllow}
          className="flex items-center gap-1 rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors"
          style={{ background: `${accentColor}20`, color: accentColor, borderColor: `${accentColor}40` }}
        >
          <Check size={11} />
          Allow
        </button>
        <button
          onClick={onDeny}
          className="flex items-center gap-1 rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors hover:bg-white/5"
          style={{ background: 'transparent', color: '#8b949e', borderColor: '#21262d' }}
        >
          <Ban size={11} />
          Deny
        </button>
      </div>
    </div>
  )
}
