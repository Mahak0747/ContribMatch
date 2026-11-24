import { useNavigate } from 'react-router-dom'
import { ProfileForm } from '../components/ProfileForm'
import { useSession } from '../context/sessionContext'

export default function ProfileSetup() {
  const { profile, setProfile } = useSession()
  const navigate = useNavigate()
  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-50">{profile ? 'Edit your profile' : 'Set up your developer profile'}</h1>
        <p className="mt-1 text-sm text-slate-400">
          {profile ? `Saved profile #${profile.id}. Saving changes creates a fresh set of recommendations.` : 'Tell us what you know and what you want to learn.'}
        </p>
      </header>
      <div className="grid gap-8 lg:grid-cols-[1fr_18rem]">
        <div className="panel p-5 sm:p-6">
          <ProfileForm initial={profile ?? undefined} onSaved={(p) => { setProfile(p); navigate('/dashboard') }} />
        </div>
        <aside className="panel h-fit p-5 text-sm text-slate-400" aria-label="How your profile is used">
          <h2 className="font-medium text-slate-100">How your profile is used</h2>
          <ul className="mt-3 list-disc space-y-2 pl-4 marker:text-violet-400">
            <li>The first two languages and the first domain shape the GitHub search.</li>
            <li>Your level picks the issue labels searched (for example <span className="font-mono text-xs">good first issue</span> for beginners).</li>
            <li>Skills, languages, domains and learning interests are embedded for semantic matching.</li>
            <li>Your level is judged separately, against an estimated issue difficulty.</li>
          </ul>
        </aside>
      </div>
    </div>
  )
}
