import { LoaderCircle } from 'lucide-react'

interface Props {
  title?: string
  message?: string
  /** 'cards' shows skeleton recommendation cards, 'charts' skeleton chart tiles, 'inline' only the spinner. */
  variant?: 'cards' | 'charts' | 'inline'
}

export function LoadingState({ title = 'Loading…', message, variant = 'inline' }: Props) {
  return (
    <div role="status" aria-live="polite" className="animate-fade-up">
      <div className="flex items-start gap-3">
        <LoaderCircle className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-violet-400" aria-hidden />
        <div>
          <p className="font-medium text-slate-100">{title}</p>
          {message && <p className="mt-1 max-w-xl text-sm text-slate-400">{message}</p>}
        </div>
      </div>
      {variant === 'cards' && (
        <div className="mt-6 space-y-4" aria-hidden>
          {[0, 1, 2].map((i) => (
            <div key={i} className="panel space-y-3 p-5">
              <div className="skeleton h-3 w-40" />
              <div className="skeleton h-5 w-3/4" />
              <div className="flex gap-2"><div className="skeleton h-5 w-16" /><div className="skeleton h-5 w-20" /></div>
              <div className="skeleton h-3 w-full" />
              <div className="skeleton h-3 w-2/3" />
            </div>
          ))}
        </div>
      )}
      {variant === 'charts' && (
        <div className="mt-6 grid gap-4 md:grid-cols-2" aria-hidden>
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-64 rounded-xl" />)}
        </div>
      )}
    </div>
  )
}
