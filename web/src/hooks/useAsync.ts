import { useState, useCallback, useRef, useEffect } from 'react'

type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'

interface UseAsyncState<T> {
  status: AsyncStatus
  data: T | null
  error: string | null
}

interface UseAsyncReturn<T, Args extends unknown[]> extends UseAsyncState<T> {
  execute: (...args: Args) => Promise<T | null>
  reset: () => void
}

/**
 * Generic hook for async operations with loading/error/data state.
 * Does NOT auto-execute — call execute() manually.
 */
export function useAsync<T, Args extends unknown[] = []>(
  fn: (...args: Args) => Promise<T>
): UseAsyncReturn<T, Args> {
  const [state, setState] = useState<UseAsyncState<T>>({
    status: 'idle',
    data: null,
    error: null
  })
  const mountedRef = useRef(true)

  useEffect(() => {
    return () => {
      mountedRef.current = false
    }
  }, [])

  const execute = useCallback(async (...args: Args): Promise<T | null> => {
    setState({ status: 'loading', data: null, error: null })
    try {
      const result = await fn(...args)
      if (mountedRef.current) {
        setState({ status: 'success', data: result, error: null })
      }
      return result
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      if (mountedRef.current) {
        setState({ status: 'error', data: null, error: message })
      }
      return null
    }
  }, [fn])

  const reset = useCallback(() => {
    setState({ status: 'idle', data: null, error: null })
  }, [])

  return { ...state, execute, reset }
}
