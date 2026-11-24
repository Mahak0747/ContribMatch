import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import * as api from '../api/endpoints'
import App from '../App'
import Dashboard from '../pages/Dashboard'
import { analytics, history, profile, renderApp, run, seedSession } from './helpers'

vi.mock('../api/endpoints')
const m = vi.mocked(api)

beforeEach(() => {
  vi.resetAllMocks()
  m.getHealth.mockResolvedValue({ status: 'ok', app: 'x', version: '1', environment: 'test', database: 'ok' })
})

describe('Dashboard', () => {
  it('asks for a profile when there is none and calls no recommendation API', () => {
    renderApp(<Dashboard />)
    expect(screen.getByText(/create a profile to get recommendations/i)).toBeInTheDocument()
    expect(m.createRecommendations).not.toHaveBeenCalled()
    expect(m.getRecommendation).not.toHaveBeenCalled()
  })

  it('creates recommendations exactly once for a saved profile (even under StrictMode) and shows real results', async () => {
    seedSession({ profile })
    m.createRecommendations.mockResolvedValue(run)
    renderApp(<Dashboard />)
    expect(screen.getByRole('status')).toHaveTextContent(/searching github/i)
    expect(await screen.findByRole('heading', { name: run.recommendations[0].issue.title })).toBeInTheDocument()
    expect(m.createRecommendations).toHaveBeenCalledTimes(1)
    expect(m.createRecommendations).toHaveBeenCalledWith(profile.id, 10)
    expect(screen.getAllByRole('article')).toHaveLength(run.recommendations.length)
    expect(JSON.parse(localStorage.getItem('contribmatch.session.v1')!).runId).toBe(run.id)
    expect(screen.getByText(/issues? analysed/i)).toHaveTextContent(String(run.issues_analyzed))
  })

  it('reopens a stored run via GET instead of generating a new one', async () => {
    seedSession({ profile, runId: run.id })
    m.getRecommendation.mockResolvedValue(run)
    renderApp(<Dashboard />)
    expect(await screen.findAllByRole('article')).toHaveLength(run.recommendations.length)
    expect(m.getRecommendation).toHaveBeenCalledWith(run.id)
    expect(m.createRecommendations).not.toHaveBeenCalled()
  })

  it('falls back to generating when the stored run no longer exists', async () => {
    seedSession({ profile, runId: 999 })
    m.getRecommendation.mockRejectedValue(new ApiError('gone', { status: 404, code: 'not_found' }))
    m.createRecommendations.mockResolvedValue(run)
    renderApp(<Dashboard />)
    expect(await screen.findAllByRole('article')).toBeTruthy()
    expect(m.createRecommendations).toHaveBeenCalledTimes(1)
  })

  it('shows a rate-limit error with a hint and retries on demand', async () => {
    seedSession({ profile })
    m.createRecommendations.mockRejectedValueOnce(new ApiError('GitHub API rate limit reached.', { status: 429, code: 'rate_limited', retryAfter: 30 }))
    m.createRecommendations.mockResolvedValueOnce(run)
    renderApp(<Dashboard />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/rate limit/i)
    expect(alert).toHaveTextContent(/30 seconds/)
    await userEvent.click(within(alert).getByRole('button', { name: /try again/i }))
    expect(await screen.findAllByRole('article')).toBeTruthy()
    expect(m.createRecommendations).toHaveBeenCalledTimes(2)
  })

  it('shows a backend-unreachable error', async () => {
    seedSession({ profile })
    m.createRecommendations.mockRejectedValue(new ApiError('Cannot reach the ContribMatch backend.', { code: 'network_error' }))
    renderApp(<Dashboard />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/uvicorn/)
  })

  it('shows an empty state with warnings when GitHub returned nothing', async () => {
    seedSession({ profile })
    m.createRecommendations.mockResolvedValue({ ...run, recommendations: [], issues_analyzed: 0, warnings: ['No open GitHub issues matched the search.'] })
    renderApp(<Dashboard />)
    expect(await screen.findByText(/no matching issues found/i)).toBeInTheDocument()
    expect(screen.getByText(/no open github issues matched/i)).toBeInTheDocument()
  })

  it('filters and sorts client-side, with an empty-filter state and reset', async () => {
    seedSession({ profile })
    m.createRecommendations.mockResolvedValue(run)
    renderApp(<Dashboard />)
    await screen.findAllByRole('article')
    const search = screen.getAllByLabelText('Search results')[0]
    await userEvent.type(search, 'pytorch')
    expect(screen.getAllByRole('article')).toHaveLength(1)
    await userEvent.clear(search)
    await userEvent.type(search, 'zzzz')
    expect(screen.getByText(/no recommendations match these filters/i)).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: /^reset filters$/i }).at(-1)!)
    expect(screen.getAllByRole('article')).toHaveLength(run.recommendations.length)
    await userEvent.selectOptions(screen.getAllByLabelText('Sort by')[0], 'beginner_friendliness')
    const scores = screen.getAllByRole('article').map((a) => a)
    expect(scores).toHaveLength(run.recommendations.length)
  })

  it('refresh requests a new run with the chosen count', async () => {
    seedSession({ profile })
    m.createRecommendations.mockResolvedValue(run)
    renderApp(<Dashboard />)
    await screen.findAllByRole('article')
    await userEvent.selectOptions(screen.getByLabelText('Show'), '20')
    await userEvent.click(screen.getByRole('button', { name: /refresh/i }))
    await waitFor(() => expect(m.createRecommendations).toHaveBeenLastCalledWith(profile.id, 20))
    expect(await screen.findAllByRole('article')).toBeTruthy()
  })
})

describe('Analytics', () => {
  it('shows the empty state when no runs exist', async () => {
    m.getAnalytics.mockResolvedValue({ ...analytics, totals: { ...analytics.totals, recommendation_runs: 0 } })
    renderApp(<App />, '/analytics')
    expect(await screen.findByText(/no analytics yet/i)).toBeInTheDocument()
  })

  it('renders backend totals and chart cards (no hard-coded numbers)', async () => {
    m.getAnalytics.mockResolvedValue(analytics)
    renderApp(<App />, '/analytics')
    expect(await screen.findByText('Recommendation runs')).toBeInTheDocument()
    const runs = screen.getByText('Recommendation runs').nextElementSibling
    expect(runs).toHaveTextContent(String(analytics.totals.recommendation_runs))
    expect(screen.getByRole('region', { name: /recommendation score distribution/i })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: /skill-match distribution/i })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: /requested domains/i })).toBeInTheDocument()
  })

  it('shows an error and retries', async () => {
    // (StrictMode runs the mount effect twice in tests, so use a persistent failure, then switch to success)
    m.getAnalytics.mockRejectedValue(new ApiError('boom', { status: 500, code: 'internal_error' }))
    renderApp(<App />, '/analytics')
    const retry = await screen.findByRole('button', { name: /try again/i })
    expect(screen.getByRole('alert')).toHaveTextContent('boom')
    m.getAnalytics.mockResolvedValue(analytics)
    await userEvent.click(retry)
    expect(await screen.findByText('Recommendation runs')).toBeInTheDocument()
  })
})

describe('History', () => {
  it('lists runs and opens one in the dashboard', async () => {
    m.getHistory.mockResolvedValue(history)
    m.getRecommendation.mockResolvedValue(run)
    renderApp(<App />, '/history')
    const first = history.items[0]
    expect(await screen.findByText(`Run #${first.id}`, { exact: false })).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: 'Open' })[0])
    await waitFor(() => expect(m.getRecommendation).toHaveBeenCalledWith(first.id))
    expect(await screen.findByRole('heading', { name: /recommended issues/i })).toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    m.getHistory.mockResolvedValue({ total: 0, limit: 10, offset: 0, items: [] })
    renderApp(<App />, '/history')
    expect(await screen.findByText(/no history yet/i)).toBeInTheDocument()
  })

  it('pages with older/newer', async () => {
    m.getHistory.mockResolvedValue({ ...history, total: 25 })
    renderApp(<App />, '/history')
    await screen.findByText(/of 25/)
    await userEvent.click(screen.getByRole('button', { name: /older/i }))
    await waitFor(() => expect(m.getHistory).toHaveBeenLastCalledWith(10, 10))
  })
})

describe('Profile setup', () => {
  it('blocks an empty profile client-side without calling the API', async () => {
    renderApp(<App />, '/profile')
    await userEvent.click(screen.getByRole('button', { name: /save profile/i }))
    expect(screen.getByRole('alert')).toHaveTextContent(/add at least one/i)
    expect(m.saveProfile).not.toHaveBeenCalled()
  })

  it('saves a profile, stores it and lands on the dashboard which generates recommendations', async () => {
    m.saveProfile.mockResolvedValue(profile)
    m.createRecommendations.mockResolvedValue(run)
    renderApp(<App />, '/profile')
    await userEvent.type(screen.getByLabelText('Technical skills'), 'Python{Enter}')
    await userEvent.click(screen.getByLabelText(/intermediate/i))
    await userEvent.click(screen.getByRole('button', { name: /save profile/i }))
    await waitFor(() => expect(m.saveProfile).toHaveBeenCalledTimes(1))
    expect(m.saveProfile.mock.calls[0][0]).toMatchObject({ skills: ['Python'], experience_level: 'intermediate' })
    expect(await screen.findAllByRole('article')).toBeTruthy()
    expect(JSON.parse(localStorage.getItem('contribmatch.session.v1')!).profile.id).toBe(profile.id)
  })

  it('shows backend validation errors next to the field', async () => {
    m.saveProfile.mockRejectedValue(new ApiError('Invalid request data', { status: 422, code: 'validation_error', details: [{ field: 'body.skills', message: 'at most 30 items are allowed' }] }))
    renderApp(<App />, '/profile')
    await userEvent.type(screen.getByLabelText('Technical skills'), 'Python{Enter}')
    await userEvent.click(screen.getByRole('button', { name: /save profile/i }))
    expect(await screen.findByText(/at most 30 items/)).toBeInTheDocument()
  })
})

describe('Navigation & shell', () => {
  function Shell() {
    return <Routes><Route path="*" element={<App />} /></Routes>
  }

  it('landing page has working CTAs and shows no invented statistics', () => {
    renderApp(<Shell />, '/')
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
    const cta = screen.getAllByRole('link', { name: /build your profile/i })[0]
    expect(cta).toHaveAttribute('href', '/profile')
    expect(screen.queryByText(/\d+\s?\+?\s?(developers|users|stars|issues matched)/i)).toBeNull()
    expect(screen.getByText(/initial design weights/i)).toBeInTheDocument()
  })

  it('sidebar links navigate between pages', async () => {
    m.getAnalytics.mockResolvedValue(analytics)
    m.getHistory.mockResolvedValue(history)
    renderApp(<Shell />, '/profile')
    const side = screen.getByRole('complementary', { name: /sidebar/i })
    await userEvent.click(within(side).getByRole('link', { name: /analytics/i }))
    expect(await screen.findByRole('heading', { name: 'Analytics' })).toBeInTheDocument()
    await userEvent.click(within(side).getByRole('link', { name: /history/i }))
    expect(await screen.findByRole('heading', { name: 'History' })).toBeInTheDocument()
  })

  it('mobile menu opens, closes with Escape and via the backdrop', async () => {
    renderApp(<Shell />, '/profile')
    await userEvent.click(screen.getByRole('button', { name: /open navigation menu/i }))
    expect(screen.getByRole('dialog', { name: /navigation menu/i })).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: /open navigation menu/i }))
    await userEvent.click(screen.getByRole('button', { name: /close navigation menu/i }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('unknown routes show a 404 page', () => {
    renderApp(<Shell />, '/nope')
    expect(screen.getByText(/page not found/i)).toBeInTheDocument()
  })

  it('API status reflects health: online and offline', async () => {
    renderApp(<Shell />, '/')
    expect((await screen.findAllByText('API online')).length).toBeGreaterThan(0)
  })

  it('API status shows offline when the backend is unreachable', async () => {
    m.getHealth.mockRejectedValue(new ApiError('down', { code: 'network_error' }))
    renderApp(<Shell />, '/')
    expect((await screen.findAllByText('API offline')).length).toBeGreaterThan(0)
  })

  it('"forget profile" clears the stored session', async () => {
    seedSession({ profile, runId: 1 })
    renderApp(<Shell />, '/profile')
    await userEvent.click(screen.getByRole('button', { name: /forget profile/i }))
    expect(JSON.parse(localStorage.getItem('contribmatch.session.v1')!)).toEqual({ profile: null, runId: null })
  })
})
