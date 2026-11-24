import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { FilterPanel } from '../components/FilterPanel'
import { RecommendationCard } from '../components/RecommendationCard'
import { SkillSelector } from '../components/SkillSelector'
import { DEFAULT_FILTERS, type Filters } from '../lib/filters'
import type { Recommendation } from '../types/api'
import { run } from './helpers'

const rec = run.recommendations[0]

describe('RecommendationCard', () => {
  it('shows every field the spec requires, from real backend data', () => {
    render(<RecommendationCard rec={rec} weights={run.weights} />)
    expect(screen.getByRole('heading', { name: rec.issue.title })).toBeInTheDocument()
    expect(screen.getByText(rec.issue.repo_full_name)).toBeInTheDocument()
    // the language chip and a matched skill can share a name (e.g. "Python"), so allow several matches
    expect(screen.getAllByText(rec.issue.repo_language!).length).toBeGreaterThan(0)
    for (const l of rec.issue.labels) expect(screen.getByText(l)).toBeInTheDocument()
    for (const s of rec.matching_skills) expect(screen.getAllByText(s).length).toBeGreaterThan(0)
    expect(screen.getByRole('img', { name: /overall match score/i })).toHaveAttribute('aria-label', expect.stringContaining(String(Math.round(rec.scores.overall))))
    expect(screen.getByText(rec.explanation)).toBeInTheDocument()
    expect(screen.getByTitle(`Created ${rec.issue.created_at}`)).toHaveTextContent(/opened .*ago/)
    expect(screen.getByTitle(`Updated ${rec.issue.updated_at}`)).toHaveTextContent(/updated .*ago/)
  })

  it('links to the original GitHub issue safely', () => {
    render(<RecommendationCard rec={rec} weights={run.weights} />)
    const link = screen.getByRole('link', { name: /view on github/i })
    expect(link).toHaveAttribute('href', rec.issue.url)
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })

  it('never renders a non-GitHub link', () => {
    const evil: Recommendation = { ...rec, issue: { ...rec.issue, url: 'javascript:alert(1)', repo_url: 'https://evil.example' } }
    render(<RecommendationCard rec={evil} weights={run.weights} />)
    expect(screen.queryByRole('link')).toBeNull()
    expect(screen.getByText('link unavailable')).toBeInTheDocument()
  })

  it('renders issue titles as text, not HTML', () => {
    const xss: Recommendation = { ...rec, issue: { ...rec.issue, title: '<img src=x onerror=alert(1)>' } }
    const { container } = render(<RecommendationCard rec={xss} weights={run.weights} />)
    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument()
  })

  it('toggles the score breakdown with the five weighted components', async () => {
    render(<RecommendationCard rec={rec} weights={run.weights} />)
    const btn = screen.getByRole('button', { name: /score details/i })
    expect(btn).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(btn)
    expect(btn).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByRole('meter')).toHaveLength(5)
    expect(screen.getByText('× 45%')).toBeInTheDocument()
    expect(screen.getByText(/estimates from labels/i)).toBeInTheDocument()
  })

  it('handles an issue with no labels, no skills, no language', () => {
    const bare: Recommendation = { ...rec, matching_skills: [], relevant_labels: [], potential_skills_to_learn: [],
      issue: { ...rec.issue, labels: [], repo_language: null, repo_stars: null } }
    render(<RecommendationCard rec={bare} weights={run.weights} />)
    expect(screen.queryByLabelText('Labels')).toBeNull()
    expect(screen.queryByText(/matches your skills/i)).toBeNull()
  })
})

describe('SkillSelector', () => {
  function Harness({ initial = [] as string[], onChange = vi.fn() }) {
    const [v, setV] = useState(initial)
    return <SkillSelector label="Skills" value={v} onChange={(n) => { setV(n); onChange(n) }} suggestions={['Python', 'Rust']} />
  }

  it('adds on Enter and comma, de-duplicates case-insensitively', async () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    const input = screen.getByLabelText('Skills')
    await userEvent.type(input, 'Python{Enter}')
    await userEvent.type(input, 'python{Enter}')
    await userEvent.type(input, 'Go, Docker,')
    expect(onChange).toHaveBeenLastCalledWith(['Python', 'Go', 'Docker'])
  })

  it('removes chips and toggles suggestions', async () => {
    render(<Harness initial={['Rust']} />)
    expect(screen.getByRole('button', { name: 'Rust', pressed: true })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Remove Rust' }))
    expect(screen.getByRole('button', { name: 'Rust', pressed: false })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Python' }))
    expect(screen.getByRole('button', { name: 'Remove Python' })).toBeInTheDocument()
  })

  it('rejects over-long items and caps the list', async () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    await userEvent.type(screen.getByLabelText('Skills'), `${'x'.repeat(51)}{Enter}`)
    expect(screen.getByRole('alert')).toHaveTextContent(/at most 50/)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('adds a pending draft on blur', async () => {
    const onChange = vi.fn()
    render(<Harness onChange={onChange} />)
    await userEvent.type(screen.getByLabelText('Skills'), 'Kotlin')
    await userEvent.tab()
    expect(onChange).toHaveBeenCalledWith(['Kotlin'])
  })
})

describe('FilterPanel', () => {
  function Harness() {
    const [f, setF] = useState<Filters>(DEFAULT_FILTERS)
    return <FilterPanel filters={f} onChange={setF} onReset={() => setF(DEFAULT_FILTERS)} languages={['Go', 'Python']} labels={['bug']} shown={3} total={5} />
  }
  it('reset is disabled until something changes, then restores defaults', async () => {
    render(<Harness />)
    const panel = within(screen.getByRole('region', { name: /filters/i }))
    const reset = panel.getAllByRole('button', { name: /reset filters/i })[0]
    expect(reset).toBeDisabled()
    await userEvent.selectOptions(panel.getAllByLabelText('Repository language')[0], 'Python')
    expect(reset).toBeEnabled()
    await userEvent.click(reset)
    expect(panel.getAllByLabelText('Repository language')[0]).toHaveValue('')
  })
})
