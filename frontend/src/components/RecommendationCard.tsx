import { Check, ChevronDown, Clock, ExternalLink, GitBranch, Lightbulb, MessageSquare, Star } from 'lucide-react'
import { useState } from 'react'
import { formatCompact, safeGithubUrl, timeAgo } from '../lib/format'
import type { Recommendation } from '../types/api'
import { ScoreBreakdown } from './ScoreBreakdown'
import { ScoreRing } from './ScoreRing'

interface Props {
  rec: Recommendation
  weights: Record<string, number>
}

export function RecommendationCard({ rec, weights }: Props) {
  const [details, setDetails] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const { issue } = rec
  const issueUrl = safeGithubUrl(issue.url)
  const repoUrl = safeGithubUrl(issue.repo_url)
  const relevant = new Set(rec.relevant_labels)
  const longExplanation = rec.explanation.length > 220

  return (
    <article className="panel animate-fade-up p-5 transition-colors hover:border-violet-400/30" aria-labelledby={`issue-${issue.id}`}>
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
            <span className="font-mono text-slate-500">#{rec.rank}</span>
            <span className="inline-flex min-w-0 items-center gap-1">
              <GitBranch className="h-3.5 w-3.5 shrink-0" aria-hidden />
              {repoUrl
                ? <a href={repoUrl} target="_blank" rel="noopener noreferrer" className="truncate font-mono hover:text-violet-300 hover:underline">{issue.repo_full_name}</a>
                : <span className="truncate font-mono">{issue.repo_full_name}</span>}
            </span>
            {issue.repo_language && <span className="chip">{issue.repo_language}</span>}
            {issue.repo_stars != null && (
              <span className="inline-flex items-center gap-1" title="Repository stars">
                <Star className="h-3.5 w-3.5" aria-hidden />{formatCompact(issue.repo_stars)}
              </span>
            )}
          </div>

          <h3 id={`issue-${issue.id}`} className="mt-2 text-base font-semibold leading-snug text-slate-100 sm:text-lg">
            {issueUrl
              ? <a href={issueUrl} target="_blank" rel="noopener noreferrer" className="break-words hover:text-violet-300">{issue.title}</a>
              : <span className="break-words">{issue.title}</span>}
          </h3>
        </div>
        <ScoreRing score={rec.scores.overall} />
      </div>

      {issue.labels.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Labels">
          {issue.labels.map((l) => (
            <li key={l} className={relevant.has(l) ? 'chip border-violet-400/40 bg-violet-500/10 text-violet-200' : 'chip'}>{l}</li>
          ))}
        </ul>
      )}

      {rec.matching_skills.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-slate-500">Matches your skills</span>
          {rec.matching_skills.map((s) => (
            <span key={s} className="chip border-blue-400/30 bg-blue-500/10 text-blue-200"><Check className="h-3 w-3" aria-hidden />{s}</span>
          ))}
        </div>
      )}

      <p className={`mt-3 text-sm leading-relaxed text-slate-300 ${expanded ? '' : 'line-clamp-3'}`}>{rec.explanation}</p>
      {longExplanation && (
        <button type="button" className="mt-1 text-xs text-violet-300 hover:underline" onClick={() => setExpanded((v) => !v)}>
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}

      {rec.potential_skills_to_learn.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <Lightbulb className="h-3.5 w-3.5 text-slate-500" aria-hidden />
          <span className="text-xs text-slate-500">Mentioned in the issue, could teach you</span>
          {rec.potential_skills_to_learn.map((s) => <span key={s} className="chip">{s}</span>)}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
          <span className="inline-flex items-center gap-1" title={`Created ${issue.created_at}`}>
            <Clock className="h-3.5 w-3.5" aria-hidden />opened {timeAgo(issue.created_at)}
          </span>
          <span title={`Updated ${issue.updated_at}`}>updated {timeAgo(issue.updated_at)}</span>
          <span className="inline-flex items-center gap-1"><MessageSquare className="h-3.5 w-3.5" aria-hidden />{issue.comments}</span>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs" aria-expanded={details}
            aria-controls={`scores-${issue.id}`} onClick={() => setDetails((v) => !v)}>
            Score details <ChevronDown className={`h-4 w-4 transition-transform ${details ? 'rotate-180' : ''}`} aria-hidden />
          </button>
          {issueUrl
            ? <a href={issueUrl} target="_blank" rel="noopener noreferrer" className="btn-primary px-3 py-1.5 text-xs">
                View on GitHub <ExternalLink className="h-3.5 w-3.5" aria-hidden />
              </a>
            : <span className="chip">link unavailable</span>}
        </div>
      </div>

      {details && <div id={`scores-${issue.id}`} className="mt-4"><ScoreBreakdown rec={rec} weights={weights} /></div>}
    </article>
  )
}
