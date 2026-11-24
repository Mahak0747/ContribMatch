import { BarChart3, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getAnalytics } from '../api/endpoints'
import { AnalyticsCharts } from '../components/AnalyticsCharts'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { useResource } from '../hooks/useResource'

export default function Analytics() {
  const { state, reload } = useResource(getAnalytics)
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-50">Analytics</h1>
          <p className="mt-1 text-sm text-slate-400">Computed from the recommendation history stored by your backend.</p>
        </div>
        <button type="button" className="btn-secondary" onClick={reload}><RefreshCw className="h-4 w-4" aria-hidden /> Refresh</button>
      </header>

      {state.status === 'loading' && <LoadingState variant="charts" title="Loading analytics…" />}
      {state.status === 'error' && <ErrorState error={state.error} title="Couldn't load analytics" onRetry={reload} />}
      {state.status === 'success' && (
        state.data.totals.recommendation_runs === 0
          ? <EmptyState icon={BarChart3} title="No analytics yet"
              description="Analytics appear after you generate your first recommendations."
              action={<Link to="/profile" className="btn-primary">Create a profile</Link>} />
          : <AnalyticsCharts data={state.data} />
      )}
    </div>
  )
}
