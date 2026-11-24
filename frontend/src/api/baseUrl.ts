/**
 * Work out the API base URL from the VITE_API_BASE_URL build-time variable.
 *
 *  - unset / empty      -> '/api' (development: the Vite dev server proxies it to the backend)
 *  - 'https://host'     -> 'https://host/api'   (a bare origin gets the '/api' prefix added)
 *  - 'https://host/api/'-> 'https://host/api'   (trailing slashes removed)
 *  - '/something'       -> kept as a same-origin path (for example behind a reverse proxy)
 *  - anything invalid   -> '/api', with a console error, rather than crashing the whole app
 *
 * VITE_* variables are embedded in the public JavaScript bundle, so only ever put the (public) backend URL
 * here, never a secret.
 */
export function resolveApiBaseUrl(raw: string | undefined): string {
  const value = (raw ?? '').trim()
  if (!value) return '/api'

  if (value.startsWith('/')) return value.replace(/\/+$/, '') || '/api'

  let url: URL
  try {
    url = new URL(value)
  } catch {
    console.error(`VITE_API_BASE_URL is not a valid URL ("${value}"). Falling back to "/api".`)
    return '/api'
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    console.error(`VITE_API_BASE_URL must start with http:// or https:// (got "${url.protocol}"). Falling back to "/api".`)
    return '/api'
  }
  const path = url.pathname.replace(/\/+$/, '')
  return `${url.origin}${path || '/api'}`
}
