import { Plus, X } from 'lucide-react'
import { useId, useState, type KeyboardEvent } from 'react'

const MAX_ITEMS = 30 // same limits as the backend profile validation
const MAX_LEN = 50

interface Props {
  label: string
  hint?: string
  value: string[]
  onChange: (next: string[]) => void
  suggestions?: string[]
  placeholder?: string
  error?: string
}

/** Tag input: type + Enter/comma to add, click chips to remove, click suggestions to toggle. */
export function SkillSelector({ label, hint, value, onChange, suggestions = [], placeholder = 'Type and press Enter', error }: Props) {
  const [draft, setDraft] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const id = useId()
  const has = (s: string) => value.some((v) => v.toLowerCase() === s.toLowerCase())

  function add(raw: string) {
    const items = raw.split(',').map((s) => s.replace(/\s+/g, ' ').trim()).filter(Boolean)
    if (items.length === 0) return
    let next = [...value]
    for (const item of items) {
      if (item.length > MAX_LEN) { setLocalError(`Each item can be at most ${MAX_LEN} characters.`); return }
      if (next.some((v) => v.toLowerCase() === item.toLowerCase())) continue
      if (next.length >= MAX_ITEMS) { setLocalError(`You can add at most ${MAX_ITEMS} items.`); return }
      next = [...next, item]
    }
    setLocalError(null)
    onChange(next)
    setDraft('')
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      add(draft)
    } else if (e.key === 'Backspace' && draft === '' && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }

  const toggle = (s: string) => (has(s) ? onChange(value.filter((v) => v.toLowerCase() !== s.toLowerCase())) : add(s))
  const shownError = localError ?? error

  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-100">{label}</label>
      {hint && <p id={`${id}-hint`} className="mb-2 text-xs text-slate-500">{hint}</p>}

      <div className={`flex flex-wrap gap-1.5 rounded-lg border bg-navy-950/60 p-2 focus-within:border-violet-400 ${shownError ? 'border-rose-400/60' : 'border-white/10'}`}>
        {value.map((v) => (
          <span key={v} className="chip border-violet-400/30 bg-violet-500/10 text-violet-100">
            {v}
            <button type="button" aria-label={`Remove ${v}`} className="rounded p-0.5 hover:bg-white/10" onClick={() => onChange(value.filter((x) => x !== v))}>
              <X className="h-3 w-3" aria-hidden />
            </button>
          </span>
        ))}
        <input id={id} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKeyDown}
          onBlur={() => draft.trim() && add(draft)} placeholder={value.length ? '' : placeholder} maxLength={MAX_LEN * 4}
          aria-describedby={hint ? `${id}-hint` : undefined} aria-invalid={!!shownError}
          className="min-w-[8rem] flex-1 bg-transparent px-1 py-1 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none" />
      </div>

      {shownError && <p role="alert" className="mt-1 text-xs text-rose-300">{shownError}</p>}

      {suggestions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5" aria-label={`${label} suggestions`}>
          {suggestions.map((s) => (
            <button key={s} type="button" aria-pressed={has(s)} onClick={() => toggle(s)}
              className={`chip transition-colors hover:bg-white/10 ${has(s) ? 'border-violet-400/40 text-violet-200' : ''}`}>
              {!has(s) && <Plus className="h-3 w-3" aria-hidden />}{s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
