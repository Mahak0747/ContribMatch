import { Link } from 'react-router-dom'

export function Logo() {
  return (
    <Link to="/" className="inline-flex items-center gap-2 font-semibold text-slate-100" aria-label="ContribMatch home" >
      <img src="/icon.png" className="h-13 w-13 rounded-lg object-contain" />
      <span>
        Contrib<span className="text-violet-300">Match</span>
      </span>
    </Link>
  )
}