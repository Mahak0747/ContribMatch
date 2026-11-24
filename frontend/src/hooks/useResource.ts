import { useCallback, useEffect, useState } from 'react'
import { toApiError, type ApiError } from '../api/client'

export type ResourceState<T> =
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: ApiError }

/** Fetch on mount and whenever `key` changes; `reload()` re-fetches. Ignores results of superseded requests. */
export function useResource<T>(fetcher: () => Promise<T>, key: readonly unknown[] = []) {
  const [state, setState] = useState<ResourceState<T>>({ status: 'loading' })
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let current = true
    fetcher().then(
      (data) => current && setState({ status: 'success', data }),
      (e: unknown) => current && setState({ status: 'error', error: toApiError(e) }),
    )
    return () => { current = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...key])

  const reload = useCallback(() => {
    setState({ status: 'loading' })
    setNonce((n) => n + 1)
  }, [])

  return { state, reload }
}
