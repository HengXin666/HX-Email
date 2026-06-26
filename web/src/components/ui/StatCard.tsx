import React from 'react'
import { motion } from 'framer-motion'

interface StatCardProps {
  label: string
  value: number | string
  icon: React.FC<{ size?: number }>
  color: string
  trend?: string
  onClick?: () => void
}

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  icon: IconComp,
  color,
  trend,
  onClick
}) => (
  <motion.div
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    whileHover={onClick ? { y: -2 } : undefined}
    onClick={onClick}
    className={`relative overflow-hidden rounded-xl border border-gh-border bg-gh-canvas-subtle p-4 ${
      onClick ? 'cursor-pointer hover:border-gh-text-muted' : ''
    } transition-all`}
  >
    <div
      className="absolute top-0 right-0 w-24 h-24 rounded-full blur-2xl opacity-20"
      style={{ background: color }}
    />
    <div className="relative flex items-start justify-between">
      <div>
        <div className="text-xs text-gh-text-muted mb-1">{label}</div>
        <div className="text-2xl font-bold text-gh-text tabular-nums">{value}</div>
        {trend && <div className="text-xs text-gh-success mt-1">{trend}</div>}
      </div>
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center"
        style={{ background: color + '20', color }}
      >
        <IconComp size={18} />
      </div>
    </div>
  </motion.div>
)
