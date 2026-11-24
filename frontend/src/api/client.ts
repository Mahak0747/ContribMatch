import axios, { AxiosError } from 'axios'
import type { ApiErrorBody } from '../types/api'
import { resolveApiBaseUrl } from './baseUrl'

/**
 * In development '/api' is proxied to FastAPI by the Vite dev server. In production (Vercel) set
 * VITE_API_BASE_URL to the deployed backend, for example https://contribmatch-api.onrender.com/api
 */
export const API_BASE_URL: string = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL)

if (import.meta.env.PROD && API_BASE_URL === '/api') {
  // A production build that still points at '/api' would call the static host itself, which has no API.
  console.warn('ContribMatch: VITE_API_BASE_URL was not set at build time, so API calls go to "/api" on this host.')
}

export const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
  headers: { Accept: 'application/json' },
})

export class ApiError extends Error {
  status: number | null
  code: string
  details: unknown
  retryAfter: number | null

  constructor(message: string, opts: { status?: number | null; code?: string; details?: unknown; retryAfter?: number | null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = opts.status ?? null
    this.code = opts.code ?? 'unknown_error'
    this.details = opts.details
    this.retryAfter = opts.retryAfter ?? null
  }
}

function isErrorBody(x: unknown): x is ApiErrorBody {
  return typeof x === 'object' && x !== null && 'error' in x &&
    typeof (x as ApiErrorBody).error?.message === 'string'
}

/** Normalise anything thrown by axios into an ApiError with a user-presentable message. */
export function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e
  if (axios.isAxiosError(e)) {
    const err = e as AxiosError
    if (err.response) {
      const data = err.response.data
      const retry = Number(err.response.headers?.['retry-after'])
      if (isErrorBody(data)) {
        return new ApiError(data.error.message, {
          status: err.response.status, code: data.error.code, details: data.error.details,
          retryAfter: Number.isFinite(retry) ? retry : null,
        })
      }
      return new ApiError(`The server returned an unexpected response (HTTP ${err.response.status}).`,
        { status: err.response.status, code: 'bad_response' })
    }
    if (err.code === 'ECONNABORTED') {
      return new ApiError('The request took too long. The backend may still be loading the model; try again.', { code: 'timeout' })
    }
    return new ApiError('Cannot reach the ContribMatch backend. Make sure it is running on port 8000.', { code: 'network_error' })
  }
  return new ApiError(e instanceof Error ? e.message : 'Something went wrong.')
}

/** Field-level messages from a 422 response, keyed by the last path segment (e.g. "skills"). */
export function fieldErrors(err: ApiError): Record<string, string> {
  const out: Record<string, string> = {}
  if (err.code === 'validation_error' && Array.isArray(err.details)) {
    for (const d of err.details as { field?: string; message?: string }[]) {
      const key = String(d.field ?? '').split('.').pop() ?? ''
      if (key && d.message && !out[key]) out[key] = d.message
    }
  }
  return out
}
