import type { ReactNode } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { AnalyticsResponse, CountItem } from '../types/api'

const VIOLET = '#8b5cf6'
const BLUE = '#3b82f6'
const TICK = { fill: '#94a3b8', fontSize: 12 }
const TOOLTIP = {
  contentStyle: { background: '#0f1830', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, color: '#e2e8f0', fontSize: 12 },
  cursor: { fill: 'rgba(255,255,255,0.05)' },
  labelStyle: { color: '#cbd5e1' },
  itemStyle: { color: '#e2e8f0' },
}

function ChartCard({ title, subtitle, children, empty }: { title: string; subtitle?: string; children: ReactNode; empty: boolean }) {
  return (
    <section className="panel p-5" aria-label={title}>
      <h3 className="font-semibold text-slate-100">{title}</h3>
      {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      <div className="mt-4 h-60">
        {empty
          ? <div className="grid h-full place-items-center text-sm text-slate-500">No data yet</div>
          : children}
      </div>
    </section>
  )
}

function hasData(items: CountItem[]) {
  return items.some((i) => i.count > 0)
}

function Columns({ title, subtitle, data, color }: { title: string; subtitle?: string; data: CountItem[]; color: string }) {
  return (
    <ChartCard title={title} subtitle={subtitle} empty={!hasData(data)}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
          <XAxis dataKey="label" tick={TICK} tickLine={false} axisLine={false} />
          <YAxis allowDecimals={false} tick={TICK} tickLine={false} axisLine={false} />
          <Tooltip {...TOOLTIP} formatter={(v) => [v, 'Recommendations']} />
          <Bar dataKey="count" fill={color} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

function Rows({ title, subtitle, data, color, unit = 'Count' }: { title: string; subtitle?: string; data: CountItem[]; color: string; unit?: string }) {
  return (
    <ChartCard title={title} subtitle={subtitle} empty={!hasData(data)}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.06)" horizontal={false} />
          <XAxis type="number" allowDecimals={false} tick={TICK} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="label" width={96} tick={TICK} tickLine={false} axisLine={false}
            tickFormatter={(v: string) => (v.length > 14 ? `${v.slice(0, 13)}…` : v)} />
          <Tooltip {...TOOLTIP} formatter={(v) => [v, unit]} />
          <Bar dataKey="count" fill={color} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

const KPI = [
  ['recommendation_runs', 'Recommendation runs'],
  ['recommendations_generated', 'Recommendations generated'],
  ['issues_analyzed', 'Issues analysed'],
  ['unique_issues_recommended', 'Unique issues recommended'],
  ['profiles', 'Profiles saved'],
  ['cached_issues', 'Issues cached'],
] as const

const AVG = [
  ['overall', 'Overall'], ['semantic_similarity', 'Semantic similarity'], ['skill_compatibility', 'Skill compatibility'],
  ['experience_compatibility', 'Experience fit'], ['repository_activity', 'Repository activity'], ['beginner_friendliness', 'Beginner friendliness'],
] as const

export function AnalyticsCharts({ data }: { data: AnalyticsResponse }) {
  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {KPI.map(([k, label]) => (
          <div key={k} className="panel p-4">
            <dt className="text-xs text-slate-400">{label}</dt>
            <dd className="mt-1 font-mono text-2xl font-semibold text-slate-100">{data.totals[k].toLocaleString()}</dd>
          </div>
        ))}
      </dl>

      {data.average_scores && (
        <section className="panel p-5" aria-label="Average scores">
          <h3 className="font-semibold text-slate-100">Average scores across all recommendations</h3>
          <ul className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-2">
            {AVG.map(([k, label]) => {
              const v = data.average_scores![k]
              return (
                <li key={k}>
                  <div className="mb-1 flex justify-between text-xs"><span className="text-slate-300">{label}</span><span className="font-mono text-slate-200">{v.toFixed(1)}</span></div>
                  <div className="h-1.5 rounded-full bg-white/10"><div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500" style={{ width: `${v}%` }} /></div>
                </li>
              )
            })}
          </ul>
        </section>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Columns title="Recommendation score distribution" subtitle="Overall score (0–100) of every recommendation made" data={data.score_distribution} color={VIOLET} />
        <Columns title="Skill-match distribution" subtitle="Skill-compatibility score buckets" data={data.skill_compatibility_distribution} color={BLUE} />
        <Columns title="Matched skills per recommendation" subtitle="How many of your skills each recommended issue mentions" data={data.matching_skill_count_distribution} color={VIOLET} />
        <Rows title="Top matched skills" subtitle="Skills most often found in recommended issues" data={data.top_matching_skills} color={BLUE} unit="Recommendations" />
        <Rows title="Requested domains" subtitle="Domains from the profiles used for runs" data={data.requested_domains} color={VIOLET} unit="Runs" />
        <Rows title="Languages of recommended issues" subtitle="Primary language of each recommended repository" data={data.recommended_language_distribution} color={BLUE} unit="Recommendations" />
        <Rows title="Most common labels" subtitle="Labels on recommended issues" data={data.top_labels} color={VIOLET} unit="Recommendations" />
        <Rows title="Experience levels" subtitle="Level of the profile used for each run" data={data.experience_level_distribution} color={BLUE} unit="Runs" />
      </div>
    </div>
  )
}
