import { getHealth } from '../api/endpoints'
import { useResource } from '../hooks/useResource'

/** Real backend health check (GET /api/health), shown as a small status dot. */
export function ApiStatus() {
  const { state } = useResource(getHealth)
  const ok = state.status === 'success' && state.data.status === 'ok'
  const degraded = state.status === 'success' && state.data.status !== 'ok'
  const label = state.status === 'loading' ? 'Checking API…' : ok ? 'API online' : degraded ? 'API degraded' : 'API offline'
  const dot = state.status === 'loading' ? 'bg-slate-500' : ok ? 'bg-emerald-400' : degraded ? 'bg-amber-400' : 'bg-rose-400'
  return (
    <span className="inline-flex items-center gap-2 text-xs text-slate-400" role="status" title={state.status === 'error' ? state.error.message : undefined}>
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden />
      <span className="hidden sm:inline">{label}</span>
      <span className="sr-only sm:hidden">{label}</span>
    </span>
  )
}
