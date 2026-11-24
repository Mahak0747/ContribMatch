import type { Recommendation } from '../types/api'

export type SortKey =
  | 'overall' | 'semantic_similarity' | 'skill_compatibility' | 'beginner_friendliness'
  | 'repository_activity' | 'updated' | 'created'

export interface Filters {
  query: string
  language: string
  label: string
  minScore: number
  sort: SortKey
}

export const DEFAULT_FILTERS: Filters = { query: '', language: '', label: '', minScore: 0, sort: 'overall' }

export const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'overall', label: 'Best overall match' },
  { value: 'semantic_similarity', label: 'Semantic similarity' },
  { value: 'skill_compatibility', label: 'Skill compatibility' },
  { value: 'beginner_friendliness', label: 'Beginner friendliness' },
  { value: 'repository_activity', label: 'Repository activity' },
  { value: 'updated', label: 'Recently updated' },
  { value: 'created', label: 'Recently created' },
]

export function isFiltered(f: Filters): boolean {
  return f.query !== '' || f.language !== '' || f.label !== '' || f.minScore > 0 || f.sort !== 'overall'
}

export function filterAndSort(recs: Recommendation[], f: Filters): Recommendation[] {
  const q = f.query.trim().toLowerCase()
  const out = recs.filter((r) => {
    if (r.scores.overall < f.minScore) return false
    if (f.language && (r.issue.repo_language ?? '') !== f.language) return false
    if (f.label && !r.issue.labels.some((l) => l.toLowerCase() === f.label.toLowerCase())) return false
    if (q) {
      const hay = `${r.issue.title} ${r.issue.repo_full_name} ${r.matching_skills.join(' ')} ${r.issue.labels.join(' ')}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
  const key = (r: Recommendation): number => {
    switch (f.sort) {
      case 'updated': return new Date(r.issue.updated_at).getTime()
      case 'created': return new Date(r.issue.created_at).getTime()
      default: return r.scores[f.sort]
    }
  }
  // stable: ties keep the backend's rank order
  return [...out].sort((a, b) => key(b) - key(a) || a.rank - b.rank)
}

export function filterOptions(recs: Recommendation[]) {
  const languages = [...new Set(recs.map((r) => r.issue.repo_language).filter((x): x is string => !!x))].sort()
  const labels = [...new Set(recs.flatMap((r) => r.issue.labels.map((l) => l.toLowerCase())))].sort()
  return { languages, labels }
}
