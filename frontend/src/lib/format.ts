const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

/** "3 days ago" style text; "unknown" for missing or invalid dates. */
export function timeAgo(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return 'unknown'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return 'unknown'
  const sec = Math.round((t - now.getTime()) / 1000)
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 31_536_000], ['month', 2_592_000], ['week', 604_800], ['day', 86_400], ['hour', 3_600], ['minute', 60],
  ]
  for (const [unit, s] of units) {
    if (Math.abs(sec) >= s) return rtf.format(Math.round(sec / s), unit)
  }
  return 'just now'
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return 'unknown'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? 'unknown' : d.toLocaleDateString('en', { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatCompact(n: number | null | undefined): string {
  return n == null ? '—' : new Intl.NumberFormat('en', { notation: 'compact' }).format(n)
}

export type Tone = 'high' | 'mid' | 'low'
export function scoreTone(score: number): Tone {
  return score >= 70 ? 'high' : score >= 40 ? 'mid' : 'low'
}

/** Only ever link to github.com over https; anything else is rendered as plain text. */
export function safeGithubUrl(url: string): string | null {
  try {
    const u = new URL(url)
    return u.protocol === 'https:' && (u.hostname === 'github.com' || u.hostname === 'www.github.com') ? u.toString() : null
  } catch {
    return null
  }
}
