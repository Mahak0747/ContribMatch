import { ArrowRight, Cpu, Gauge, GitPullRequestArrow, Search, SlidersHorizontal, UserCog } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Navbar } from '../components/Navbar'
import { useSession } from '../context/sessionContext'

// The weights of the ranking formula (documented in the backend README). Static documentation, not data.
const FORMULA = [
  { name: 'Semantic similarity', pct: 45, color: 'bg-violet-500', text: 'Meaning-level match between your profile and the issue, from a pretrained embedding model running locally.' },
  { name: 'Skill compatibility', pct: 20, color: 'bg-blue-500', text: 'Your skills and languages literally found in the issue title, labels or text.' },
  { name: 'Experience fit', pct: 15, color: 'bg-indigo-400', text: 'Estimated difficulty (labels, length, discussion) against your level.' },
  { name: 'Repository activity', pct: 10, color: 'bg-sky-400', text: 'How recently the repo and issue were touched.' },
  { name: 'Beginner friendliness', pct: 10, color: 'bg-fuchsia-400', text: 'Signals like "good first issue" and a clear description.' },
]

const STEPS = [
  { icon: UserCog, title: 'Describe yourself', text: 'Skills, languages, domains, what you want to learn, and your experience level.' },
  { icon: Search, title: 'Discover real issues', text: 'The backend searches open GitHub issues (never pull requests) using your profile.' },
  { icon: Gauge, title: 'Rank and explain', text: 'Each issue gets five transparent scores and an explanation built from what was actually matched.' },
  { icon: GitPullRequestArrow, title: 'Contribute', text: 'Open the original issue on GitHub and start. Every run is saved so you can revisit it.' },
]

const HONEST = [
  { title: 'Pretrained, not trained', text: 'The embedding model (all-MiniLM-L6-v2) is a pretrained open model. The ranking formula is hand-designed. Nothing here is a model we trained.' },
  { title: 'Estimates are labelled', text: 'GitHub does not say how hard an issue is. Difficulty and beginner-friendliness are estimated from labels and issue text, and the score details say so.' },
  { title: 'Runs locally', text: 'No paid or hosted AI APIs. Your profile stays in your own backend and database.' },
]

export default function Landing() {
  const { profile } = useSession()
  const cta = profile ? '/dashboard' : '/profile'
  return (
    <div className="min-h-screen">
      <Navbar variant="marketing" />
      <main>
        <section className="relative overflow-hidden">
          <div className="grid-bg absolute inset-0" aria-hidden />
          <div className="relative mx-auto grid max-w-7xl gap-12 px-4 py-16 sm:px-6 sm:py-24 lg:grid-cols-[1.1fr_1fr] lg:items-center lg:px-8">
            <div className="animate-fade-up">
              <p className="font-mono text-xs uppercase tracking-widest text-violet-300">open-source contribution matching</p>
              <h1 className="mt-4 text-4xl font-semibold leading-[1.1] tracking-tight text-slate-50 sm:text-5xl">
                Find the open issues that fit <span className="bg-gradient-to-r from-blue-400 to-violet-400 bg-clip-text text-transparent">you</span>, not just your language.
              </h1>
              <p className="mt-5 max-w-xl text-lg text-slate-400">
                ContribMatch searches real GitHub issues and ranks them against your skills, experience and interests.
                Every recommendation shows the evidence behind its score.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to={cta} className="btn-primary px-5 py-2.5">{profile ? 'Open dashboard' : 'Build your profile'} <ArrowRight className="h-4 w-4" aria-hidden /></Link>
                <a href="#how" className="btn-secondary px-5 py-2.5">How it works</a>
              </div>
            </div>

            <div id="scoring" className="panel animate-fade-up scroll-mt-24 p-5 sm:p-6" style={{ animationDelay: '120ms' }}>
              <div className="flex items-center gap-2 font-mono text-xs text-slate-400"><SlidersHorizontal className="h-4 w-4" aria-hidden /> ranking formula</div>
              <div className="mt-4 flex h-3 overflow-hidden rounded-full" role="img" aria-label="Score weights: semantic 45, skill 20, experience 15, activity 10, beginner 10 percent">
                {FORMULA.map((f) => <div key={f.name} className={f.color} style={{ width: `${f.pct}%` }} />)}
              </div>
              <ul className="mt-5 space-y-3">
                {FORMULA.map((f) => (
                  <li key={f.name} className="grid grid-cols-[auto_1fr] gap-x-3">
                    <span className={`mt-1.5 h-2.5 w-2.5 rounded-sm ${f.color}`} aria-hidden />
                    <div>
                      <p className="text-sm text-slate-100"><span className="font-mono">{f.pct}%</span> {f.name}</p>
                      <p className="text-xs text-slate-500">{f.text}</p>
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-5 border-t border-white/10 pt-3 text-xs text-slate-500">Initial design weights, not learned parameters.</p>
            </div>
          </div>
        </section>

        <section id="how" className="scroll-mt-20 border-t border-white/10 bg-navy-900/40">
          <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
            <h2 className="text-2xl font-semibold text-slate-50">How it works</h2>
            <ol className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {STEPS.map(({ icon: Icon, title, text }, i) => (
                <li key={title} className="panel p-5">
                  <div className="flex items-center justify-between">
                    <span className="grid h-9 w-9 place-items-center rounded-lg bg-violet-500/15 text-violet-300"><Icon className="h-4 w-4" aria-hidden /></span>
                    <span className="font-mono text-xs text-slate-600">0{i + 1}</span>
                  </div>
                  <h3 className="mt-4 font-medium text-slate-100">{title}</h3>
                  <p className="mt-1 text-sm text-slate-400">{text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="border-t border-white/10">
          <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
            <div className="flex items-center gap-2 text-violet-300"><Cpu className="h-5 w-5" aria-hidden /><h2 className="text-2xl font-semibold text-slate-50">Honest by design</h2></div>
            <div className="mt-8 grid gap-4 md:grid-cols-3">
              {HONEST.map((h) => (
                <div key={h.title} className="rounded-xl border border-white/10 p-5">
                  <h3 className="font-medium text-slate-100">{h.title}</h3>
                  <p className="mt-2 text-sm text-slate-400">{h.text}</p>
                </div>
              ))}
            </div>
            <div className="mt-12 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-violet-400/20 bg-violet-500/5 p-6">
              <p className="text-lg text-slate-100">Ready to find your first (or next) contribution?</p>
              <Link to={cta} className="btn-primary px-5 py-2.5">{profile ? 'Open dashboard' : 'Build your profile'} <ArrowRight className="h-4 w-4" aria-hidden /></Link>
            </div>
          </div>
        </section>
      </main>
      <footer className="border-t border-white/10 py-6 text-center text-xs text-slate-600">ContribMatch · open-source issue recommendations</footer>
    </div>
  )
}
