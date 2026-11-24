import { scoreTone, type Tone } from '../lib/format'

const STROKE: Record<Tone, string> = { high: 'stroke-violet-400', mid: 'stroke-blue-400', low: 'stroke-slate-500' }

export function ScoreRing({ score, size = 56 }: { score: number; size?: number }) {
  const r = (size - 8) / 2
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(100, score))
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img"
      aria-label={`Overall match score ${Math.round(score)} out of 100`}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={4} className="stroke-white/10" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={4} strokeLinecap="round"
          className={`${STROKE[scoreTone(score)]} transition-[stroke-dashoffset] duration-700`}
          strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)} />
      </svg>
      <span className="absolute inset-0 grid place-items-center font-mono text-sm font-semibold text-slate-100">
        {Math.round(score)}
      </span>
    </div>
  )
}
