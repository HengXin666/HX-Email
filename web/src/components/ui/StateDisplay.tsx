import React from 'react'
import { Spinner } from './Spinner'

interface LoadingStateProps {
  message?: string
  className?: string
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = '加载中...',
  className = ''
}) => (
  <div className={`flex flex-col items-center justify-center py-16 gap-3 ${className}`}>
    <Spinner size={24} className="text-gh-text-muted" />
    <span className="text-sm text-gh-text-secondary">{message}</span>
  </div>
)

interface EmptyStateProps {
  message?: string
  className?: string
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  message = '暂无数据',
  className = ''
}) => (
  <div className={`text-center py-16 text-gh-text-secondary text-sm ${className}`}>
    {message}
  </div>
)

interface ErrorStateProps {
  message: string
  onRetry?: () => void
  className?: string
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  message,
  onRetry,
  className = ''
}) => (
  <div className={`flex flex-col items-center justify-center py-16 gap-3 ${className}`}>
    <span className="text-sm text-gh-danger">{message}</span>
    {onRetry && (
      <button
        onClick={onRetry}
        className="text-xs text-gh-accent hover:underline"
      >
        重试
      </button>
    )}
  </div>
)
