import { ChevronLeft, ChevronRight, History as HistoryIcon } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getHistory } from '../api/endpoints'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { useSession } from '../context/sessionContext'
import { useResource } from '../hooks/useResource'
import { formatDate, timeAgo } from '../lib/format'

const PAGE = 10

export default function History() {
  const [offset, setOffset] = useState(0)
  const { state, reload } = useResource(() => getHistory(PAGE, offset), [offset])
  const { setRunId } = useSession()
  const navigate = useNavigate()

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-50">History</h1>
        <p className="mt-1 text-sm text-slate-400">Every recommendation run saved by your backend, newest first.</p>
      </header>

      {state.status === 'loading' && <LoadingState title="Loading history…" />}
      {state.status === 'error' && <ErrorState error={state.error} title="Couldn't load history" onRetry={reload} />}
      {state.status === 'success' && (state.data.total === 0
        ? <EmptyState icon={HistoryIcon} title="No history yet" description="Runs you generate will be listed here."
            action={<Link to="/profile" className="btn-primary">Create a profile</Link>} />
        : (
          <>
            <ul className="space-y-3">
              {state.data.items.map((h) => (
                <li key={h.id} className="panel flex flex-wrap items-center justify-between gap-4 p-4">
                  <div className="min-w-0">
                    <p className="text-sm text-slate-100">
                      Run #{h.id} <span className="text-slate-500">· {timeAgo(h.created_at)} ({formatDate(h.created_at)})</span>
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <span className="chip">{h.experience_level}</span>
                      {h.skills.slice(0, 5).map((s) => <span key={s} className="chip border-violet-400/30 text-violet-200">{s}</span>)}
                      {h.skills.length > 5 && <span className="chip">+{h.skills.length - 5}</span>}
                      {h.domains.slice(0, 2).map((d) => <span key={d} className="chip border-blue-400/30 text-blue-200">{d}</span>)}
                    </div>
                    <p className="mt-2 text-xs text-slate-500">
                      {h.issues_analyzed} analysed · {h.recommendation_count} recommended{h.top_score != null && <> · top score <span className="font-mono">{h.top_score.toFixed(1)}</span></>}
                    </p>
                  </div>
                  <button type="button" className="btn-secondary" onClick={() => { setRunId(h.id); navigate('/dashboard') }}>Open</button>
                </li>
              ))}
            </ul>
            <nav className="flex items-center justify-between" aria-label="History pages">
              <button type="button" className="btn-secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                <ChevronLeft className="h-4 w-4" aria-hidden /> Newer
              </button>
              <span className="font-mono text-xs text-slate-400">{offset + 1}–{Math.min(offset + PAGE, state.data.total)} of {state.data.total}</span>
              <button type="button" className="btn-secondary" disabled={offset + PAGE >= state.data.total} onClick={() => setOffset(offset + PAGE)}>
                Older <ChevronRight className="h-4 w-4" aria-hidden />
              </button>
            </nav>
          </>
        ))}
    </div>
  )
}
