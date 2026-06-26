import React from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { IconX } from '../icons'
import { Spinner } from './Spinner'

interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  children: React.ReactNode
  footer?: React.ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl'
}

export const Modal: React.FC<ModalProps> = ({ open, onClose, title, children, footer, size = 'md' }) => {
  const widthClass =
    size === 'sm'
      ? 'max-w-sm'
      : size === 'lg'
      ? 'max-w-2xl'
      : size === 'xl'
      ? 'max-w-4xl'
      : 'max-w-lg'

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 20 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className={`w-full ${widthClass} bg-gh-canvas-subtle border border-gh-border rounded-xl shadow-2xl overflow-hidden`}
            onClick={(e) => e.stopPropagation()}
          >
            {title && (
              <div className="flex items-center justify-between px-5 py-3 border-b border-gh-border">
                <h3 className="text-base font-semibold text-gh-text">{title}</h3>
                <button
                  onClick={onClose}
                  className="p-1 rounded-md text-gh-text-muted hover:text-gh-text hover:bg-gh-border/50 transition-colors"
                >
                  <IconX size={18} />
                </button>
              </div>
            )}
            <div className="px-5 py-4">{children}</div>
            {footer && (
              <div className="px-5 py-3 bg-gh-canvas-inset border-t border-gh-border flex justify-end gap-2">
                {footer}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'subtle'
  size?: 'sm' | 'md'
  loading?: boolean
  icon?: React.ReactNode
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'secondary',
  size = 'md',
  loading,
  icon,
  children,
  className = '',
  disabled,
  ...props
}) => {
  const base =
    'inline-flex items-center justify-center gap-2 font-medium rounded-md transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-offset-gh-canvas focus:ring-gh-accent/50 active:scale-[0.98]'

  const variants = {
    primary:
      'bg-gh-accent text-white hover:brightness-110 shadow-sm shadow-gh-accent/20',
    secondary:
      'bg-gh-canvas-subtle border border-gh-border text-gh-text hover:border-gh-text-muted hover:bg-gh-border/30',
    danger:
      'bg-gh-danger/10 border border-gh-danger/40 text-gh-danger hover:bg-gh-danger/20',
    ghost:
      'text-gh-text-muted hover:text-gh-text hover:bg-gh-border/40',
    subtle:
      'bg-gh-border/30 text-gh-text hover:bg-gh-border/50'
  }

  const sizes = {
    sm: 'px-2.5 py-1 text-xs',
    md: 'px-3 py-1.5 text-sm'
  }

  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {loading ? <Spinner size={16} /> : icon}
      {children}
    </button>
  )
}

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  hint?: string
}

export const Input: React.FC<InputProps> = ({ id, label, hint, className = '', ...props }) => {
  const generatedId = React.useId()
  const inputId = id ?? generatedId

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={inputId} className="text-xs font-medium text-gh-text-muted">
          {label}
        </label>
      )}
      <input
        {...props}
        id={inputId}
        className={`bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent focus:ring-1 focus:ring-gh-accent/50 transition-colors ${className}`}
      />
      {hint && <span className="text-xs text-gh-text-secondary">{hint}</span>}
    </div>
  )
}

interface BadgeProps {
  children: React.ReactNode
  color?: string
  className?: string
  onClick?: () => void
}

export const Badge: React.FC<BadgeProps> = ({ children, color, className = '', onClick }) => (
  <span
    onClick={onClick}
    className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border transition-all ${
      onClick ? 'cursor-pointer hover:brightness-125' : ''
    } ${className}`}
    style={
      color
        ? {
            backgroundColor: color + '20',
            borderColor: color + '40',
            color
          }
        : undefined
    }
  >
    {children}
  </span>
)

interface CardProps {
  children: React.ReactNode
  className?: string
  onClick?: () => void
  selected?: boolean
}

export const Card: React.FC<CardProps> = ({ children, className = '', onClick, selected }) => (
  <motion.div
    whileHover={onClick ? { y: -1 } : undefined}
    whileTap={onClick ? { scale: 0.99 } : undefined}
    onClick={onClick}
    className={`rounded-lg border transition-all ${
      selected
        ? 'border-gh-accent bg-gh-accent/5 shadow-[0_0_0_1px_rgba(88,166,255,0.3)]'
        : 'border-gh-border bg-gh-canvas-subtle hover:border-gh-text-muted'
    } ${onClick ? 'cursor-pointer' : ''} ${className}`}
  >
    {children}
  </motion.div>
)
