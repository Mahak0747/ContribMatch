import type { ApiError } from '../api/client'

/** Friendly follow-up advice for the error codes the backend can return. */
export function errorHint(error: ApiError): string | null {
  switch (error.code) {
    case 'rate_limited': {
      const wait = error.retryAfter ? ` Try again in about ${error.retryAfter} seconds.` : ''
      return `GitHub is limiting requests.${wait} Setting GITHUB_TOKEN in the backend .env raises the limit.`
    }
    case 'network_error':
      return 'Start the backend with: uvicorn app.main:app --port 8000 (from the backend folder).'
    case 'service_unavailable':
      return 'This is usually temporary. If it mentions the model, the first run needs internet access to download it.'
    case 'upstream_timeout':
    case 'timeout':
      return 'GitHub or the model took too long to respond. Trying again often works.'
    default:
      return null
  }
}
