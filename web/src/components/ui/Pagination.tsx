import React from 'react'
import { Button } from './Primitives'
import { IconChevronLeft, IconChevronRight } from '../icons'

interface PaginationProps {
  currentPage: number
  totalPages: number
  hasPrev: boolean
  hasNext: boolean
  onPrev: () => void
  onNext: () => void
}

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  hasPrev,
  hasNext,
  onPrev,
  onNext
}) => {
  if (totalPages <= 1) return null

  return (
    <div className="flex items-center justify-center gap-3">
      <Button
        variant="ghost"
        size="sm"
        disabled={!hasPrev}
        onClick={onPrev}
      >
        <IconChevronLeft size={14} /> 上一页
      </Button>
      <span className="text-sm text-gh-text-secondary tabular-nums">
        第 {currentPage} / {totalPages} 页
      </span>
      <Button
        variant="ghost"
        size="sm"
        disabled={!hasNext}
        onClick={onNext}
      >
        下一页 <IconChevronRight size={14} />
      </Button>
    </div>
  )
}
