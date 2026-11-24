import { RefreshCw, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ApiError } from '../api/client'
import { errorHint } from '../lib/errors'

interface Props {
  error: ApiError
  title?: string
  onRetry?: () => void
  actions?: ReactNode
}

export function ErrorState({ error, title = 'Something went wrong', onRetry, actions }: Props) {
  const hint = errorHint(error)
  return (
    <div role="alert" className="panel animate-fade-up border-rose-400/30 bg-rose-950/20 p-6">
      <div className="flex items-start gap-3">
        <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0 text-rose-300" aria-hidden />
        <div className="min-w-0">
          <h2 className="font-semibold text-slate-100">{title}</h2>
          <p className="mt-1 break-words text-sm text-slate-300">{error.message}</p>
          {hint && <p className="mt-2 text-sm text-slate-400">{hint}</p>}
          <div className="mt-4 flex flex-wrap gap-3">
            {onRetry && (
              <button type="button" className="btn-secondary" onClick={onRetry}>
                <RefreshCw className="h-4 w-4" aria-hidden /> Try again
              </button>
            )}
            {actions}
          </div>
        </div>
      </div>
    </div>
  )
}
