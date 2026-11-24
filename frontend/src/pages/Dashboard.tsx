import { Info, RefreshCw, SearchX, UserPlus } from 'lucide-react'
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { toApiError, type ApiError } from '../api/client'
import { createRecommendations, getRecommendation } from '../api/endpoints'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { FilterPanel } from '../components/FilterPanel'
import { LoadingState } from '../components/LoadingState'
import { RecommendationCard } from '../components/RecommendationCard'
import { useSession } from '../context/sessionContext'
import { DEFAULT_FILTERS, filterAndSort, filterOptions, type Filters } from '../lib/filters'
import { timeAgo } from '../lib/format'
import type { RecommendationRun } from '../types/api'

type State =
  | { status: 'idle' }
  | { status: 'loading'; kind: 'load' | 'generate' }
  | { status: 'success'; run: RecommendationRun }
  | { status: 'error'; error: ApiError }

type Action =
  | { type: 'loading'; kind: 'load' | 'generate' }
  | { type: 'success'; run: RecommendationRun }
  | { type: 'error'; error: ApiError }

function reducer(_: State, a: Action): State {
  switch (a.type) {
    case 'loading': return { status: 'loading', kind: a.kind }
    case 'success': return { status: 'success', run: a.run }
    case 'error': return { status: 'error', error: a.error }
  }
}

const TOP_K_OPTIONS = [5, 10, 20]

export default function Dashboard() {
  const { profile, runId, setRunId, reset } = useSession()
  const [state, dispatch] = useReducer(reducer, undefined, (): State =>
    runId != null ? { status: 'loading', kind: 'load' } : profile ? { status: 'loading', kind: 'generate' } : { status: 'idle' })
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [topK, setTopK] = useState(10)
  const seq = useRef(0)
  const started = useRef(false)

  /** Runs `fn`, ignoring the result if a newer request has started since. */
  const execute = useCallback(async (fn: () => Promise<RecommendationRun>) => {
    const mine = ++seq.current
    try {
      const run = await fn()
      if (mine !== seq.current) return
      setRunId(run.id)
      dispatch({ type: 'success', run })
    } catch (e) {
      if (mine !== seq.current) return
      dispatch({ type: 'error', error: toApiError(e) })
    }
  }, [setRunId])

  const generate = useCallback((profileId: number, k: number) => execute(() => createRecommendations(profileId, k)), [execute])

  // First load: open the saved run if there is one, otherwise create recommendations for the saved profile.
  useEffect(() => {
    if (started.current) return
    started.current = true
    if (runId != null) {
      void execute(async () => {
        try {
          return await getRecommendation(runId)
        } catch (e) {
          const err = toApiError(e)
          if (err.code === 'not_found' && profile) return createRecommendations(profile.id, topK) // stored run is gone
          throw err
        }
      })
    } else if (profile) {
      void generate(profile.id, topK)
    }
  }, [runId, profile, topK, execute, generate])

  const run = state.status === 'success' ? state.run : null
  const options = useMemo(() => filterOptions(run?.recommendations ?? []), [run])
  const visible = useMemo(() => (run ? filterAndSort(run.recommendations, filters) : []), [run, filters])
  const profileId = run?.profile_id ?? profile?.id

  function refresh() {
    if (profileId == null) return
    dispatch({ type: 'loading', kind: 'generate' })
    setFilters(DEFAULT_FILTERS)
    void generate(profileId, topK)
  }

  const goProfile = <Link to="/profile" className="btn-primary"><UserPlus className="h-4 w-4" aria-hidden /> {profile ? 'Edit profile' : 'Create a profile'}</Link>

  if (state.status === 'idle') {
    return <EmptyState icon={UserPlus} title="Create a profile to get recommendations"
      description="Tell ContribMatch your skills and interests, and it will find real open GitHub issues that fit." action={goProfile} />
  }

  if (state.status === 'loading') {
    return <LoadingState variant="cards"
      title={state.kind === 'generate' ? 'Searching GitHub and ranking issues…' : 'Loading your recommendations…'}
      message={state.kind === 'generate'
        ? 'This fetches real open issues and scores them. The very first request also loads the local embedding model, which can take a minute.'
        : undefined} />
  }

  if (state.status === 'error') {
    return <ErrorState error={state.error} title="Couldn't get recommendations"
      onRetry={profileId != null ? refresh : undefined}
      actions={<>
        {state.error.code === 'not_found' && <button type="button" className="btn-secondary" onClick={() => { reset() }}>Start over</button>}
        {goProfile}
      </>} />
  }

  const { recommendations } = state.run
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-50">Recommended issues</h1>
          <p className="mt-1 text-sm text-slate-400">
            {state.run.issues_analyzed} issue{state.run.issues_analyzed === 1 ? '' : 's'} analysed · generated {timeAgo(state.run.created_at)} ·
            model <span className="font-mono text-xs">{state.run.model}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="topk" className="text-xs text-slate-400">Show</label>
          <select id="topk" className="field w-20 py-1.5" value={topK} onChange={(e) => setTopK(Number(e.target.value))}>
            {TOP_K_OPTIONS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <button type="button" className="btn-secondary" onClick={refresh}><RefreshCw className="h-4 w-4" aria-hidden /> Refresh</button>
        </div>
      </header>

      {(state.run.warnings.length > 0 || state.run.stale_data) && (
        <div role="status" className="rounded-lg border border-amber-400/30 bg-amber-500/10 p-4 text-sm text-amber-100">
          <div className="flex items-center gap-2 font-medium"><Info className="h-4 w-4" aria-hidden /> Notes about this run</div>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-amber-100/90">
            {state.run.stale_data && <li>Some GitHub data comes from an older cached copy because GitHub was unavailable.</li>}
            {state.run.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        </div>
      )}

      {recommendations.length === 0 ? (
        <EmptyState icon={SearchX} title="No matching issues found"
          description="GitHub returned no open issues for this search. Try adding more languages or skills, choosing a broader domain, or a different experience level."
          action={goProfile} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[17rem_1fr]">
          <div className="lg:sticky lg:top-24 lg:self-start">
            <FilterPanel filters={filters} onChange={setFilters} onReset={() => setFilters(DEFAULT_FILTERS)}
              languages={options.languages} labels={options.labels} shown={visible.length} total={recommendations.length} />
          </div>
          <div className="min-w-0 space-y-4">
            {visible.length === 0
              ? <EmptyState icon={SearchX} title="No recommendations match these filters"
                  description="Loosen the filters to see the rest of your results."
                  action={<button type="button" className="btn-secondary" onClick={() => setFilters(DEFAULT_FILTERS)}>Reset filters</button>} />
              : visible.map((r) => <RecommendationCard key={r.issue.id} rec={r} weights={state.run.weights} />)}
            <details className="panel p-4 text-sm text-slate-400">
              <summary className="cursor-pointer text-slate-300">GitHub searches used for this run</summary>
              <ul className="mt-3 space-y-2">
                {state.run.search_queries.map((q) => <li key={q} className="break-all rounded bg-navy-950/60 p-2 font-mono text-xs">{q}</li>)}
              </ul>
            </details>
          </div>
        </div>
      )}
    </div>
  )
}
