import { AxiosError, AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'
import { ApiError, fieldErrors, toApiError } from '../api/client'
import { DEFAULT_FILTERS, filterAndSort, filterOptions, isFiltered } from '../lib/filters'
import { errorHint } from '../lib/errors'
import { formatCompact, safeGithubUrl, scoreTone, timeAgo } from '../lib/format'
import { run } from './helpers'

const recs = run.recommendations

describe('filterAndSort', () => {
  it('keeps backend order by default and never mutates input', () => {
    const copy = [...recs]
    expect(filterAndSort(recs, DEFAULT_FILTERS).map((r) => r.rank)).toEqual(recs.map((r) => r.rank).sort((a, b) => a - b))
    expect(recs).toEqual(copy)
  })
  it('filters by min score, language, label and text', () => {
    const top = Math.max(...recs.map((r) => r.scores.overall))
    expect(filterAndSort(recs, { ...DEFAULT_FILTERS, minScore: top }).length).toBeGreaterThanOrEqual(1)
    expect(filterAndSort(recs, { ...DEFAULT_FILTERS, minScore: 101 })).toEqual([])
    expect(filterAndSort(recs, { ...DEFAULT_FILTERS, language: 'Python' }).every((r) => r.issue.repo_language === 'Python')).toBe(true)
    expect(filterAndSort(recs, { ...DEFAULT_FILTERS, label: 'GOOD FIRST ISSUE' }).every((r) => r.issue.labels.includes('good first issue'))).toBe(true)
    expect(filterAndSort(recs, { ...DEFAULT_FILTERS, query: 'pytorch' }).length).toBeGreaterThan(0)
    expect(filterAndSort(recs, { ...DEFAULT_FILTERS, query: 'zzz-no-match' })).toEqual([])
  })
  it('sorts by chosen key, descending', () => {
    const sorted = filterAndSort(recs, { ...DEFAULT_FILTERS, sort: 'beginner_friendliness' })
    const v = sorted.map((r) => r.scores.beginner_friendliness)
    expect(v).toEqual([...v].sort((a, b) => b - a))
    const byDate = filterAndSort(recs, { ...DEFAULT_FILTERS, sort: 'updated' })
    const d = byDate.map((r) => new Date(r.issue.updated_at).getTime())
    expect(d).toEqual([...d].sort((a, b) => b - a))
  })
  it('exposes options and detects active filters', () => {
    const o = filterOptions(recs)
    expect(o.languages).toContain('Python')
    expect(o.labels).toContain('good first issue')
    expect(isFiltered(DEFAULT_FILTERS)).toBe(false)
    expect(isFiltered({ ...DEFAULT_FILTERS, minScore: 5 })).toBe(true)
  })
})

describe('format helpers', () => {
  const now = new Date('2026-11-21T00:00:00Z')
  it('timeAgo', () => {
    expect(timeAgo('2026-11-18T00:00:00Z', now)).toBe('3 days ago')
    expect(timeAgo('2026-11-20T23:59:30Z', now)).toBe('just now')
    expect(timeAgo(null)).toBe('unknown')
    expect(timeAgo('not-a-date')).toBe('unknown')
  })
  it('safeGithubUrl only allows https github.com', () => {
    expect(safeGithubUrl('https://github.com/o/r/issues/1')).toBe('https://github.com/o/r/issues/1')
    for (const bad of ['javascript:alert(1)', 'http://github.com/x', 'https://evil.com/github.com', 'https://github.com.evil.io/x', 'nonsense', '']) {
      expect(safeGithubUrl(bad)).toBeNull()
    }
  })
  it('tone and compact numbers', () => {
    expect([scoreTone(90), scoreTone(50), scoreTone(10)]).toEqual(['high', 'mid', 'low'])
    expect(formatCompact(12000)).toBe('12K')
    expect(formatCompact(null)).toBe('—')
  })
})

function axiosErr(status: number | null, data?: unknown, headers: Record<string, string> = {}, code?: string) {
  const e = new AxiosError('x', code)
  if (status !== null) e.response = { status, data, headers: new AxiosHeaders(headers), statusText: '', config: { headers: new AxiosHeaders() } }
  return e
}

describe('toApiError', () => {
  it('parses the backend error body', () => {
    const e = toApiError(axiosErr(429, { error: { code: 'rate_limited', message: 'slow down' } }, { 'retry-after': '42' }))
    expect(e).toMatchObject({ status: 429, code: 'rate_limited', message: 'slow down', retryAfter: 42 })
    expect(errorHint(e)).toContain('42 seconds')
    expect(errorHint(e)).toContain('GITHUB_TOKEN')
  })
  it('handles non-standard bodies, timeouts and network failures', () => {
    expect(toApiError(axiosErr(500, '<html>')).code).toBe('bad_response')
    expect(toApiError(axiosErr(null, undefined, {}, 'ECONNABORTED')).code).toBe('timeout')
    const net = toApiError(axiosErr(null))
    expect(net.code).toBe('network_error')
    expect(errorHint(net)).toContain('uvicorn')
    expect(toApiError(new Error('boom')).message).toBe('boom')
    const same = new ApiError('a')
    expect(toApiError(same)).toBe(same)
  })
  it('extracts field errors from 422 details', () => {
    const e = new ApiError('Invalid', { code: 'validation_error', details: [{ field: 'body.skills', message: 'too many' }, { field: 'body.skills', message: 'dup' }] })
    expect(fieldErrors(e)).toEqual({ skills: 'too many' })
    expect(fieldErrors(new ApiError('x'))).toEqual({})
  })
})
