import { BarChart3, History, LayoutDashboard, LogOut, UserCog, X } from 'lucide-react'
import { useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import { useSession } from '../context/sessionContext'

const LINKS = [
  { to: '/dashboard', label: 'Recommendations', icon: LayoutDashboard },
  { to: '/profile', label: 'Profile', icon: UserCog },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/history', label: 'History', icon: History },
]

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const { profile, reset } = useSession()
  return (
    <div className="flex h-full flex-col gap-6">
      <ul className="space-y-1">
        {LINKS.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink to={to} onClick={onNavigate}
              className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${isActive ? 'bg-violet-500/15 text-violet-100' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'}`}>
              <Icon className="h-4 w-4" aria-hidden />{label}
            </NavLink>
          </li>
        ))}
      </ul>

      <div className="mt-auto space-y-3">
        <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs">
          <p className="mb-1 font-medium text-slate-200">Saved profile</p>
          {profile ? (
            <p className="text-slate-400">
              #{profile.id} · {profile.experience_level}<br />
              {profile.skills.length} skill{profile.skills.length === 1 ? '' : 's'}, {profile.preferred_languages.length} language{profile.preferred_languages.length === 1 ? '' : 's'}
            </p>
          ) : <p className="text-slate-500">None yet. Create one to get recommendations.</p>}
        </div>
        {profile && (
          <button type="button" className="btn-ghost w-full justify-start px-3 text-xs text-slate-400" onClick={() => { reset(); onNavigate?.() }}>
            <LogOut className="h-4 w-4" aria-hidden /> Forget profile in this browser
          </button>
        )}
      </div>
    </div>
  )
}

interface Props { open: boolean; onClose: () => void }

export function Sidebar({ open, onClose }: Props) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <>
      <aside className="sticky top-16 hidden h-[calc(100vh-4rem)] w-60 shrink-0 border-r border-white/10 p-4 lg:block" aria-label="Sidebar">
        <Nav />
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation menu">
          <button type="button" className="absolute inset-0 bg-black/60" aria-label="Close navigation menu" onClick={onClose} />
          <div className="animate-fade-up absolute inset-y-0 left-0 w-72 max-w-[85vw] border-r border-white/10 bg-navy-900 p-4">
            <button type="button" className="btn-ghost mb-4 ml-auto p-2" onClick={onClose} aria-label="Close menu"><X className="h-5 w-5" aria-hidden /></button>
            <Nav onNavigate={onClose} />
          </div>
        </div>
      )}
    </>
  )
}
