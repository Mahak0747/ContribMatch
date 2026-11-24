import type { Recommendation } from '../types/api'

const ROWS = [
  { key: 'semantic_similarity', weightKey: 'semantic', label: 'Semantic similarity', hint: 'Meaning-level similarity between your profile and the issue (local embedding model)' },
  { key: 'skill_compatibility', weightKey: 'skill', label: 'Skill compatibility', hint: 'Your skills and languages found in the issue title, labels or text' },
  { key: 'experience_compatibility', weightKey: 'experience', label: 'Experience fit', hint: 'Estimated difficulty (from labels, length, comments) vs. your level' },
  { key: 'repository_activity', weightKey: 'activity', label: 'Repository activity', hint: 'How recently the repository and issue were updated, plus stars' },
  { key: 'beginner_friendliness', weightKey: 'beginner', label: 'Beginner friendliness', hint: 'Estimated from labels like "good first issue" and the description' },
] as const

interface Props {
  rec: Recommendation
  weights: Record<string, number>
}

export function ScoreBreakdown({ rec, weights }: Props) {
  const { scores } = rec
  return (
    <div className="rounded-lg border border-white/10 bg-navy-950/50 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h4 className="text-sm font-semibold text-slate-100">Score breakdown</h4>
        <span className="font-mono text-xs text-slate-400">overall {scores.overall.toFixed(1)} / 100</span>
      </div>
      <ul className="space-y-3">
        {ROWS.map((r) => {
          const value = scores[r.key]
          const weight = weights[r.weightKey]
          return (
            <li key={r.key} title={r.hint}>
              <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                <span className="text-slate-300">
                  {r.label}
                  {weight != null && <span className="ml-1.5 font-mono text-slate-500">× {Math.round(weight * 100)}%</span>}
                </span>
                <span className="font-mono text-slate-200">{value.toFixed(1)}</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-white/10" role="meter" aria-label={r.label}
                aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value)}>
                <div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500 transition-[width] duration-500"
                  style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
              </div>
            </li>
          )
        })}
      </ul>
      <p className="mt-4 text-xs leading-relaxed text-slate-500">
        {rec.difficulty_signals.length > 0
          ? <>Difficulty estimate based on: {rec.difficulty_signals.join('; ')}.</>
          : <>No difficulty signals were found for this issue, so its experience fit is a neutral 50.</>}
        {' '}Experience fit and beginner friendliness are estimates from labels and issue text, not data GitHub provides.
        Raw cosine similarity: <span className="font-mono">{rec.cosine_similarity.toFixed(3)}</span>.
      </p>
    </div>
  )
}
