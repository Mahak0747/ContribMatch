import { GitPullRequestArrow } from 'lucide-react'
import { Link } from 'react-router-dom'

export function Logo() {
  return (
    <Link to="/" className="inline-flex items-center gap-2 font-semibold text-slate-100" aria-label="ContribMatch home">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 text-white">
        <GitPullRequestArrow className="h-4 w-4" aria-hidden />
      </span>
      <span>Contrib<span className="text-violet-300">Match</span></span>
    </Link>
  )
}
