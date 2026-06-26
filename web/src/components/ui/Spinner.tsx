import React from 'react'

interface SpinnerProps {
  size?: number
  className?: string
}

export const Spinner: React.FC<SpinnerProps> = ({ size = 16, className = '' }) => (
  <svg
    className={`animate-spin ${className}`}
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
  >
    <circle
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="3"
      className="opacity-25"
    />
    <path
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      fill="currentColor"
      className="opacity-75"
    />
  </svg>
)
