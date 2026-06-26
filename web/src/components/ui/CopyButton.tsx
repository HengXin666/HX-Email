import React from 'react'
import { IconCopy, IconCheck } from '../icons'

interface CopyButtonProps {
  text: string
  size?: number
  className?: string
  timeout?: number
}

export const CopyButton: React.FC<CopyButtonProps> = ({
  text,
  size = 14,
  className = '',
  timeout = 2000
}) => {
  const [copied, setCopied] = React.useState(false)
  const timerRef = React.useRef<ReturnType<typeof setTimeout>>()

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => setCopied(false), timeout)
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      try {
        document.execCommand('copy')
        setCopied(true)
        clearTimeout(timerRef.current)
        timerRef.current = setTimeout(() => setCopied(false), timeout)
      } catch {
        // Silently fail
      }
      document.body.removeChild(textarea)
    }
  }

  React.useEffect(() => {
    return () => clearTimeout(timerRef.current)
  }, [])

  return (
    <button
      onClick={handleCopy}
      className={`p-0.5 rounded transition-colors hover:bg-gh-border/40 ${
        copied ? 'text-gh-success' : 'text-gh-text-muted hover:text-gh-text'
      } ${className}`}
      title={copied ? '已复制' : '复制'}
    >
      {copied ? <IconCheck size={size} /> : <IconCopy size={size} />}
    </button>
  )
}
