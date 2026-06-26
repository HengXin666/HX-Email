/**
 * Format an ISO date string to a relative time display (Chinese).
 *
 * - < 1 min  → "刚刚"
 * - < 60 min → "X 分钟前"
 * - < 24 hr  → "X 小时前"
 * - else     → locale short date + time
 */
export function formatRelativeTime(raw: string): string {
  if (!raw) return '—'
  try {
    const d = new Date(raw)
    if (isNaN(d.getTime())) return raw
    const diff = Date.now() - d.getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return '刚刚'
    if (mins < 60) return `${mins} 分钟前`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours} 小时前`
    return d.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return raw
  }
}

/**
 * Format an ISO date string to a fixed locale display (no relative).
 */
export function formatDateTime(raw: string): string {
  if (!raw) return '—'
  try {
    const d = new Date(raw)
    if (isNaN(d.getTime())) return raw
    return d.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return raw
  }
}

/**
 * Format with seconds precision (for audit logs).
 */
export function formatDateTimeFull(raw: string): string {
  if (!raw) return '—'
  try {
    const d = new Date(raw)
    if (isNaN(d.getTime())) return raw
    return d.toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch {
    return raw
  }
}
