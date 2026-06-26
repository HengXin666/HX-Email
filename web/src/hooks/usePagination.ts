import { useState, useCallback } from 'react'

interface UsePaginationOptions {
  pageSize: number
  total: number
}

interface UsePaginationReturn {
  offset: number
  page: number
  totalPages: number
  hasPrev: boolean
  hasNext: boolean
  goNext: () => void
  goPrev: () => void
  goTo: (p: number) => void
  reset: () => void
}

/**
 * Unified pagination hook. Supports both offset-based and page-based modes.
 * Returns `offset` for offset-based APIs and `page` for page-based APIs.
 */
export function usePagination({ pageSize, total }: UsePaginationOptions): UsePaginationReturn {
  const [page, setPage] = useState(1)

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const offset = (page - 1) * pageSize
  const hasPrev = page > 1
  const hasNext = page < totalPages

  const goNext = useCallback(() => {
    setPage((p) => Math.min(p + 1, totalPages))
  }, [totalPages])

  const goPrev = useCallback(() => {
    setPage((p) => Math.max(1, p - 1))
  }, [])

  const goTo = useCallback((p: number) => {
    setPage(Math.max(1, Math.min(p, totalPages)))
  }, [totalPages])

  const reset = useCallback(() => {
    setPage(1)
  }, [])

  return { offset, page, totalPages, hasPrev, hasNext, goNext, goPrev, goTo, reset }
}
