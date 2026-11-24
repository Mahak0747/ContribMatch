import { useCallback, useMemo, useState, type ReactNode } from 'react'
import type { SavedProfile } from '../types/api'
import { SessionContext, type Session } from './sessionContext'

const KEY = 'contribmatch.session.v1'

interface Stored { profile: SavedProfile | null; runId: number | null }

function isProfile(x: unknown): x is SavedProfile {
  const p = x as SavedProfile
  return typeof p === 'object' && p !== null && typeof p.id === 'number' && Array.isArray(p.skills) &&
    Array.isArray(p.domains) && Array.isArray(p.preferred_languages) && Array.isArray(p.learning_interests) &&
    typeof p.experience_level === 'string'
}

function load(): Stored {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { profile: null, runId: null }
    const parsed = JSON.parse(raw) as Partial<Stored>
    return {
      profile: isProfile(parsed.profile) ? parsed.profile : null,
      runId: typeof parsed.runId === 'number' ? parsed.runId : null,
    }
  } catch {
    return { profile: null, runId: null }
  }
}

function save(s: Stored) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s))
  } catch {
    /* storage unavailable (private mode / quota): the app still works for this tab */
  }
}

/** Remembers the saved profile and the last recommendation run in this browser only. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Stored>(load)

  const update = useCallback((next: Stored) => {
    setState(next)
    save(next)
  }, [])

  const value = useMemo<Session>(() => ({
    profile: state.profile,
    runId: state.runId,
    setProfile: (profile) => update({ profile, runId: profile?.id === state.profile?.id ? state.runId : null }),
    setRunId: (runId) => update({ ...state, runId }),
    reset: () => update({ profile: null, runId: null }),
  }), [state, update])

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}
