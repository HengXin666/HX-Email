export function maskValue(value: string, show: number = 4): string {
  if (!value) return ''
  if (value.length <= show * 2) return '*'.repeat(Math.min(value.length, 8))
  return value.slice(0, show) + '*'.repeat(4) + value.slice(-show)
}

export const CRON_PRESETS: Array<{ label: string; value: string }> = [
  { label: '每小时', value: '0 * * * *' },
  { label: '每天 03:00', value: '0 3 * * *' },
  { label: '每周一 03:00', value: '0 3 * * 1' },
  { label: '每月1号 03:00', value: '0 3 1 * *' }
]
