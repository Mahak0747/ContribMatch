import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { LoadingState } from './components/LoadingState'
import Dashboard from './pages/Dashboard'
import History from './pages/History'
import Landing from './pages/Landing'
import NotFound from './pages/NotFound'
import ProfileSetup from './pages/ProfileSetup'

// The charting library is large, so the analytics page is only downloaded when it is opened.
const Analytics = lazy(() => import('./pages/Analytics'))

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route element={<AppShell />}>
        <Route path="/profile" element={<ProfileSetup />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/analytics" element={<Suspense fallback={<LoadingState variant="charts" title="Loading analytics…" />}><Analytics /></Suspense>} />
        <Route path="/history" element={<History />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
