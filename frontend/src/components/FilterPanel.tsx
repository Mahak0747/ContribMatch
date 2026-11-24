import { RotateCcw, Search, SlidersHorizontal } from 'lucide-react'
import { useId, useState } from 'react'
import { isFiltered, SORT_OPTIONS, type Filters, type SortKey } from '../lib/filters'

interface Props {
  filters: Filters
  onChange: (f: Filters) => void
  onReset: () => void
  languages: string[]
  labels: string[]
  shown: number
  total: number
}

export function FilterPanel({ filters, onChange, onReset, languages, labels, shown, total }: Props) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => onChange({ ...filters, [k]: v })

  return (
    <section className="panel p-4" aria-label="Filters and sorting">
      <button type="button" className="flex w-full items-center justify-between lg:hidden" aria-expanded={open}
        aria-controls={`${id}-body`} onClick={() => setOpen((v) => !v)}>
        <span className="inline-flex items-center gap-2 text-sm font-medium text-slate-100">
          <SlidersHorizontal className="h-4 w-4" aria-hidden /> Filter &amp; sort
        </span>
        <span className="font-mono text-xs text-slate-400">{shown}/{total}</span>
      </button>

      <div id={`${id}-body`} className={`${open ? 'mt-4 block' : 'hidden'} space-y-4 lg:mt-0 lg:block`}>
        <div className="hidden items-center justify-between lg:flex">
          <h2 className="inline-flex items-center gap-2 text-sm font-semibold text-slate-100">
            <SlidersHorizontal className="h-4 w-4" aria-hidden /> Filter &amp; sort
          </h2>
          <span className="font-mono text-xs text-slate-400" aria-live="polite">{shown}/{total}</span>
        </div>

        <div>
          <label htmlFor={`${id}-q`} className="mb-1 block text-xs text-slate-400">Search results</label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" aria-hidden />
            <input id={`${id}-q`} type="search" className="field pl-8" placeholder="title, repo, skill…"
              value={filters.query} onChange={(e) => set('query', e.target.value)} />
          </div>
        </div>

        <div>
          <label htmlFor={`${id}-sort`} className="mb-1 block text-xs text-slate-400">Sort by</label>
          <select id={`${id}-sort`} className="field" value={filters.sort} onChange={(e) => set('sort', e.target.value as SortKey)}>
            {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>

        <div>
          <label htmlFor={`${id}-lang`} className="mb-1 block text-xs text-slate-400">Repository language</label>
          <select id={`${id}-lang`} className="field" value={filters.language} onChange={(e) => set('language', e.target.value)}>
            <option value="">Any</option>
            {languages.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>

        <div>
          <label htmlFor={`${id}-label`} className="mb-1 block text-xs text-slate-400">Issue label</label>
          <select id={`${id}-label`} className="field" value={filters.label} onChange={(e) => set('label', e.target.value)}>
            <option value="">Any</option>
            {labels.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>

        <div>
          <label htmlFor={`${id}-min`} className="mb-1 flex justify-between text-xs text-slate-400">
            <span>Minimum score</span><span className="font-mono text-slate-200">{filters.minScore}</span>
          </label>
          <input id={`${id}-min`} type="range" min={0} max={100} step={5} className="w-full accent-violet-500"
            value={filters.minScore} onChange={(e) => set('minScore', Number(e.target.value))} />
        </div>

        <button type="button" className="btn-secondary w-full" onClick={onReset} disabled={!isFiltered(filters)}>
          <RotateCcw className="h-4 w-4" aria-hidden /> Reset filters
        </button>
      </div>
    </section>
  )
}
