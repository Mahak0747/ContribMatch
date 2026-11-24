import { Menu } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useSession } from '../context/sessionContext'
import { ApiStatus } from './ApiStatus'
import { Logo } from './Logo'

interface Props {
  variant: 'marketing' | 'app'
  onMenu?: () => void
}

export function Navbar({ variant, onMenu }: Props) {
  const { profile } = useSession()
  return (
    <header className="sticky top-0 z-30 border-b border-white/10 bg-navy-950/85 backdrop-blur">
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8" aria-label="Main">
        <div className="flex items-center gap-3">
          {variant === 'app' && (
            <button type="button" className="btn-ghost -ml-2 p-2 lg:hidden" onClick={onMenu} aria-label="Open navigation menu">
              <Menu className="h-5 w-5" aria-hidden />
            </button>
          )}
          <Logo />
        </div>
        <div className="flex items-center gap-4">
          <ApiStatus />
          {variant === 'marketing' && (
            <>
              <a href="#how" className="hidden text-sm text-slate-400 hover:text-slate-100 md:inline">How it works</a>
              <a href="#scoring" className="hidden text-sm text-slate-400 hover:text-slate-100 md:inline">Scoring</a>
              <Link to={profile ? '/dashboard' : '/profile'} className="btn-primary px-3 py-1.5">
                {profile ? 'Dashboard' : 'Get started'}
              </Link>
            </>
          )}
        </div>
      </nav>
    </header>
  )
}
