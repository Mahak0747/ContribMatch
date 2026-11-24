import { afterEach, describe, expect, it, vi } from 'vitest'
import { resolveApiBaseUrl } from '../api/baseUrl'

afterEach(() => vi.restoreAllMocks())

describe('resolveApiBaseUrl', () => {
  it('defaults to the dev-proxy path when unset or blank', () => {
    expect(resolveApiBaseUrl(undefined)).toBe('/api')
    expect(resolveApiBaseUrl('')).toBe('/api')
    expect(resolveApiBaseUrl('   ')).toBe('/api')
  })

  it('uses the deployed backend URL and adds /api to a bare origin', () => {
    expect(resolveApiBaseUrl('https://contribmatch-api.onrender.com')).toBe('https://contribmatch-api.onrender.com/api')
    expect(resolveApiBaseUrl('https://contribmatch-api.onrender.com/')).toBe('https://contribmatch-api.onrender.com/api')
    expect(resolveApiBaseUrl('  https://contribmatch-api.onrender.com/api  ')).toBe('https://contribmatch-api.onrender.com/api')
  })

  it('removes trailing slashes and ignores query strings and fragments', () => {
    expect(resolveApiBaseUrl('https://api.example.com/api///')).toBe('https://api.example.com/api')
    expect(resolveApiBaseUrl('https://api.example.com/api?x=1#top')).toBe('https://api.example.com/api')
  })

  it('keeps a custom path and a custom port', () => {
    expect(resolveApiBaseUrl('https://example.com/backend/api')).toBe('https://example.com/backend/api')
    expect(resolveApiBaseUrl('http://localhost:8000')).toBe('http://localhost:8000/api')
  })

  it('accepts a same-origin path', () => {
    expect(resolveApiBaseUrl('/backend/')).toBe('/backend')
    expect(resolveApiBaseUrl('/')).toBe('/api')
  })

  it('falls back to /api (and says why) instead of crashing on invalid values', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(resolveApiBaseUrl('not a url')).toBe('/api')
    expect(resolveApiBaseUrl('ftp://example.com')).toBe('/api')
    expect(resolveApiBaseUrl('javascript:alert(1)')).toBe('/api')
    expect(err).toHaveBeenCalledTimes(3)
  })
})
