import { createContext, useContext } from 'react'
import type { SavedProfile } from '../types/api'

export interface Session {
  profile: SavedProfile | null
  runId: number | null
  setProfile: (p: SavedProfile | null) => void
  setRunId: (id: number | null) => void
  reset: () => void
}

export const SessionContext = createContext<Session | null>(null)

export function useSession(): Session {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used inside <SessionProvider>')
  return ctx
}
